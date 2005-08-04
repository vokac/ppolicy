#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Check modules:
#   Base
#   Conditional (AND, OR, NOT)
#   Flow (IF, IF3)
#   Real (List, SPF, UserDomain, ...)
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import time, threading
from twisted.python import log
from twisted.python import components
from twisted.internet import task
import tools



class NotImplementedException(Exception):
    pass



class IPPolicyServerCheck(components.Interface):
    """Abstract interface for postfix policy check modules."""

    def getId(self):
        """get module unique ID."""

    def setParams(self, *args, **keywords):
        """set module parameters."""

    def doStart(self, *args, **keywords):
        """Called when changing state to 'ready'."""

    def doStop(self, *args, **keywords):
        """Called when changing state to 'stopped'."""

    def doCheck(self, data):
        """check request stored data againts policy and returns tuple
        of SMTPError, SMTPNumber, SMTPResponse or Postfix specific "dunno".
        example: 550, '5.0.7', 'Sender not permitted'
        """



class PPolicyServerCheckBase:
    """Base class for postfix policy check modules."""

    __implements__ = (IPPolicyServerCheck, )


    def __init__(self, *args, **keywords):
        self.id = self.__class__.__name__
        self._stateLock = threading.Lock()
        self._state = 'initializing'
        self.factory = None
        self.debug = 0
        self.defaultActionCode = 'dunno'
        self.defaultActionNr = None
        self.defaultActionResponse = None
        self._cacheResult = True
        self._cacheResultLock = threading.Lock()
        self._cacheResultData = {}
        self._cacheResultExpire = {}
        self._cacheResultLifetime = 600
        self._cacheResultCheckInterval = 60
        self._cacheResultSize = 10000
        #self._cacheResultCleanTask = task.LoopingCall(self.__cleanCacheResult)
        self.setParams(**keywords)
        self.setState('init')


    def getId(self):
        """get module identification."""
        return self.id


    def setParams(self, *args, **keywords):
        """set 'debug' log level for this module
        debug:
          0 ... quiet (default)
          1 ... verbose
        defaultActionCode:
        defaultActionNr:
        defaultActionResponse:
          default result if something went wrong
        cacheResult:
          use result cache (default: True)
        cacheResultLifetime:
          number of seconds for caching results for data hash (default: 600)
        """
        #self._cacheResultCleanTask.stop()
        lastState = self.setState('stop')
        self.debug = keywords.get('debug', self.debug)
        self.defaultActionCode = keywords.get('defaultActionCode', self.defaultActionCode)
        self.defaultActionNr = keywords.get('defaultActionNr', self.defaultActionNr)
        self.defaultActionResponse = keywords.get('defaultActionResponse', self.defaultActionResponse)
        self._cacheResult = keywords.get('cacheResult', self._cacheResult)
        self._cacheResultLifetime = keywords.get('cacheResultLifetime', self._cacheResultLifetime)
        self._cacheResultCheckTime = time.time()
        self.setState(lastState)
        #self._cacheDataCleanTask.start(self._cacheDataCleanInterval)


    def dataHash(self, data):
        """Compute hash from data which is then used as index
        to the result cache. Changing this function in subclasses
        and using only required fields for hash can improve cache
        usage and performance."""
        keys = sorted(data.keys())
        return hash("\n".join([ "=".join([x, data[x]]) for x in keys ]))


    def setState(self, state, *args, **keywords):
        self._stateLock.acquire()

        try:
            lastState = self._state
            if self._state == state:
                return
            if self._state != 'ready' and state == 'start':
                self._state = 'starting'
                self.__cleanCacheResult(True)
                self.doStart(**keywords)
                self._state = 'ready'
            elif self._state == 'ready' and state == 'stop':
                self._state = 'stopping'
                self.doStop(**keywords)
                self._state = 'stopped'
            elif state == 'restart':
                if self._state == 'ready':
                    self._state = 'stopping'
                    self.doStop(**keywords)
                    self._state = 'stopped'
                self._state = 'starting'
                self.doStart(**keywords)
                self._state = 'ready'
            else:
                self._state = state
        finally:
            self._stateLock.release()

        return lastState


    def doStartInt(self, *args, **keywords):
        """Called by protocol factory once before doCheck is used."""
        self.setState('start', **keywords)


    def doStart(self, *args, **keywords):
        """Called when changing state to 'ready'."""
        pass


    def doStopInt(self, *args, **keywords):
        """Called by protocol factory before shutdown."""
        self.setState('stop', **keywords)


    def doStop(self, *args, **keywords):
        """Called when changing state to 'stopped'."""
        pass


    def doRestartInt(self, *args, **keywords):
        """Restart module/reload new configuration."""
        self.setState('restart', **keywords)


    def doCheckInt(self, data):
        """This method will ensure check result caching and should not
        be redefined. User checking should be implemented in doCheck
        method."""
        if self._state != 'ready':
            return self.defaultActionCode, self.defaultActionNr, self.defaultActionResponse

        dataHash = self.dataHash(data)
        if self._cacheResult:
            code, nr, response = self.__getCacheResult(dataHash)
            if code != None:
                log.msg("[DBG] %s: result cache hit" % self.getId())
                return code, nr, response
        code, nr, response = self.doCheck(data)
        if self._cacheResult:
            self.__addCacheResult(dataHash, code, nr, response)
        return code, nr, response


    def doCheck(self, data):
        """This method will be called according configuration to
        check input data. If chaching is enabled (default) it will
        be called only if response for requested data is not in cache.
        This method has to be implemented in child classes."""
        raise NotImplementedException("Don't call base class directly")


    def __addCacheResult(self, dataHash, code, nr, response):
        """Add new result to the cache."""
        if dataHash != 0:
            self.__cleanCacheResult()
            self._cacheResultLock.acquire()
            try:
                self._cacheResultExpire[dataHash] = time.time() \
                                                 + self._cacheResultLifetime
                self._cacheResultData[dataHash] = (code, nr, response)
            finally:
                self._cacheResultLock.release()


    def __getCacheResult(self, dataHash):
        """Get result from the cache."""
        code, nr, response = (None, None, None)
        if dataHash != 0:
            self._cacheResultLock.acquire()
            try:
                if self._cacheResultData.has_key(dataHash) and self._cacheResultExpire[dataHash] >= time.time():
                    code, nr, response = self._cacheResultData[dataHash]
            finally:
                self._cacheResultLock.release()
        return code, nr, response


    def __cleanCacheResult(self, all = False):
        """Expired cache records cleanup."""
        self._cacheResultLock.acquire()
        try:
            if all:
                self._cacheResultExpire = {}
                self._cacheResultData = {}
            else:
                toDel = []
                if self._cacheResultCheckTime <= time.time():
                    self._cacheResultCheckTime = time.time() + self._cacheResultCheckInterval
                    for key in self._cacheResultExpire.keys():
                        if self._cacheResultExpire[key] <= time.time():
                            toDel.append(key)

                if len(self._cacheResultExpire) - len(toDel) > 19 * self._cacheResultSize / 20:
                    toDel = [] # this automatically include all expired
                    expVal = sorted(self._cacheResultExpire.values())
                    trh = expVal[len(expVal)/2]
                    for expKey in self._cacheResultExpire.keys():
                        if self._cacheResultExpire[expKey] <= trh:
                            toDel.append(expKey)    

                log.msg("[DBG] %s: result cache cleanup (%s from %s items)" %
                        (self.getId(), len(toDel), len(self._cacheResultExpire)))

                for key in toDel:
                    del(self._cacheResultExpire[key])
                    del(self._cacheResultData[key])
        finally:
            self._cacheResultLock.release()



