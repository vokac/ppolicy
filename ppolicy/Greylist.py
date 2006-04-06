#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# This module provide greylisting
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
from Base import Base, ParamError
from tools import spf, dnscache


__version__ = "$Revision$"


class Greylist(Base):
    """Greylist implementation. Mail thats triplet (from,to,client)
    was not seen before should be rejected with code 450 (temporary
    failed). It relay on fact that spammer software will not try to
    send mail once again and correctly configured mailservers must
    try it one again (see RFC 2821).

    Be carefull because some poorly configured mailserver did not
    retry to send mail again and some mailing list has unique sender
    name for each mail and this module delay delivery and increase
    load of remote server.

    Module arguments (see output of getParams method):
    table

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... was seen before
        0 .... some error occured (database, dns, ...)
        -1 ... Graylist in progress

    Examples:
        # greylisting module with default parameters
        define('greylist1', 'Greylist')
        # greylisting module with own database table "grey", delay set
        # to 1 minute and expiration time of triplets to 1 year
        define('greylist2', 'Greylist', table="grey", delay=60, expiration=86400*365)
    """

    PARAMS = { 'table': ('greylist database table', 'greylist'),
               'delay': ('how long to delay mail we see its triplet first time', 10*60),
               'expiration': ('expiration of triplets in database', 60*60*24*31),
               'cachePositive': (None, 0), # handle own cache
               'cacheUnknown': (None, 0),  #
               'cacheNegative': (None, 0), # in this module
               }


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        table = self.getParam('table')
        if table == None:
            raise ParamError('table has to be specified for this module')

        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        sql = "CREATE TABLE IF NOT EXISTS `%s` (`sender` VARCHAR(255) NOT NULL, `recipient` VARCHAR(255) NOT NULL, `client_address` VARCHAR(50), `delay` DATETIME, `expire` DATETIME)" % table
        logging.getLogger().debug("SQL: %s" % sql)
        cursor.execute(sql)

        sql = "DELETE FROM `%s` WHERE UNIX_TIMESTAMP(`expire`) < UNIX_TIMESTAMP()" % table
        logging.getLogger().debug("SQL: %s" % sql)
        cursor.execute(sql)
        cursor.close()


    def hashArg(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        return hash("\n".join(map(lambda x: "%s=%s" % (x, data.get(x)), [ 'sender', 'recipient', 'client_address' ])))


    def check(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        sender = data.get('sender')
        recipient = data.get('recipient')
        client_name = data.get('client_name')
        client_address = data.get('client_address')

        # RFC 2821, section 4.1.1.2
        # empty MAIL FROM: reverse address may be null
        if sender == '':
            return 1, "can't check empty from address"

        # RFC 2821, section 4.1.1.3
        # see RCTP TO: grammar
        reclc = recipient.lower()
        if reclc == 'postmaster' or reclc[:11] == 'postmaster@':
            return 1, "allow mail to postmaster without graylisting"

        try:
            user, domain = sender.split("@")
        except ValueError:
            logging.getLogger().warn("%s: sender address in unknown format: %s" %
                                     (self.getId(), sender))
            return -1, "sender address format icorrect %s" % sender

        # list of mailservers
        try:
            mailhosts = dnscache.getDomainMailhosts(domain)
            spfres, spfstat, spfexpl = spf.check(i=client_address,
                                                 s=sender, h=client_name)
        except Exception, e:
            return 0, "%s DNS failure: %s" % (self.getId(), e)

        if client_address in mailhosts or spfres == 'pass':
            greysubj = domain
        else:
            greysubj = client_address

        retCode = 0
        retInfo = "undefined result (%s module error)" % self.getId()
        try:
            conn = self.factory.getDbConnection()
            cursor = conn.cursor()
            table = self.getParam('table')

            sql = "SELECT UNIX_TIMESTAMP(`delay`) - UNIX_TIMESTAMP() AS `greylistDelay`, UNIX_TIMESTAMP(`expire`) - UNIX_TIMESTAMP() AS `greylistExpire` FROM `%s` WHERE `sender` = '%s' AND `recipient` = '%s' AND `client_address` = '%s'" % (table, sender.replace("'", "\\'"), recipient.replace("'", "\\'"), greysubj.replace("'", "\\'"))
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)
            greylistDelay = self.getParam('delay')
            greylistExpire = self.getParam('expiration')
            if int(cursor.rowcount) > 0:
                # triplet already exist in database
                row = cursor.fetchone()
                if row[1] > 0:
                    greylistDelay = row[0]
                if greylistDelay < 0:
                    # and initial delay period was finished
                    retCode = 1
                    retInfo = 'greylisting was already done'
                else:
                    # but we are in initial delay period
                    retCode = -1
                    retInfo = 'greylisting in progress, mail will be accepted in %ss' % greylistDelay
                try:
                    # this is not critical so do it in separate try section
                    sql = "UPDATE `%s` SET `expire` = FROM_UNIXTIME(UNIX_TIMESTAMP()+%i) WHERE `sender` = '%s' AND `recipient` = '%s' AND `client_address` = '%s'" % (table, greylistExpire, sender.replace("'", "\\'"), recipient.replace("'", "\\'"), greysubj.replace("'", "\\'"))
                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)
                except Exception, e:
                    logging.getLogger().error("updating expiration time failed: %s" % e)
            else:
                # insert new
                retCode = -1
                retInfo = 'greylist in progress: %ss' % greylistDelay
                sql = "INSERT INTO `%s` (`sender`, `recipient`, `client_address`, `delay`, `expire`) VALUES ('%s', '%s', '%s', FROM_UNIXTIME(UNIX_TIMESTAMP()+%i), FROM_UNIXTIME(UNIX_TIMESTAMP()+%i))" % (table, sender.replace("'", "\\'"), recipient.replace("'", "\\'"), greysubj.replace("'", "\\'"), greylistDelay, greylistExpire)
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)

        except Exception, e:
            cursor.close()
            expl = "%s: database error" % self.getId()
            logging.getLogger().error("%s: %s" % (expl, e))
            return 0, expl

        return retCode, retInfo
