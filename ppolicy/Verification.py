#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Module to check domain mailserver and/or user mail address
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
import socket
from Base import Base, ParamError
from ListDyn import ListDyn
from tools import dnscache, smtplib


__version__ = "$Revision$"


class Verification(Base):
    """Module for user and domain verification. It check domain
    existence and then it try to establish SMTP connection with
    mailhost for the domain (MX, A or AAAA DNS records - see RFC2821,
    chapter 5).

    You can check if sender/recipient or whatever reasonable has
    correct DNS records as mailhost and try to connect to this server.

    Second option si to check if sender/recipient is accepted by
    remote mailserver. Be carefull when turning on verification and
    first read http://www.postfix.org/ADDRESS_VERIFICATION_README.html
    to see limitation and problem that can happen.

    Module arguments (see output of getParams method):
    param, timeout, type

    Check arguments:
        data ... all input data in dict

    Check returns:
        2 .... verification was successfull (hit pernament cache)
        1 .... verification was successfull
        0 .... undefined (e.g. DNS error, SMTP error, ...)
        -1 ... verification failed
        -2 ... verification failed (hit pernament cache)

    Examples:
        # sender domain verification
        define('verification', 'Verification', param="sender")
        # recipient user verification
        define('verification', 'Verification', param="recipient", vtype="user")
    """

    PARAMS = { 'param': ('string key for data item that should be verified (sender/recipient)', None),
               'timeout': ('set SMTP connection timeout', 20),
               'vtype': ('domain or user verification', 'domain'),
               'table': ('database table with persistent cache', 'verification'),
               'dbExpirePositive': ('positive result expiration time in db', 60*60*24*21),
               'dbExpireNegative': ('negative result expiration time in db', 60*60*3),
               }


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for attr in [ 'param', 'timeout', 'vtype', 'table', 'dbExpirePositive', 'dbExpireNegative' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        table = self.getParam('table')
        vtype = self.getParam('vtype')
        dbExpirePositive = self.getParam('dbExpirePositive')
        dbExpireNegative = self.getParam('dbExpireNegative')

        if vtype not in [ 'domain', 'user' ]:
            raise ParamError("vtype can be only domain or user")

        self.cachePositive = ListDyn("%s_%s_persistent_cache_positive" % (vtype, self.getName()), self.factory, table=table, criteria=["param"], value=True, softExpire=dbExpirePositive*3/4, hardExpire=dbExpirePositive)
        self.cachePositive.start()
        self.cacheNegative = ListDyn("%s_%s_persistent_cache_negative" % (vtype, self.getName()), self.factory, table=table, criteria=["param"], value=True, softExpire=dbExpireNegative*3/4, hardExpire=dbExpireNegative)
        self.cacheNegative.start()


    def hashArg(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        param = self.getParam('param')
        return hash("%s=%s" % (param, data.get(param)))


    def check(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        param = self.getParam('param')
        paramValue = data.get(param, '')
        vtype = self.getParam('vtype')

        # RFC 2821, section 4.1.1.2
        # empty MAIL FROM: reverse address may be null
        if param == 'sender' and paramValue == '':
            return 1, "%s accept empty From address" % self.getId()

        # RFC 2821, section 4.1.1.3
        # see RCTP TO: grammar
        if param == 'recipient':
            reclc = paramValue.lower()
            if reclc == 'postmaster' or reclc[:11] == 'postmaster@':
                return 1, "%s accept all mail to postmaster" % self.getId()

        # create email address to check
        if paramValue.find("@") != -1:
            user, domain = paramValue.split("@", 2)
        else:
            user = 'postmaster'
            domain = paramValue
        if vtype == 'domain':
            user = 'postmaster'
        if user == None or domain == None:
            expl = "%s: address for %s in unknown format: %s" % (self.getId(), param, paramValue)
            logging.getLogger().warn(expl)
            return -1, expl

        # look in pernament result cache
        cacheCode, cacheVal = self.cachePositive.check({ 'param': paramValue }, operation="check")
        if cacheCode > 0:
            return 2, cacheVal
        cacheCode, cacheVal = self.cachePositive.check({ 'param': paramValue }, operation="check")
        if cacheCode > 0:
            return -2, cacheVal

        # list of mailservers
        mailhosts = dnscache.getDomainMailhosts(domain)
        if len(mailhosts) == 0:
            expl = "%s: no mailhost for %s" % (self.getId(), domain)
            logging.getLogger().info(expl)
            return -1, expl

        for mailhost in mailhosts:
            # FIXME: how many MX try? timeout?
            logging.getLogger().debug("trying to check %s for %s@%s" % (mailhost, user, domain))
            code, codeEx = self.checkMailhost(mailhost, domain, user)
            logging.getLogger().debug("checking returned: %s (%s)" % (code, codeEx))
            # FIXME: store result in database
            if code != None and code > 0:
                break

        if code == None:
            return 0, "%s didn't get any result" % self.getId()

        # add new informations to pernament cache
        if code > 0:
            self.cachePositive.check({ 'param': paramValue, 'value': codeEx }, operation="add")
        if code < 0:
            self.cacheNegative.check({ 'param': paramValue, 'value': codeEx }, operation="add")

        return code, codeEx


    def checkMailhost(self, mailhost, domain, user):
        """Check if something listening for incomming SMTP connection
        for mailhost. For details about status that can occur during
        communication see RFC 2821, section 4.3.2"""

        param = self.getParam('param')
        timeout = self.getParam('timeout')
        try:
            conn = smtplib.SMTP(mailhost, timeout=timeout)
            if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                conn.set_debuglevel(10)
            code, retmsg = conn.helo()
            if code >= 400:
                return -1, "%s verification HELO failed: %s" % (param, retmsg)
            code, retmsg = conn.mail("postmaster@%s" % self.factory.getConfig('domain'))
            if code >= 400:
                return -1, "%s verification MAIL failed: %s" % (param, retmsg)
            code, retmsg = conn.rcpt("%s@%s" % (user, domain))
            if code >= 400:
                return -1, "%s verification RCPT failed: %s" % (param, retmsg)
            code, retmsg = conn.rset()
            conn.quit()
            conn.close()
            return 1, "address verification success"
        except smtplib.SMTPException, err:
            msg = "SMTP communication with %s failed: %s" % (domain, err)
            logging.getLogger().warn("%s: %s" (self.getId(), msg))
            return -1, "address verirication failed. %s" % msg
        except socket.error, err:
            msg = "socket communication with %s failed: %s" % (domain, err)
            logging.getLogger().warn("%s: %s" % (self.getId(), msg))
            return -1, "Address verirication failed. %s" % msg

        return -1, "address verirication failed."