class DummyCheck(PPolicyServerCheckBase):
    """Dummy check module for testing."""


    def __init__(self, *args, **keywords):
        PPolicyServerCheckBase.__init__(self, **keywords)


    #def getId(self):
    #    return self.id


    #def setParams(self, *args, **keywords):
    #    lastState = self.setState('stop')
    #    PPolicyServerCheckBase.setParams(self, **keywords)
    #    self.someParam = keywords.get('someParam', self.someParam)
    #    self.setState(lastState)


    #def dataHash(self, data):
    #    return hash


    #def doStart(self, *args, **keywords):
    #    pass


    #def doStop(self, *args, **keywords):
    #    pass


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())
        return 'dunno', None, None



class PassCheck(PPolicyServerCheckBase):
    """Check module that always succeed."""


    def __init__(self, *args, **keywords):
        self.code = 250
        self.response = "succeed"
        PPolicyServerCheckBase.__init__(self, **keywords)


    def setParams(self, *args, **keywords):
        PPolicyServerCheckBase.setParams(self, **keywords)
        self.code = keywords.get('code', self.code)
        self.response = keywords.get('response', self.response)


    def dataHash(self, data):
        return 0


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())
        return self.code, ".".join([ x for x in str(self.code) ]), "%s %s" % (self.getId(), self.response)



