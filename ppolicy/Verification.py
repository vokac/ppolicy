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
    """Module for mx, connection, domain and user verification. It
    check domain existence and then it try to establish SMTP
    connection with mailhost for the domain (MX, A or AAAA DNS records
    - see RFC2821, chapter 5).

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

    CHECK_SUCCESS_RFC=1
    CHECK_SUCCESS_CACHE=2
    CHECK_FAILED_CACHE=-2

    PARAMS = { 'param': ('string key for data item that should be verified (sender/recipient)', None),
               'timeout': ('set SMTP connection timeout', 20),
               'vtype': ('mx, connection, domain or user verification', 'mx'),
               'table': ('database table with persistent cache', 'verification'),
               'dbExpirePositive': ('positive result expiration time in db', 60*60*24*21),
               'dbExpireNegative': ('negative result expiration time in db', 60*60*3),
               }


    def __getUserDomain(self, value):
        vtype = self.getParam('vtype')

        # create email address to check
        if value.find("@") != -1:
            user, domain = value.split("@", 2)
        else:
            user = 'postmaster'
            domain = value
        if vtype == 'domain':
            user = 'postmaster'
        if vtype in [ 'mx', 'connection' ]:
            user = None

        return user, domain


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for attr in [ 'param', 'timeout', 'vtype', 'table', 'dbExpirePositive', 'dbExpireNegative' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        table = self.getParam('table')
        vtype = self.getParam('vtype')
        #dbExpirePositive = self.getParam('dbExpirePositive')
        dbExpireNegative = self.getParam('dbExpireNegative')

        if vtype not in [ 'mx', 'connection', 'domain', 'user' ]:
            raise ParamError("vtype can be only domain or user")

        self.cacheDB = ListDyn("%s_persistent_cache" % (self.getName()), self.factory, table=table, criteria=["param"], value=["code", "codeEx"], mapping={ 'code': ('code', 'TINYINT', False) }, softExpire=dbExpireNegative*3/4, hardExpire=dbExpireNegative)
        self.cacheDB.start()


    def hashArg(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        param = self.getParam('param')
        paramValue = data.get(param)
        user, domain = self.__getUserDomain(paramValue)
        if user == None:
            return hash("%s" % domain)
        else:
            return hash("%s@%s" % (user, domain))


    def check(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        param = self.getParam('param')
        paramValue = data.get(param, '')
        vtype = self.getParam('vtype')
        dbExpirePositive = self.getParam('dbExpirePositive')
        #dbExpireNegative = self.getParam('dbExpireNegative')

        # RFC 2821, section 4.1.1.2
        # empty MAIL FROM: reverse address may be null
        if param == 'sender' and paramValue == '':
            return Verification.CHECK_SUCCESS_RFC, "%s accept empty From address" % self.getId()

        # RFC 2821, section 4.1.1.3
        # see RCTP TO: grammar
        if param == 'recipient':
            reclc = paramValue.lower()
            if reclc == 'postmaster' or reclc[:11] == 'postmaster@':
                return Verification.CHECK_SUCCESS_RFC, "%s accept all mail to postmaster" % self.getId()

        user, domain = self.__getUserDomain(paramValue)
        if domain == None:
            expl = "%s: address for %s in unknown format: %s" % (self.getId(), param, paramValue)
            logging.getLogger().warn(expl)
            return Verification.CHECK_FAILED, expl
        if vtype != 'user':
            paramValue = domain

        # look in pernament result cache
        cacheCode, cacheVal = self.cacheDB.check({ 'param': paramValue }, operation="check")
        if cacheCode > 0:
            cacheCode, cacheRes, cacheEx = cacheVal[0]
            if cacheCode != ListDyn.CHECK_SOFT_EXPIRED:
                if cacheRes > 0:
                    return Verification.CHECK_SUCCESS_CACHE, cacheEx
                elif cacheRes < 0:
                    return Verification.CHECK_FAILED_CACHE, cacheEx

        # list of mailservers
        try:
            mailhosts = dnscache.getDomainMailhosts(domain, local=False)
        except Exception, e:
            if cacheCode > 0:
                if cacheRes > 0:
                    return Verification.CHECK_SUCCESS_CACHE, cacheEx
                elif cacheRes < 0:
                    return Verification.CHECK_FAILED_CACHE, cacheEx
            return Verification.CHECK_FAILED, "%s DNS failure: %s" % (self.getId(), e)
            
        if len(mailhosts) == 0:
            code = Verification.CHECK_FAILED
            codeEx = "%s: no mailhost for %s" % (self.getId(), domain)
            logging.getLogger().info(codeEx)
            self.cacheDB.check({ 'param': paramValue }, operation="add", value={ 'code': code, 'codeEx': codeEx })
            return code, codeEx

        if vtype == 'mx':
            code = Verification.CHECK_SUCCESS
            codeEx = "%s: mailhost for %s exists" % (self.getId(), domain)
            logging.getLogger().info(codeEx)
            self.cacheDB.check({ 'param': paramValue }, operation="add", value={ 'code': code, 'codeEx': codeEx }, softExpire=dbExpirePositive*3/4, hardExpire=dbExpirePositive)
            return code, codeEx
            

        maxMXToTry = 3
        for mailhost in mailhosts:
            # FIXME: how many MX try? timeout?
            logging.getLogger().debug("trying to check %s for %s@%s" % (mailhost, user, domain))
            code, codeEx = self.checkMailhost(mailhost, domain, user)
            logging.getLogger().debug("checking returned: %s (%s)" % (code, codeEx))
            if code != None and code != Verification.CHECK_UNKNOWN:
                break
            maxMXToTry -= 1
            if maxMXToTry <= 0:
                break

        if code == None or code == Verification.CHECK_UNKNOWN:
            if cacheCode > 0:
                if cacheRes > 0:
                    return Verification.CHECK_SUCCESS_CACHE, cacheEx
                elif cacheRes < 0:
                    return Verification.CHECK_FAILED_CACHE, cacheEx
            return Verification.CHECK_UNKNOWN, "%s didn't get any result" % self.getId()

        # add new informations to pernament cache
        if code > 0:
            self.cacheDB.check({ 'param': paramValue }, operation="add", value={ 'code': code, 'codeEx': codeEx }, softExpire=dbExpirePositive*3/4, hardExpire=dbExpirePositive)
        elif code < 0:
            self.cacheDB.check({ 'param': paramValue }, operation="add", value={ 'code': code, 'codeEx': codeEx })

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
            if user != None:
                code, retmsg = conn.helo()
                if code >= 400:
                    conn.quit()
                    conn.close()
                    if code >= 500:
                        return Verification.CHECK_FAILED, "%s verification HELO failed with code %s: %s" % (param, code, retmsg)
                    else:
                        return Verification.CHECK_UNKNOWN, "%s verification HELO failed with code %s: %s" % (param, code, retmsg)
                code, retmsg = conn.mail("postmaster@%s" % self.factory.getConfig('domain'))
                if code >= 400:
                    conn.quit()
                    conn.close()
                    if code >= 500:
                        return Verification.CHECK_FAILED, "%s verification HELO failed with code %s: %s" % (param, code, retmsg)
                    else:
                        return Verification.CHECK_UNKNOWN, "%s verification HELO failed with code %s: %s" % (param, code, retmsg)
                code, retmsg = conn.rcpt("%s@%s" % (user, domain))
                if code >= 400:
                    conn.quit()
                    conn.close()
                    if code >= 500:
                        return Verification.CHECK_FAILED, "%s verification HELO failed with code %s: %s" % (param, code, retmsg)
                    else:
                        return Verification.CHECK_UNKNOWN, "%s verification HELO failed with code %s: %s" % (param, code, retmsg)
                code, retmsg = conn.rset()
                conn.quit()
            conn.close()
            return Verification.CHECK_SUCCESS, "address verification success"
        except smtplib.SMTPException, err:
            msg = "SMTP communication with %s (%s) failed: %s" % (mailhost, domain, err)
            logging.getLogger().warn("%s: %s" (self.getId(), msg))
            return Verification.CHECK_UNKNOWN, "address verification failed: %s" % msg
        except socket.error, err:
            msg = "socket communication with %s (%s) failed: %s" % (mailhost, domain, err)
            logging.getLogger().warn("%s: %s" % (self.getId(), msg))
            return Verification.CHECK_UNKNOWN, "address verification failed: %s" % msg

        return Verification.CHECK_FAILED, "address verirication failed."
