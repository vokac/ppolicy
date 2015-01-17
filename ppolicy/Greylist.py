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

    You should run following cleanup tasks from cron job (may be it
    will be part of this module in the future). Replace XXXX and YYYY
    with same value as for "mustRetry" and "expire":
    mysql 'DELETE FROM `greylist` WHERE UNIX_TIMESTAMP(`date`) + XXXX < UNIX_TIMESTAMP() AND `state` = 0
    mysql 'DELETE FROM `greylist` WHERE UNIX_TIMESTAMP(`date`) + YYYY < UNIX_TIMESTAMP()

    Module arguments (see output of getParams method):
    table

    Check arguments:
        data ... all input data in dict

    Check returns:
        2 .... always allow postmaster
        1 .... was seen before
        0 .... some error occured (database, dns, ...)
        -1 ... greylist in progress
        -2 ... invalid sender address

    Examples:
        # greylisting module with default parameters
        modules['greylist1'] = ( 'Greylist', {} )
        # greylisting module with own database table "grey", delay set
        # to 1 minute and expiration time of triplets to 1 year
        modules['greylist2'] = ( 'Greylist', { table="grey", delay=60,
                                               expiration=86400*365 } )
    """

    PARAMS = { 'table': ('greylist database table', 'greylist'),
               'delay': ('how long to delay mail we see its triplet first time', 10*60),
               'mustRetry': ('time we wait to receive next mail after we geylisted it', 12*60*60),
               'expiration': ('expiration of triplets in database', 60*60*24*31),
               'cachePositive': (None, 24*60*60),# positive can be cached long time
               'cacheUnknown': (None, 30),  # use only very short time, because
               'cacheNegative': (None, 60), # of changing greylist time
               }
    DB_ENGINE="ENGINE=InnoDB"


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for param in [ 'table', 'delay', 'mustRetry', 'expiration' ]:
            if self.getParam(param) == None:
                raise ParamError("%s has to be specified for this module" % param)

        table = self.getParam('table')
        #delay = self.getParam('delay')
        mustRetry = self.getParam('mustRetry')
        expiration = self.getParam('expiration')

        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        try:
            sql = "CREATE TABLE IF NOT EXISTS `%s` (`sender` VARCHAR(255) NOT NULL, `recipient` VARCHAR(255) NOT NULL, `client_address` VARCHAR(255), `date` DATETIME, `state` TINYINT DEFAULT 0, INDEX (`sender`), INDEX (`recipient`), INDEX (`client_address`)) %s" % (table, Greylist.DB_ENGINE)
            if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)

            sql = "DELETE FROM `%s` WHERE (UNIX_TIMESTAMP(`date`) + %i < UNIX_TIMESTAMP() AND `state` = 0) OR (UNIX_TIMESTAMP(`date`) + %i < UNIX_TIMESTAMP())" % (table, mustRetry, expiration)
            if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)

            cursor.close()
            conn.commit()
        except Exception, e:
            cursor.close()
            raise e
        #self.factory.releaseDbConnection(conn)


    def hashArg(self, data, *args, **keywords):
        return hash("\n".join([ "%s=%s" % (x, data.get(x, '').lower()) for x in [ 'sender', 'recipient', 'client_address' ] ]))


    def check(self, data, *args, **keywords):
        sender = data.get('sender', '').lower()
        recipient = data.get('recipient', '').lower()
        client_name = data.get('client_name', '').lower()
        client_address = data.get('client_address')

        # RFC 2821, section 4.1.1.2
        # empty MAIL FROM: reverse address may be null
        #if sender == '':
        #    return 1, "can't check empty from address"

        # RFC 2821, section 4.1.1.3
        # see RCTP TO: grammar
        if recipient == 'postmaster' or recipient[:11] == 'postmaster@':
            return 2, ("allow mail to postmaster without greylisting", 0)

        greysubj = client_address
        if sender != '':
            if sender.rfind("@") != -1:
                user = sender[:sender.rfind('@')]
                domain = sender[sender.rfind('@')+1:]
            else:
                return -2, ("sender address format icorrect %s" % sender, 0)

            # list of mailservers
            try:
                spfres, spfstat, spfexpl = spf.check(i=client_address, s=sender, h=client_name)
                if spfres == 'pass':
                    greysubj = domain
                if greysubj != domain:
                    mailhosts = dnscache.getDomainMailhosts(domain)
                    if client_address in mailhosts:
                        greysubj = domain
            except Exception, e:
                return 0, ("%s DNS failure: %s" % (self.getId(), e), 0)

        retCode = 0
        retInfo = "undefined result (%s module error)" % self.getId()
        retTime = 0
        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        try:
            table = self.getParam('table')

            sql = "SELECT UNIX_TIMESTAMP() - UNIX_TIMESTAMP(`date`) AS `delta`, `state` FROM `%s` WHERE `sender` = %%s AND `recipient` = %%s AND `client_address` = %%s" % table
            
            if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                logging.getLogger().debug("SQL: %s %s" % (sql, str((sender, recipient, greysubj))))
            cursor.execute(sql, (sender, recipient, greysubj))
            greylistDelay = self.getParam('delay')
            greylistExpire = self.getParam('expiration')
            if int(cursor.rowcount) > 0:
                # triplet already exist in database
                sql = None
                row = cursor.fetchone()
                delta = int(row[0])
                state = int(row[1])
                greylistDelay -= delta
                greylistExpire -= delta
                if greylistExpire > 0 and (state > 0 or (state < 0 and greylistDelay <= 0)):
                    # and initial delay period was finished
                    retCode = 1
                    retInfo = 'greylisting was already done'
                    retTime = greylistExpire
                    sql = "UPDATE `%s` SET `date` = NOW(), `state` = 1 WHERE `sender` = %%s AND `recipient` = %%s AND `client_address` = %%s" % table
                else:
                    # but we are in initial delay period or record expired
                    if greylistExpire <= 0:
                        # update expired record -> set state to initial
                        # greylisting period
                        greylistDelay = self.getParam('delay')
                        sql = "UPDATE `%s` SET `date` = NOW(), `state` = -1 WHERE `sender` = %%s AND `recipient` = %%s AND `client_address` = %%s" % table
                    retCode = -1
                    retInfo = 'greylisting in progress: %ss' % greylistDelay
                    retTime = greylistDelay
                if sql != None:
                    try:
                        # this is not critical so do it in separate try section
                        if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                            logging.getLogger().debug("SQL: %s %s" % (sql, str((sender, recipient, greysubj))))
                        cursor.execute(sql, (sender, recipient, greysubj))
                    except Exception, e:
                        logging.getLogger().error("updating expiration time failed: %s" % e)
            else:
                # insert new
                retCode = -1
                retInfo = 'greylisting in progress: %ss' % greylistDelay
                retTime = greylistDelay
                sql = "INSERT INTO `%s` (`sender`, `recipient`, `client_address`, `date`, `state`) VALUES (%%s, %%s, %%s, NOW(), -1)" % table
                if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                    logging.getLogger().debug("SQL: %s %s" % (sql, str((sender, recipient, greysubj))))
                cursor.execute(sql, (sender, recipient, greysubj))

            cursor.close()
            conn.commit()
        except Exception, e:
            try:
                cursor.close()
            except:
                pass
            expl = "%s: database error" % self.getId()
            logging.getLogger().error("%s: %s" % (expl, e))
            return 0, (expl, 0)
        #self.factory.releaseDbConnection(conn)

        return retCode, (retInfo, retTime)