class FailCheck(PPolicyServerCheckBase):
    """Check module that always fail with temporary failure 450."""


    def __init__(self, *args, **keywords):
        self.code = 450
        self.response = "failed"
        PPolicyServerCheckBase.__init__(self, **keywords)


    def setParams(self, *args, **keywords):
        PPolicyServerCheckBase.setParams(self, **keywords)
        self.code = keywords.get('code', self.code)
        self.response = keywords.get('response', self.response)


    def dataHash(self, data):
        return 0


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())
        return self.code, ".".join([ x for x in str(self.code) ]), "%s %s" % (self.getId(), self.response)



class AndCheck(PPolicyServerCheckBase):
    """Run defined checks and join result with logical AND."""


    def __init__(self, *args, **keywords):
        self.checks = []
        PPolicyServerCheckBase.__init__(self, **keywords)


    def getId(self):
        checks = ",".join(map(lambda x: x.getId(), self.checks))
        return "%s(%s)" % (self.id, checks)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        PPolicyServerCheckBase.setParams(self, **keywords)
        self.checks = keywords.get('checks', self.checks)
        self.setState(lastState)


    def doStart(self, *args, **keywords):
        for check in self.checks:
            check.doStartInt(**keywords)


    def doStop(self, *args, **keywords):
        for check in self.checks:
            check.doStopInt(**keywords)


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())

        if self.checks == []:
            log.msg("[WRN] %s: no check defined" % self.getId())
            return 'dunno', None, None

        code2xx = True
        for check in self.checks:
            code, nr, response = check.doCheckInt(data)
            if code != 'dunno' and code >= 400:
                return code, nr, "%s failed: %s" % (self.getId(), response)
            if code == 'dunno' or code >= 300:
                code2xx = False

        if code2xx:
            return 250, '2.5.0', "%s all passed Ok" % self.getId()
        else:
            return 'dunno', None, None



class OrCheck(PPolicyServerCheckBase):
    """Run defined checks and join result with logical OR."""


    def __init__(self, *args, **keywords):
        self.checks = []
        PPolicyServerCheckBase.__init__(self, **keywords)


    def getId(self):
        checks = ",".join(map(lambda x: x.getId(), self.checks))
        return "%s(%s)" % (self.id, checks)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        PPolicyServerCheckBase.setParams(self, **keywords)
        self.checks = keywords.get('checks', self.checks)
        self.setState(lastState)


    def doStart(self, *args, **keywords):
        for check in self.checks:
            check.doStartInt(**keywords)


    def doStop(self, *args, **keywords):
        for check in self.checks:
            check.doStopInt(**keywords)


    def doCheck(self, data):

        log.msg("[DBG] %s: running check" % self.getId())

        if self.checks == []:
            log.msg("[WRN] %s: no check defined" % self.getId())
            return 'dunno', None, None

        for check in self.checks:
            code, nr, response = check.doCheckInt(data)
            if code == 'dunno' or code < 400:
                return code, nr, "%s Ok: %s" % (self.getId(), response)

        return 450, '4.5.0', "%s all failed" % self.getId()



class NotCheck(PPolicyServerCheckBase):
    """Run defined check and on result apply logical NOT."""


    def __init__(self, *args, **keywords):
        self.check = None
        PPolicyServerCheckBase.__init__(self, **keywords)


    def getId(self):
        if self.check != None:
            return "%s(%s)" % (self.id, self.check.getId())
        else:
            return "%s(NDEF)" % self.id


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        PPolicyServerCheckBase.setParams(self, **keywords)
        self.check = keywords.get('check', self.check)
        self.setState(lastState)


    def doStart(self, *args, **keywords):
        if self.check != None:
            self.check.doStartInt(**keywords)


    def doStop(self, *args, **keywords):
        if self.check != None:
            self.check.doStopInt(**keywords)


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())

        if self.check == None:
            log.msg("[WRN] %s: no check defined" % self.getId())
            return 'dunno', None, None

        code, nr, response = self.check.doCheckInt(data)
        if code != 'dunno' and code >= 400:
            return 'dunno', None, None
        else:
            return 450, "4.5.0", "%s failed: %s" % (self.getId(), response)



class IfCheck(PPolicyServerCheckBase):
    """Run check and according result run first (pass) or second (fail)
    check. It prodide IF functionality for module configuration."""


    def __init__(self, *args, **keywords):
        self.ifCheck = None
        self.passCheck = None
        self.failCheck = None
        PPolicyServerCheckBase.__init__(self, **keywords)


    def getId(self):
        if self.ifCheck != None:
            ifCheck = self.ifCheck.getId()
        else:
            ifCheck = "NDEF"
        if self.passCheck != None:
            passCheck = self.passCheck.getId()
        else:
            passCheck = "NDEF"
        if self.failCheck != None:
            failCheck = self.failCheck.getId()
        else:
            failCheck = "NDEF"
        return "%s(%s?%s:%s)" % (self.id, ifCheck, passCheck, failCheck)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        PPolicyServerCheckBase.setParams(self, **keywords)
        self.ifCheck = keywords.get('ifCheck', self.ifCheck)
        self.passCheck = keywords.get('passCheck', self.passCheck)
        self.failCheck = keywords.get('failCheck', self.failCheck)
        self.setState(lastState)


    def doStart(self, *args, **keywords):
        if self.ifCheck != None:
            self.ifCheck.doStartInt(**keywords)
        if self.passCheck != None:
            self.passCheck.doStartInt(**keywords)
        if self.failCheck != None:
            self.failCheck.doStartInt(**keywords)


    def doStop(self, *args, **keywords):
        if self.ifCheck != None:
            self.ifCheck.doStopInt(**keywords)
        if self.passCheck != None:
            self.passCheck.doStopInt(**keywords)
        if self.failCheck != None:
            self.failCheck.doStopInt(**keywords)


    def doCheck(self, data):

        log.msg("[DBG] %s: running check" % self.getId())

        if self.ifCheck == None:
            log.msg("[WRN] %s: no ifCheck defined" % self.getId())
            return 'dunno', None, None

        code, nr, response = self.ifCheck.doCheckInt(data)
        if code != 'dunno' and code >= 400:
            check = self.failCheck
        else:
            check = self.passCheck

        if check == None:
            log.msg("[WRN] %s: no check defined for result %s" %
                    (self.getId(), code))
            return 'dunno', None, None

        return check.doCheckInt(data)



class If3Check(PPolicyServerCheckBase):
    """Run check and according result run first (pass), second (fail)
    or third (dunno) check. It prodide three state IF functionality
    for module configuration."""


    def __init__(self, *args, **keywords):
        self.ifCheck = None
        self.passCheck = None
        self.failCheck = None
        self.dunnoCheck = None
        PPolicyServerCheckBase.__init__(self, **keywords)


    def getId(self):
        if self.ifCheck != None:
            ifCheck = self.ifCheck.getId()
        else:
            ifCheck = "NDEF"
        if self.passCheck != None:
            passCheck = self.passCheck.getId()
        else:
            passCheck = "NDEF"
        if self.failCheck != None:
            failCheck = self.failCheck.getId()
        else:
            failCheck = "NDEF"
        if self.dunnoCheck != None:
            dunnoCheck = self.dunnoCheck.getId()
        else:
            dunnoCheck = "NDEF"
        return "%s(%s?%s:%s:%s)" % (self.id, ifCheck, passCheck,
                                    failCheck, dunnoCheck)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        PPolicyServerCheckBase.setParams(self, **keywords)
        self.ifCheck = keywords.get('ifCheck', self.ifCheck)
        self.passCheck = keywords.get('passCheck', self.passCheck)
        self.failCheck = keywords.get('failCheck', self.failCheck)
        self.dunnoCheck = keywords.get('dunnoCheck', self.dunnoCheck)
        self.setState(lastState)


    def doStart(self, *args, **keywords):
        if self.ifCheck != None:
            self.ifCheck.doStartInt(**keywords)
        if self.passCheck != None:
            self.passCheck.doStartInt(**keywords)
        if self.failCheck != None:
            self.failCheck.doStartInt(**keywords)
        if self.dunnoCheck != None:
            self.dunnoCheck.doStartInt(**keywords)


    def doStop(self, *args, **keywords):
        if self.ifCheck != None:
            self.ifCheck.doStopInt(**keywords)
        if self.passCheck != None:
            self.passCheck.doStopInt(**keywords)
        if self.failCheck != None:
            self.failCheck.doStopInt(**keywords)
        if self.dunnoCheck != None:
            self.dunnoCheck.doStopInt(**keywords)


    def doCheck(self, data):

        log.msg("[DBG] %s: running check" % self.getId())

        if self.ifCheck == None:
            log.msg("[WRN] %s: no ifCheck defined" % self.getId())
            check = self.dunnoCheck
            code = 'dunno'
        else:
            code, nr, response = self.ifCheck.doCheckInt(data)
            if code == 'dunno':
                check = self.dunnoCheck
            elif code >= 400:
                check = self.failCheck
            else:
                check = self.passCheck

        if check == None:
            log.msg("[WRN] %s: no check defined for result %s" %
                    (self.getId(), code))
            return 'dunno', None, None

        return check.doCheckInt(data)



class ListCheck(PPolicyServerCheckBase):
    """Check if item is in specified black/white list. Together
    with IfCheck it can be used to check only some user/domain/...
    with further modules"""


    def __init__(self, *args, **keywords):
        self.param = None
        self.paramFunction = None
        self.whitelistTable = None
        self.whitelistColumn = 'name'
        self.blacklistTable = None
        self.blacklistColumn = 'name'
        self.cacheSize = 0
        self.cache = None
        PPolicyServerCheckBase.__init__(self, **keywords)


    def getId(self):
        return "%s[%s,%s]" % (self.id, self.whitelistTable,
                              self.blacklistTable)


    def setParams(self, *args, **keywords):
        """
        param:
          string key for data item that should be checked
        paramFunction:
          optional function to process 'param' before checking with lists
        whitelistTable: (default: None)
        whitelistColumn: (default: name)
          database table and column with whitelist records
        blacklistTable: (default: None)
        blacklistColumn: (default: name)
          database table and column with blacklist records
        cacheSize:
          max number of records in memory cache (default: 0 - all records)
        """
        lastState = self.setState('stop')
        PPolicyServerCheckBase.setParams(self, **keywords)
        self.param = keywords.get('param', self.param)
        self.paramFunction = keywords.get('paramFunction', self.paramFunction)
        self.whitelistTable = keywords.get('whitelistTable', self.whitelistTable)
        self.whitelistColumn = keywords.get('whitelistColumn', self.whitelistColumn)
        self.blacklistTable = keywords.get('blacklistTable', self.blacklistTable)
        self.blacklistColumn = keywords.get('blacklistColumn', self.blacklistColumn)
        self.cacheSize = keywords.get('cacheSize', self.cacheSize)
        self.setState(lastState)


    def dataHash(self, data):
        if self.param == None:
            return 0
        else:
            return hash("=".join([ self.param, data.get(self.param) ]))


    def doStart(self, *args, **keywords):
        self.factory = keywords.get('factory', self.factory)
        if self.factory != None:
            self.getDbConnection = self.factory.getDbConnection
        self.cache = tools.DbMemWBCache(self,
                                        self.whitelistTable,
                                        self.whitelistColumn,
                                        self.blacklistTable,
                                        self.blacklistColumn,
                                        self.cacheSize)


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())

        if self.paramFunction == None:
            testDataArr = [ data.get(self.param) ]
        else:
            testDataArr = self.paramFunction(data.get(self.param))

        if testDataArr in [ None, [], [ None ] ]:
            log.msg("[WRN] %s: no test data for %s" %
                    (self.getId(), self.param))
            return 'dunno', None, None

        for testData in testDataArr:
            if self.__isInWhitelist(testData):
                return 250, '2.5.0', "%s in whitelist" % self.getId()
            if self.__isInBlacklist(testData):
                return 450, '4.5.0', "%s in blacklist" % self.getId()

        return self.defaultActionCode, self.defaultActionNr, self.defaultActionResponse


    def __isInWhitelist(self, data):
        if self.whitelistTable == None or self.whitelistColumn == None:
            return False

        return self.cache.get(data) == True


    def __isInBlacklist(self, data):
        if self.blacklistTable == None or self.blacklistColumn == None:
            return False

        return self.cache.get(data) == False


    def getDbConnection(self):
        raise Exception("No connection function defined")



class SPFCheck(PPolicyServerCheckBase):
    """Module for checking SPF records. It can run in passive
    or restrictive mode. Passive mode is default and recomended
    for general usage. Restrictive drop too much correct mail
    and shoul be used only in special cases when you really
    know what you are doing..."""


    def __init__(self, *args, **keywords):
        self.restrictive = False
        PPolicyServerCheckBase.__init__(self, **keywords)


    def setParams(self, *args, **keywords):
        """set 'restrictive' SPF checking and call base class
        L{PPolicyServer.PPolicyServerBase.setParams}
        restrictive:
          False ... passive, Unknown Querys are permitted (default)
          True  ... restrictive, Unknown Querys are denyed
        """
        lastState = self.setState('stop')
        PPolicyServerCheckBase.setParams(self, **keywords)
        self.restrictive = keywords.get('restrictive', self.restrictive)
        self.setState(lastState)


    def dataHash(self, data):
        """Compute hash only from used data fields."""
        keys = sorted(data.keys())
        return hash("\n".join([ "=".join([x, data[x]]) for x in keys if x in [ "sender", "client_address", "client_name" ] ]))


    def doCheck(self, data):
        """ check Request against SPF results in 'deny', 'unknown', 'pass'"""
        log.msg("[DBG] %s: running check" % self.getId())
        import spf
        sender = data.get('sender', '')
        client_address = data.get('client_address')
        client_name = data.get('client_name')
        if len(sender) > 0 and sender[0] == '<': sender = sender[1:]
        if len(sender) > 0 and sender[-1] == '>': sender = sender[:-1]

        try:
            log.msg("[DBG] %s: spf.check('%s', '%s', '%s')" %
                    (self.getId(), client_address, sender, client_name))
            result, mtastatus, explanation = spf.check(i=client_address,
                                                       s=sender, h=client_name)
            log.msg("[DBG] %s: result: %s, %s, %s" %
                    (self.getId(), result, mtastatus, explanation))
        except Exception, error:
            log.msg("[ERR] %s: checking SPF failed: %s" %
                    (self.getId(), str(error)))
            return 'dunno', None, None

        if self.restrictive:
            if result.lower() == 'unknown':
                return 550, '5.5.7', 'SPF Policy violation'
            else:
                return mtastatus, mtastatus, explanation
        else:
            if result.lower() != 'deny':
                return 250, '2.5.0', 'SPF Policy success'
            else:
                return mtastatus, mtastatus, explanation



class UserDomainCheck(PPolicyServerCheckBase):
    """Check if sender/recipient mailserver is reachable. It provide
    also sender/recipient verification if "verify" parameter is set
    to True (default is False). Be carefull when turning on verification
    and first read http://www.postfix.org/ADDRESS_VERIFICATION_README.html
    about its limitation"""


    def __init__(self, *args, **keywords):
        self.param = 'sender'
        self.verify = False
        self.cacheTable = "verif_%s" % self.param
        self.cacheCols = { 'key': 'name', 'res': 'result', 'exp': 'expir' }
        self.cachePositive = 60*60*24*31    # month
        self.cacheNegative = 60*60*4        # 4 hours
        self.cacheNegative5xx = 60*60*24*2  # 2 days
        self.cacheSize = 0
        self.cache = None
        PPolicyServerCheckBase.__init__(self, **keywords)


    def setParams(self, *args, **keywords):
        """
        param:
          string key for data item that should be verified
        verify:
          verify user, not only domain mailserver (default: False)
        cacheTable:
          database table name for caching data (default: verif_"param")
        cacheCols:
          dictionary { 'key': 'name',
                       'res': 'result',
                       'exp': 'expir' }
        cachePositive:
          expiration time sucessfully verified records (default: month)
        cacheNegative:
          expiration time if verification fail (def: 4 hours)
        cacheNegative5xx:
          expiration time if verification fail with code 5xx (def: 2 days)
        cacheSize:
          max number of records in memory cache (default: 0 - all records)
        """
        lastState = self.setState('stop')
        PPolicyServerCheckBase.setParams(self, **keywords)
        self.param = keywords.get('param', self.param)
        self.verify = keywords.get('verify', self.verify)
        self.cacheTable = keywords.get('cacheTable', self.cacheTable)
        self.cacheCols = keywords.get('cacheCols', self.cacheCols)
        self.cachePositive = keywords.get('cachePositive', self.cachePositive)
        self.cacheNegative = keywords.get('cacheNegative', self.cacheNegative)
        self.cacheNegative5xx = keywords.get('cacheNegative5xx', self.cacheNegative5xx)
        self.cacheSize = keywords.get('cacheSize', self.cacheSize)
        self.setState(lastState)


    def dataHash(self, data):
        """Compute hash only from used data fields."""
        return hash("=".join([ self.param, data.get(self.param) ]))


    def doStart(self, *args, **keywords):
        self.factory = keywords.get('factory', self.factory)
        if self.factory != None:
            self.getDbConnection = self.factory.getDbConnection
        self.cache = tools.DbMemCache(self, self.cacheTable, self.cacheCols,
                                      self.cacheSize)


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())
        if not data.has_key(self.param):
            return self.defaultActionCode, self.defaultActionNr, self.defaultActionResponse

        code = self.defaultActionCode
        nr = self.defaultActionNr
        response = self.defaultActionResponse

        try:
            user, domain = data[self.param].split("@")
            if self.verify:
                key = "%s@%s" % (user, domain)
            else:
                key = domain
            res = self.cache.get(key)
            if res != None:
                code = int(res[:res.find(":")])
                response = res[res.find(":")+1:]
            else:
                if self.verify:
                    code, response = self.__checkDomain(domain, user)
                else:
                    code, response = self.__checkDomain(domain)
                if code < 400:
                    expir = self.cachePositive
                elif code < 500:
                    expir = self.cacheNegative
                else:
                    expir = self.cacheNegative5xx
                self.cache.set(key, "%s:%s" % (code, response),
                               time.time() + expir)
            nr = ".".join([ x for x in str(code) ])
        except ValueError:
            log.msg("[WRN] %s: sender address in unknown format %s" %
                    (self.getId(), data[self.param]))

        return code, nr, response


    def getDbConnection(self):
        raise Exception("No connection function defined")


## FIXME: replaced by configuration with OrCheck(ListCheck, UserDomainCheck)
##     def __verifyDomain(self, domain):
##         """Check verification lists and return if address verifycation
##         should be done for this domain."""
##         while len(domain) > 0:
##             if self.verifyNever.has_key(domain):
##                 return False
##             if self.verifyAlways.has_key(domain):
##                 return True
##             if domain.find(".") != -1:
##                 domain = domain[domain.find(".")+1:]
##         return self.verifyDefault


    def __checkDomain(self, domain, user = None):
        """Check if something listening for incomming SMTP connection
        for specified domain. First try to look in cached records
        in memory, then in database and the last step is to try connect
        to MX record(s) or if none exist then A record with. If "domain"
        CNAME is found instead, the resulting name is processed as if
        it were the initial name (RFC2821, chapter 5)."""
        import smtplib
        import socket

        for mailhost in tools.getDomainMailhosts(domain):
            try:
                conn = smtplib.SMTP(mailhost)
                conn.set_debuglevel(10) # FIXME: [DBG]
                retcode, retmsg = conn.helo()
                if retcode >= 400:
                    return retcode, "Sender domain verification failed: %s" % retmsg
                retcode, retmsg = conn.mail("postmaster@%s" %
                                            socket.gethostname())
                if retcode >= 400:
                    return retcode, "Sender domain verification failed: %s" % retmsg
                if user == None:
                    retcode, retmsg = conn.rcpt("postmaster@%s" % domain)
                    if retcode >= 400:
                        return retcode, "Sender domain verification failed: %s" % retmsg
                else:
                    retcode, retmsg = conn.rcpt("%s@%s" % (user, domain))
                    if retcode >= 400:
                        return retcode, "Sender verification failed: %s" % retmsg
                retcode, retmsg = conn.rset()
                conn.quit()
                conn.close()
                return 250, "Sender domain verification success"
##             SMTPRecipientsRefused
##             SMTPAuthenticationError
##             SMTPConnectError
##             SMTPDataError
##             SMTPHeloError
##             SMTPSenderRefused
##             SMTPResponseException
##             SMTPServerDisconnected
            except smtplib.SMTPException, err:
                log.msg("[WRN] %s: SMTP connection to %s failed: %s" %
                        (self.getId(), domain, str(err)))

        return 450, "Sender domain verirication failed."



class FakeFactory:
    def getDbConnection(self):
        import MySQLdb

        conn = None
        try:
            conn = MySQLdb.connect(host = "localhost",
                                   db = "ppolicy",
                                   user = "ppolicy",
                                   passwd = "ppolicy")
        except MySQLdb.Error, e:
            print "Error %d: %s" % (e.args[0], e.args[1])

        return conn



if __name__ == "__main__":
    print "Module tests:"
    import sys, traceback
    log.startLogging(sys.stdout)
    data = { 'request': 'smtpd_access_policy',
             'protocol_state': 'RCPT',
             'protocol_name': 'SMTP',
             'helo_name': 'mailgw1.fjfi.cvut.cz',
             'queue_id': '8045F2AB23',
             'sender': 'vokac@kmlinux.fjfi.cvut.cz',
             'recipient': 'vokac@linux.fjfi.cvut.cz',
             'client_address': '147.32.9.3',
             'client_name': 'mailgw1.fjfi.cvut.cz',
             'reverse_client_name': 'mailgw1.fjfi.cvut.cz',
             'instance': '123.456.7',
             'sasl_method': 'plain',
             'sasl_username': 'you',
             'sasl_sender': '',
             'ccert_subject': '???',
             'ccert_issuer': '???',
             'ccert_fingerprint': '???',
             'size': '12345' }
    for checkClass in [ PPolicyServerCheckBase, DummyCheck, PassCheck,
                        FailCheck, AndCheck, OrCheck, NotCheck, IfCheck,
                        If3Check, ListCheck, SPFCheck, UserDomainCheck ]:
        check = checkClass(debug=True)
        print check.getId()
        try:
            check.doStartInt(factory=FakeFactory())
            # check.doStart()
            print check.doCheckInt(data)
            check.doStopInt()
        except Exception, err:
            print "ERROR: %s" % str(err)
            print traceback.print_exc()

    dummyCheck = DummyCheck(debug=True)
    dummyCheck.doStartInt(factory=FakeFactory())
    passCheck = PassCheck(debug=True)
    passCheck.doStartInt(factory=FakeFactory())
    pass2xxCheck = PassCheck(debug=True, code=234, response="pass2xx")
    pass2xxCheck.doStartInt(factory=FakeFactory())
    failCheck = FailCheck(debug=True)
    failCheck.doStartInt(factory=FakeFactory())
    fail4xxCheck = FailCheck(debug=True, code=432, response="fail4xx")
    fail4xxCheck.doStartInt(factory=FakeFactory())
    fail5xxCheck = FailCheck(debug=True, code=543, response="fail5xx")
    fail4xxCheck.doStartInt(factory=FakeFactory())

    print ">>> AND <<<"
    test1AndCheck = AndCheck(debug=True, checks=[ passCheck, passCheck ])
    test1AndCheck.doStartInt(factory=FakeFactory())
    print test1AndCheck.doCheckInt(data)
    test2AndCheck = AndCheck(debug=True, checks=[ passCheck, failCheck ])
    test2AndCheck.doStartInt(factory=FakeFactory())
    print test2AndCheck.doCheckInt(data)

    print ">>> OR <<<"
    test1OrCheck = OrCheck(debug=True, checks=[ failCheck, failCheck ])
    test1OrCheck.doStartInt(factory=FakeFactory())
    print test1OrCheck.doCheckInt(data)
    test2OrCheck = OrCheck(debug=True, checks=[ passCheck, failCheck ])
    test2OrCheck.doStartInt(factory=FakeFactory())
    print test2OrCheck.doCheckInt(data)

    print ">>> NOT <<<"
    test1NotCheck = NotCheck(debug=True, check=passCheck)
    test1NotCheck.doStartInt(factory=FakeFactory())
    print test1NotCheck.doCheckInt(data)
    test2NotCheck = NotCheck(debug=True, check=failCheck)
    test2NotCheck.doStartInt(factory=FakeFactory())
    print test2NotCheck.doCheckInt(data)

    print ">>> IF <<<"
    test1IfCheck = IfCheck(debug=True, ifCheck=passCheck)
    test1IfCheck.doStartInt(factory=FakeFactory())
    print test1IfCheck.doCheckInt(data)
    test2IfCheck = IfCheck(debug=True, ifCheck=failCheck)
    test2IfCheck.doStartInt(factory=FakeFactory())
    print test2IfCheck.doCheckInt(data)
    test3IfCheck = IfCheck(debug=True, ifCheck=passCheck, passCheck=passCheck,
                           failCheck=failCheck)
    test3IfCheck.doStartInt(factory=FakeFactory())
    print test3IfCheck.doCheckInt(data)
    test4IfCheck = IfCheck(debug=True, ifCheck=failCheck, passCheck=passCheck,
                           failCheck=failCheck)
    test4IfCheck.doStartInt(factory=FakeFactory())
    print test4IfCheck.doCheckInt(data)

    print ">>> IF3 <<<"
    test1If3Check = If3Check(debug=True, ifCheck=passCheck)
    test1If3Check.doStartInt(factory=FakeFactory())
    print test1If3Check.doCheckInt(data)
    test2If3Check = If3Check(debug=True, ifCheck=failCheck)
    test2If3Check.doStartInt(factory=FakeFactory())
    print test2If3Check.doCheckInt(data)
    test3If3Check = If3Check(debug=True, ifCheck=passCheck,
                             passCheck=passCheck, failCheck=failCheck,
                             dunnoCheck=dummyCheck)
    test3If3Check.doStartInt(factory=FakeFactory())
    print test3If3Check.doCheckInt(data)
    test4If3Check = If3Check(debug=True, ifCheck=failCheck,
                             passCheck=passCheck, failCheck=failCheck,
                             dunnoCheck=dummyCheck)
    test4If3Check.doStartInt(factory=FakeFactory())
    print test4If3Check.doCheckInt(data)
    test5If3Check = If3Check(debug=True, ifCheck=None,
                             passCheck=passCheck, failCheck=failCheck,
                             dunnoCheck=dummyCheck)
    test5If3Check.doStartInt(factory=FakeFactory())
    print test5If3Check.doCheckInt(data)

