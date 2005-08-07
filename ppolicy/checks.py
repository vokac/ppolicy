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
        of action and actionEx according Postfix access specification.
        example: dunno, None
                 permit, None
                 OK, None
                 450, '4.5.1 Temporary failed'
                 550, '5.0.7 Sender not permitted'
                 ...
        """



class PPolicyServerCheckBase:
    """Base class for postfix policy check modules.

    Parameters:
      debug
        set debug level: 0 - quiet, 1 - verbose (default: 0)
      defaultAction
      defaultActionEx
        default result if something went wrong (default: 'DUNNO', None)
      cacheResult
        use result cache (default: True)
      cacheResultLifetime
        number of seconds for caching results for data hash (default: 600)
      cacheResultSize
        maximum records in cache (default: 1000)
    """

    __implements__ = (IPPolicyServerCheck, )


    def __init__(self, *args, **keywords):
        self.id = self.__class__.__name__
        self._stateLock = threading.Lock()
        self._state = 'initializing'
        self.factory = None
        self.debug = getattr(self, 'debug', 0)
        self.defaultAction = getattr(self, 'defaultAction', 'DUNNO')
        self.defaultActionEx = getattr(self, 'defaultActionEx', None)
        self.cacheResult = getattr(self, 'cacheResult', True)
        self.cacheResultLifetime = getattr(self, 'cacheResultLifetime', 600)
        self.cacheResultSize = getattr(self, 'cacheResultSize', 1000)
        self.cacheResultLock = threading.Lock()
        self.cacheResultData = {}
        self.cacheResultExpire = {}
        self.cacheResultCheckInterval = 150
        self.setParams(*args, **keywords)
        self.setState('init')


    def getId(self):
        """get module identification."""
        return self.id


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        self.debug = keywords.get('debug', self.debug)
        self.defaultAction = keywords.get('defaultAction', self.defaultAction)
        self.defaultActionEx = keywords.get('defaultActionEx', self.defaultActionEx)
        self.cacheResult = keywords.get('cacheResult', self.cacheResult)
        self.cacheResultLifetime = keywords.get('cacheResultLifetime', self.cacheResultLifetime)
        self.cacheResultSize = keywords.get('cacheResultSize', self.cacheResultSize)
        self.cacheResultCheckTime = time.time()
        self.setState(lastState)


    def dataHash(self, data):
        """Compute hash from data which is then used as index
        to the result cache. Changing this function in subclasses
        and using only required fields for hash can improve cache
        usage and performance."""
        keys = sorted(data.keys())
        return hash("\n".join([ "=".join([x, data[x]]) for x in keys ]))


    def getState(self):
        return self._state


    def setState(self, state, *args, **keywords):
        self._stateLock.acquire()

        try:
            lastState = self._state
            if self._state == state:
                return
            if self._state == 'ready' and state == 'start':
                return
            if self._state != 'ready' and state == 'start':
                self._state = 'starting'
                self.__cleanCacheResult(True)
                self.doStart(*args, **keywords)
                self._state = 'ready'
            elif self._state == 'ready' and state == 'stop':
                self._state = 'stopping'
                self.doStop(*args, **keywords)
                self._state = 'stopped'
            elif state == 'restart':
                if self._state == 'ready':
                    self._state = 'stopping'
                    self.doStop(*args, **keywords)
                    self._state = 'stopped'
                self._state = 'starting'
                self.doStart(*args, **keywords)
                self._state = 'ready'
            else:
                self._state = state
        finally:
            self._stateLock.release()

        return lastState


    def doStartInt(self, *args, **keywords):
        """Called by protocol factory once before doCheck is used."""
        self.setState('start', *args, **keywords)


    def doStart(self, *args, **keywords):
        """Called when changing state to 'ready'."""
        pass


    def doStopInt(self, *args, **keywords):
        """Called by protocol factory before shutdown."""
        self.setState('stop', *args, **keywords)


    def doStop(self, *args, **keywords):
        """Called when changing state to 'stopped'."""
        pass


    def doRestartInt(self, *args, **keywords):
        """Restart module/reload new configuration."""
        self.setState('restart', *args, **keywords)


    def doCheckInt(self, data):
        """This method will ensure check result caching and should not
        be redefined. User checking should be implemented in doCheck
        method called by this method in case of no cached data available."""
        if self._state != 'ready':
            return self.defaultAction, self.defaultActionEx

        dataHash = self.dataHash(data)
        if self.cacheResult:
            action, actionEx = self.__getCacheResult(dataHash)
            if action != None:
                log.msg("[DBG] %s: result cache hit" % self.getId())
                return action, actionEx
        action, actionEx = self.doCheck(data)
        if self.cacheResult:
            self.__addCacheResult(dataHash, action, actionEx)
        return action, actionEx


    def doCheck(self, data):
        """This method will be called according configuration to
        check input data. If chaching is enabled (default) it will
        be called only if actionEx for requested data is not in cache.
        This method has to be implemented in child classes."""
        raise NotImplementedException("Don't call base class directly")


    def __addCacheResult(self, dataHash, action, actionEx):
        """Add new result to the cache."""
        if dataHash != 0:
            self.__cleanCacheResult()
            self.cacheResultLock.acquire()
            try:
                self.cacheResultExpire[dataHash] = time.time() \
                                                    + self.cacheResultLifetime
                self.cacheResultData[dataHash] = (action, actionEx)
            finally:
                self.cacheResultLock.release()


    def __getCacheResult(self, dataHash):
        """Get result from the cache."""
        action, actionEx = (None, None)
        if dataHash != 0:
            self.cacheResultLock.acquire()
            try:
                if self.cacheResultData.has_key(dataHash) and self.cacheResultExpire[dataHash] >= time.time():
                    action, actionEx = self.cacheResultData[dataHash]
            finally:
                self.cacheResultLock.release()
        return action, actionEx


    def __cleanCacheResult(self, all = False):
        """Expired cache records cleanup."""
        self.cacheResultLock.acquire()
        try:
            if all:
                self.cacheResultExpire = {}
                self.cacheResultData = {}
            elif self.cacheResult:
                toDel = []
##                 if self.cacheResultCheckTime <= time.time():
##                     self.cacheResultCheckTime = time.time() + self.cacheResultCheckInterval
##                     for key in self.cacheResultExpire.keys():
##                         if self.cacheResultExpire[key] <= time.time():
##                             toDel.append(key)

##                 if len(self.cacheResultExpire) - len(toDel) > 19 * self.cacheResultSize / 20:
                if self.cacheResultSize <= len(self.cacheResultExpire):

##                     toDel = [] # this automatically include all expired
                    expVal = sorted(self.cacheResultExpire.values())
                    trh = expVal[len(expVal)/2]
                    for expKey in self.cacheResultExpire.keys():
                        if self.cacheResultExpire[expKey] <= trh:
                            toDel.append(expKey)    

                if len(toDel) > 0:
                    log.msg("[DBG] %s: result cache cleanup (%s from %s items)" %
                            (self.getId(), len(toDel), len(self.cacheResultExpire)))

                    for key in toDel:
                        del(self.cacheResultExpire[key])
                        del(self.cacheResultData[key])
        finally:
            self.cacheResultLock.release()



class DummyCheck(PPolicyServerCheckBase):
    """Dummy check module for testing."""


    def __init__(self, *args, **keywords):
        PPolicyServerCheckBase.__init__(self, *args, **keywords)


    #def getId(self):
    #    return self.id


    #def setParams(self, *args, **keywords):
    #    lastState = self.setState('stop')
    #    PPolicyServerCheckBase.setParams(self, *args, **keywords)
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
        return 'DUNNO', None



class SimpleCheck(PPolicyServerCheckBase):
    """Check module that returns exactly what it get
    as constructor parameters.

    Parameters:
      action:
        return action (default: None)
      actionEx:
        return actionEx string (default: None)
    """


    def __init__(self, *args, **keywords):
        self.cacheResult = getattr(self, 'cacheResult', False)
        self.action = getattr(self, 'action', None)
        self.actionEx = getattr(self, 'actionEx', None)
        PPolicyServerCheckBase.__init__(self, *args, **keywords)


    def setParams(self, *args, **keywords):
        PPolicyServerCheckBase.setParams(self, *args, **keywords)
        self.action = keywords.get('action', self.action)
        self.actionEx = keywords.get('actionEx', self.actionEx)


    def dataHash(self, data):
        return 0


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())

        if self.action == None:
            action = 'DUNNO'
        else:
            action = self.action

        if self.actionEx == None:
            actionEx = None
        else:
            actionEx = tools.safeSubstitute(self.actionEx, data)

        return action, actionEx



class OkCheck(SimpleCheck):
    """Check module that return OK."""

    def __init__(self, *args, **keywords):
        self.action = 'OK'
        SimpleCheck.__init__(self, *args, **keywords)


class Reject4xxCheck(SimpleCheck):
    """Check module that return 4xx."""

    def __init__(self, *args, **keywords):
        self.action = '450'
        self.actionEx = 'temporary failure'
        SimpleCheck.__init__(self, *args, **keywords)


class Reject5xxCheck(SimpleCheck):
    """Check module that return 5xx."""

    def __init__(self, *args, **keywords):
        self.action = '550'
        self.actionEx = 'pernament failure'
        SimpleCheck.__init__(self, *args, **keywords)


class RejectCheck(SimpleCheck):
    """Check module that return REJECT."""

    def __init__(self, *args, **keywords):
        self.action = 'REJECT'
        self.actionEx = 'reject'
        SimpleCheck.__init__(self, *args, **keywords)


class DeferIfRejectCheck(SimpleCheck):
    """Check module that return DEFER_IF_REJECT."""

    def __init__(self, *args, **keywords):
        self.action = 'DEFER_IF_REJECT'
        SimpleCheck.__init__(self, *args, **keywords)


class DeferIfPermitCheck(SimpleCheck):
    """Check module that return DEFER_IF_PERMIT."""

    def __init__(self, *args, **keywords):
        self.action = 'DEFER_IF_PERMIT'
        SimpleCheck.__init__(self, *args, **keywords)


class DiscardCheck(SimpleCheck):
    """Check module that return DISCARD."""

    def __init__(self, *args, **keywords):
        self.action = 'DISCARD'
        SimpleCheck.__init__(self, *args, **keywords)


class DunnoCheck(SimpleCheck):
    """Check module that return DUNNO."""

    def __init__(self, *args, **keywords):
        self.action = 'DUNNO'
        SimpleCheck.__init__(self, *args, **keywords)


class FilterCheck(SimpleCheck):
    """Check module that return FILTER."""

    def __init__(self, *args, **keywords):
        self.action = 'FILTER'
        SimpleCheck.__init__(self, *args, **keywords)


class HoldCheck(SimpleCheck):
    """Check module that return HOLD."""

    def __init__(self, *args, **keywords):
        self.action = 'HOLD'
        SimpleCheck.__init__(self, *args, **keywords)


class PrependCheck(SimpleCheck):
    """Check module that return PREPEND."""

    def __init__(self, *args, **keywords):
        self.action = 'PREPEND'
        SimpleCheck.__init__(self, *args, **keywords)


class RedirectCheck(SimpleCheck):
    """Check module that return REDIRECT."""

    def __init__(self, *args, **keywords):
        self.action = 'REDIRECT'
        SimpleCheck.__init__(self, *args, **keywords)


class WarnCheck(SimpleCheck):
    """Check module that return WARN."""

    def __init__(self, *args, **keywords):
        self.action = 'WARN'
        SimpleCheck.__init__(self, *args, **keywords)



class LogicCheck(PPolicyServerCheckBase):
    """Base class for logical operations and conditions between
    some group of check modules.
    """

    def __init__(self, *args, **keywords):
        PPolicyServerCheckBase.__init__(self, *args, **keywords)


    def getLogicValue(self, action):
        action = action.lower()
        if len(action) == 3:
            if action[0] == '4': action = '4xx'
            elif action[0] == '5': action = '5xx'
        if action in [ 'ok', 'permit' ]:
            return True
        elif action in [ 'reject', '4xx', '5xx' ]:
            return False
        else:
            return None


class AndCheck(LogicCheck):
    """Run defined checks and join result with logical AND.

    --------+-------+-------+-------+
    | AND   | TRUE  | FALSE | DUNNO |
    +-------+-------+-------+-------+
    | TRUE  | TRUE  | FALSE | DUNNO |
    +-------+-------+-------+-------+
    | FALSE | FALSE | FALSE | FALSE |
    +-------+-------+-------+-------+
    | DUNNO | DUNNO | FALSE | DUNNO |
    +-------+-------+-------+-------+

    Parameters:
      checks
        array of "check" class instances (default: [])
    """


    def __init__(self, *args, **keywords):
        self.checks = []
        LogicCheck.__init__(self, *args, **keywords)


    def getId(self):
        checks = ",".join(map(lambda x: x.getId(), self.checks))
        return "%s(%s)" % (self.id, checks)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        LogicCheck.setParams(self, *args, **keywords)
        self.checks = keywords.get('checks', self.checks)
        self.setState(lastState)


    def doStart(self, *args, **keywords):
        for check in self.checks:
            check.doStartInt(*args, **keywords)


    def doStop(self, *args, **keywords):
        for check in self.checks:
            check.doStopInt(*args, **keywords)


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())

        if self.checks == []:
            log.msg("[WRN] %s: no check defined" % self.getId())
            return 'DUNNO', None

        dunno = False
        for check in self.checks:
            action, actionEx = check.doCheckInt(data)
            logic = self.getLogicValue(action)
            if logic == None:
                dunno = True
            elif not logic:
                return action, actionEx

        if dunno:
            return 'DUNNO', None
        else:
            return 'OK', "%s all ok" % self.getId()



class OrCheck(LogicCheck):
    """Run defined checks and join result with logical OR.

    --------+-------+-------+-------+
    | OR    | TRUE  | FALSE | DUNNO |
    +-------+-------+-------+-------+
    | TRUE  | TRUE  | TRUE  | TRUE  |
    +-------+-------+-------+-------+
    | FALSE | TRUE  | FALSE | DUNNO |
    +-------+-------+-------+-------+
    | DUNNO | TRUE  | DUNNO | DUNNO |
    +-------+-------+-------+-------+

    Parameters:
      checks
        array of "check" class instances (default: [])
    """


    def __init__(self, *args, **keywords):
        self.checks = []
        LogicCheck.__init__(self, *args, **keywords)


    def getId(self):
        checks = ",".join(map(lambda x: x.getId(), self.checks))
        return "%s(%s)" % (self.id, checks)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        LogicCheck.setParams(self, *args, **keywords)
        self.checks = keywords.get('checks', self.checks)
        self.setState(lastState)


    def doStart(self, *args, **keywords):
        for check in self.checks:
            check.doStartInt(*args, **keywords)


    def doStop(self, *args, **keywords):
        for check in self.checks:
            check.doStopInt(*args, **keywords)


    def doCheck(self, data):

        log.msg("[DBG] %s: running check" % self.getId())

        if self.checks == []:
            log.msg("[WRN] %s: no check defined" % self.getId())
            return 'DUNNO', None

        dunno = False
        for check in self.checks:
            action, actionEx = check.doCheckInt(data)
            logic = self.getLogicValue(action)
            if logic == None:
                dunno = True
            elif logic:
                return action, actionEx

        if dunno:
            return 'DUNNO', None
        else:
            return 'REJECT', "%s all failed" % self.getId()



class NotCheck(LogicCheck):
    """Run defined check and on result apply logical NOT.

    --------+-------+-------+-------+
    | NOT   | TRUE  | FALSE | DUNNO |
    +-------+-------+-------+-------+
    |       | FALSE | TRUE  | DUNNO |
    +-------+-------+-------+-------+

    Parameters:
      check
        "check" class instance (default: None)
    """


    def __init__(self, *args, **keywords):
        self.check = None
        LogicCheck.__init__(self, *args, **keywords)


    def getId(self):
        if self.check != None:
            return "%s(%s)" % (self.id, self.check.getId())
        else:
            return "%s(NDEF)" % self.id


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        LogicCheck.setParams(self, *args, **keywords)
        self.check = keywords.get('check', self.check)
        self.setState(lastState)


    def doStart(self, *args, **keywords):
        if self.check != None:
            self.check.doStartInt(*args, **keywords)


    def doStop(self, *args, **keywords):
        if self.check != None:
            self.check.doStopInt(*args, **keywords)


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())

        if self.check == None:
            log.msg("[WRN] %s: no check defined" % self.getId())
            return 'DUNNO', None

        action, actionEx = self.check.doCheckInt(data)
        logic = self.getLogicValue(action)
        if logic == None:
            return 'DUNNO', None
        elif logic:
            return 'OK', "%s ok" % self.getId()
        else:
            return 'REJECT', "%s failed" % self.getId()



class IfCheck(LogicCheck):
    """Run check and according result run first (ok) or second (reject)
    check. It provide IF functionality for module configuration. If some
    error occurs than it returns 'DUNNO'

    Parameters:
      ifCheck
        "check" class instance, result used as condition
        which check should be called (default: None)
      okCheck
        "check" class instance called when ifCheck succeed (default: None)
      rejectCheck
        "check" class instance called when ifCheck fail (default: None)
    """


    def __init__(self, *args, **keywords):
        self.ifCheck = None
        self.okCheck = None
        self.rejectCheck = None
        LogicCheck.__init__(self, *args, **keywords)


    def getId(self):
        if self.ifCheck != None:
            ifCheck = self.ifCheck.getId()
        else:
            ifCheck = "NDEF"
        if self.okCheck != None:
            okCheck = self.okCheck.getId()
        else:
            okCheck = "NDEF"
        if self.rejectCheck != None:
            rejectCheck = self.rejectCheck.getId()
        else:
            rejectCheck = "NDEF"
        return "%s(%s?%s:%s)" % (self.id, ifCheck, okCheck, rejectCheck)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        LogicCheck.setParams(self, *args, **keywords)
        self.ifCheck = keywords.get('ifCheck', self.ifCheck)
        self.okCheck = keywords.get('okCheck', self.okCheck)
        self.rejectCheck = keywords.get('rejectCheck', self.rejectCheck)
        self.setState(lastState)


    def doStart(self, *args, **keywords):
        if self.ifCheck != None:
            self.ifCheck.doStartInt(*args, **keywords)
        if self.okCheck != None:
            self.okCheck.doStartInt(*args, **keywords)
        if self.rejectCheck != None:
            self.rejectCheck.doStartInt(*args, **keywords)


    def doStop(self, *args, **keywords):
        if self.ifCheck != None:
            self.ifCheck.doStopInt(*args, **keywords)
        if self.okCheck != None:
            self.okCheck.doStopInt(*args, **keywords)
        if self.rejectCheck != None:
            self.rejectCheck.doStopInt(*args, **keywords)


    def doCheck(self, data):

        log.msg("[DBG] %s: running check" % self.getId())

        if self.ifCheck == None:
            log.msg("[WRN] %s: no ifCheck defined" % self.getId())
            return 'DUNNO', None

        action, actionEx = self.ifCheck.doCheckInt(data)

        logic = self.getLogicValue(action)
        if logic == None:
            return action, actionEx

        if logic:
            check = self.okCheck
        else:
            check = self.rejectCheck

        if check == None:
            log.msg("[WRN] %s: no check defined for result %s" %
                    (self.getId(), action))
            return 'DUNNO', None

        return check.doCheckInt(data)



class If3Check(LogicCheck):
    """Run check and according result run first (ok), second (reject)
    or third (dunno) check. It provide three state IF functionality
    for module configuration.

    Parameters:
      ifCheck
        "check" class instance, result used as condition
        which check should be called (default: None)
      okCheck
        "check" class instance called when ifCheck succeed (default: None)
      rejectCheck
        "check" class instance called when ifCheck fail (default: None)
      dunnoCheck
        "check" class instance called when ifCheck return dunno (default: None)
    """

    def __init__(self, *args, **keywords):
        self.ifCheck = None
        self.okCheck = None
        self.rejectCheck = None
        self.dunnoCheck = None
        LogicCheck.__init__(self, *args, **keywords)


    def getId(self):
        if self.ifCheck != None:
            ifCheck = self.ifCheck.getId()
        else:
            ifCheck = "NDEF"
        if self.okCheck != None:
            okCheck = self.okCheck.getId()
        else:
            okCheck = "NDEF"
        if self.rejectCheck != None:
            rejectCheck = self.rejectCheck.getId()
        else:
            rejectCheck = "NDEF"
        if self.dunnoCheck != None:
            dunnoCheck = self.dunnoCheck.getId()
        else:
            dunnoCheck = "NDEF"
        return "%s(%s?%s:%s:%s)" % (self.id, ifCheck, okCheck,
                                    rejectCheck, dunnoCheck)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        LogicCheck.setParams(self, *args, **keywords)
        self.ifCheck = keywords.get('ifCheck', self.ifCheck)
        self.okCheck = keywords.get('okCheck', self.okCheck)
        self.rejectCheck = keywords.get('rejectCheck', self.rejectCheck)
        self.dunnoCheck = keywords.get('dunnoCheck', self.dunnoCheck)
        self.setState(lastState)


    def doStart(self, *args, **keywords):
        if self.ifCheck != None:
            self.ifCheck.doStartInt(*args, **keywords)
        if self.okCheck != None:
            self.okCheck.doStartInt(*args, **keywords)
        if self.rejectCheck != None:
            self.rejectCheck.doStartInt(*args, **keywords)
        if self.dunnoCheck != None:
            self.dunnoCheck.doStartInt(*args, **keywords)


    def doStop(self, *args, **keywords):
        if self.ifCheck != None:
            self.ifCheck.doStopInt(*args, **keywords)
        if self.okCheck != None:
            self.okCheck.doStopInt(*args, **keywords)
        if self.rejectCheck != None:
            self.rejectCheck.doStopInt(*args, **keywords)
        if self.dunnoCheck != None:
            self.dunnoCheck.doStopInt(*args, **keywords)


    def doCheck(self, data):

        log.msg("[DBG] %s: running check" % self.getId())

        if self.ifCheck == None:
            log.msg("[WRN] %s: no ifCheck defined" % self.getId())
            return 'DUNNO', None

        action, actionEx = self.ifCheck.doCheckInt(data)

        logic = self.getLogicValue(action)
        if logic == None:
            check = self.dunnoCheck
        elif logic:
            check = self.okCheck
        else:
            check = self.rejectCheck

        if check == None:
            log.msg("[WRN] %s: no check defined for result %s" %
                    (self.getId(), action))
            return 'DUNNO', None

        return check.doCheckInt(data)



class SwitchCheck(LogicCheck):
    """Run check and according result run another one. It use return action
    as parameter for "switch" command. You can specify different check
    for each action.

    Parameters:
      switchCheck
        "check" class instance, result used as condition
        which check should be called (default: None)
      caseChecks
        dictionary of action and "check" class instances (default: {})
        for all 4xx resp. 5xx codes you can use key 4xx resp. 5xx
    """


    def __init__(self, *args, **keywords):
        self.switchCheck = None
        self.caseChecks = {}
        LogicCheck.__init__(self, *args, **keywords)


    def getId(self):
        if self.switchCheck != None:
            switchCheck = self.switchCheck.getId()
        else:
            switchCheck = "NDEF"
        caseChecks = []
        for action, check in self.caseChecks.items():
            caseChecks.append("%s=%s" % (action, check.getId()))
        return "%s(%s?%s)" % (self.id, switchCheck, ",".join(caseChecks))


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        LogicCheck.setParams(self, *args, **keywords)
        self.switchCheck = keywords.get('switchCheck', self.switchCheck)
        self.caseChecks = keywords.get('caseChecks', self.caseChecks)
        self.setState(lastState)


    def doStart(self, *args, **keywords):
        if self.switchCheck != None:
            self.switchCheck.doStartInt(*args, **keywords)
        for check in self.caseChecks.values():
            check.doStartInt(*args, **keywords)


    def doStop(self, *args, **keywords):
        if self.switchCheck != None:
            self.switchCheck.doStopInt(*args, **keywords)
        for check in self.caseChecks.values():
            check.doStopInt(*args, **keywords)


    def doCheck(self, data):

        log.msg("[DBG] %s: running check" % self.getId())

        if self.switchCheck == None:
            log.msg("[WRN] %s: no switchCheck defined" % self.getId())
            return 'DUNNO', None

        action, actionEx = self.switchCheck.doCheckInt(data)

        check = None
        if self.caseChecks.has_key(action):
            check = self.caseChecks[action]
        else:
            action = action.lower()
            if len(action) == 3:
                if action[0] == '4': action = '4xx'
                elif action[0] == '5': action = '5xx'
            if self.caseChecks.has_key(action):
                check = self.caseChecks[action]

        if check == None:
            log.msg("[WRN] %s: no check defined for result %s" %
                    (self.getId(), action))
            return 'DUNNO', None

        return check.doCheckInt(data)



class ListCheck(PPolicyServerCheckBase):
    """Check if item is in specified list and return corresponding
    action, actionEx.

    Parameters:
      param
        which parameter from data received from postfix should be used
        (default: None)
      paramFunction
        function which will be called on param data. It can be used to
        separate user from domain in email address, ... Its return has
        to be array of strins and each will be checked with white/black
        list. (default: None)
      table
        database table with whitelist (default: None)
      cols
        dictionary { 'name': 'name',
                     'action': 'action',
                     'actionEx': 'actionEx' }
      cacheSize
        memory cache size, for best performance should be 0 - means
        load all records in memory (default: 0)
    """


    def __init__(self, *args, **keywords):
        self.param = None
        self.paramFunction = None
        self.table = None
        self.cols = { 'name': 'name',
                      'action': 'action',
                      'actionEx': 'actionEx' }
        self.cacheSize = 0
        self.cache = None
        PPolicyServerCheckBase.__init__(self, *args, **keywords)


    def getId(self):
        return "%s[%s]" % (self.id, self.table)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        PPolicyServerCheckBase.setParams(self, *args, **keywords)
        self.param = keywords.get('param', self.param)
        self.paramFunction = keywords.get('paramFunction', self.paramFunction)
        self.table = keywords.get('table', self.table)
        self.cols =keywords.get('cols', self.cols)
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
        self.cache = tools.DbMemListCache(self, self.table, self.cols,
                                          self.cacheSize)


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())

        if self.param == None:
            return self.defaultAction, self.defaultActionEx

        if self.paramFunction == None:
            testDataArr = [ data.get(self.param) ]
        else:
            testDataArr = self.paramFunction(data.get(self.param))

        if testDataArr in [ None, [], [ None ] ]:
            log.msg("[WRN] %s: no test data for %s" %
                    (self.getId(), self.param))
            return 'DUNNO', None

        for testData in testDataArr:
            action, actionEx = self.cache.get(testData)
            if action == None:
                return 'DUNNO', None
            else:
                return action, actionEx

        return self.defaultAction, self.defaultActionEx


    def getDbConnection(self):
        raise Exception("No connection function defined")



class ListWBCheck(PPolicyServerCheckBase):
    """Check if item is in specified black/white list. Together
    with IfCheck it can be used to check only some user/domain/...
    with further modules.

    Parameters:
      param
        which parameter from data received from postfix should be used
        (default: None)
      paramFunction
        function which will be called on param data. It can be used to
        separate user from domain in email address, ... Its return has
        to be array of strins and each will be checked with white/black
        list. (default: None)
      whitelistTable
        database table with whitelist (default: None)
      whitelistColumn
        table column for data lookup (default: 'name')
      blacklistTable
        database table with blacklist (default: None)
      blacklistColumn
        table column for data lookup (default: 'name')
      cacheSize
        memory cache size, for best performance should be 0 - means
        load all records in memory (default: 0)
    """


    def __init__(self, *args, **keywords):
        self.param = None
        self.paramFunction = None
        self.whitelistTable = None
        self.whitelistColumn = 'name'
        self.blacklistTable = None
        self.blacklistColumn = 'name'
        self.cacheSize = 0
        self.cache = None
        PPolicyServerCheckBase.__init__(self, *args, **keywords)


    def getId(self):
        return "%s[%s,%s]" % (self.id, self.whitelistTable,
                              self.blacklistTable)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        PPolicyServerCheckBase.setParams(self, *args, **keywords)
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
        self.cache = tools.DbMemListWBCache(self,
                                            self.whitelistTable,
                                            self.whitelistColumn,
                                            self.blacklistTable,
                                            self.blacklistColumn,
                                            self.cacheSize)


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())

        if self.param == None:
            return self.defaultAction, self.defaultActionEx

        if self.paramFunction == None:
            testDataArr = [ data.get(self.param) ]
        else:
            testDataArr = self.paramFunction(data.get(self.param))

        if testDataArr in [ None, [], [ None ] ]:
            log.msg("[WRN] %s: no test data for %s" %
                    (self.getId(), self.param))
            return 'DUNNO', None

        for testData in testDataArr:
            if self.__isInWhitelist(testData):
                return 'OK', "%s %s is on whitelist" % (self.param, testData)
            if self.__isInBlacklist(testData):
                return 'REJECT', "%s %s is on blacklist" % (self.param, testData)

        return self.defaultAction, self.defaultActionEx


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
    know what you are doing...

    Parameters:
      restrictive
        very strict SPF checking, be very carefull setting
        this option to True (default: False)
    """


    def __init__(self, *args, **keywords):
        self.restrictive = False
        PPolicyServerCheckBase.__init__(self, *args, **keywords)


    def setParams(self, *args, **keywords):
        """set 'restrictive' SPF checking and call base class
        L{PPolicyServer.PPolicyServerBase.setParams}
        restrictive:
          False ... passive, Unknown Querys are permitted (default)
          True  ... restrictive, Unknown Querys are denyed
        """
        lastState = self.setState('stop')
        PPolicyServerCheckBase.setParams(self, *args, **keywords)
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
            result, mtastatus, mtaexpl = spf.check(i=client_address,
                                                   s=sender, h=client_name)
            log.msg("[DBG] %s: result: %s, %s, %s" %
                    (self.getId(), result, mtastatus, mtaexpl))
        except Exception, error:
            log.msg("[ERR] %s: checking SPF failed: %s" %
                    (self.getId(), str(error)))
            return 'DUNNO', None

        if self.restrictive:
            if result.lower() == 'unknown':
                return 'REJECT', '5.5.7 SPF Policy violation'
            else:
                return 'OK', mtaexpl
        else:
            if result.lower() != 'deny':
                return 'OK', '2.5.0 SPF Policy success'
            else:
                return 'REJECT', mtaexpl



class UserDomainCheck(PPolicyServerCheckBase):
    """Check if sender/recipient mailserver is reachable. It provide
    also sender/recipient verification if "verify" parameter is set
    to True (default is False). Be carefull when turning on verification
    and first read http://www.postfix.org/ADDRESS_VERIFICATION_README.html
    about its limitation

    Parameters:
      param
        string key for data item that should be verified (default: None)
      verify
        verify user, not only domain mailserver (default: False)
      cacheTable
        database table name for caching data (default: None)
      cacheCols
        dictionary { 'key': 'name',
                     'res': 'result',
                     'exp': 'expire' }
      cachePositive
        expiration time sucessfully verified records (default: month)
      cacheNegative
        expiration time if verification fail (def: 4 hours)
      cacheNegative5xx
        expiration time if verification fail with code 5xx (def: 2 days)
      cacheSize
        max number of records in memory cache (default: 0 - all records)
    """


    def __init__(self, *args, **keywords):
        self.param = None
        self.verify = False
        self.cacheTable = None
        self.cacheCols = { 'key': 'name', 'res': 'result', 'exp': 'expire' }
        self.cachePositive = 60*60*24*31    # month
        self.cacheNegative = 60*60*4        # 4 hours
        self.cacheNegative5xx = 60*60*24*2  # 2 days
        self.cacheSize = 0
        self.cache = None
        PPolicyServerCheckBase.__init__(self, *args, **keywords)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        PPolicyServerCheckBase.setParams(self, *args, **keywords)
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
        if self.param == None:
            return 0
        else:
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
            return self.defaultAction, self.defaultActionEx

        action = self.defaultAction
        actionEx = self.defaultActionEx

        try:
            user, domain = data[self.param].split("@")
            if self.verify:
                key = "%s@%s" % (user, domain)
            else:
                key = domain
            res = self.cache.get(key)
            if res != None:
                action = res[:res.find(":")]
                actionEx = res[res.find(":")+1:]
            else:
                if self.verify:
                    code, actionEx = self.__checkDomain(domain, user)
                else:
                    code, actionEx = self.__checkDomain(domain)
                action = str(code)
                if code < 400:
                    expire = self.cachePositive
                elif code < 500:
                    expire = self.cacheNegative
                else:
                    expire = self.cacheNegative5xx
                self.cache.set(key, "%s:%s" % (action, actionEx),
                               time.time() + expire)
        except ValueError:
            log.msg("[WRN] %s: sender address in unknown format %s" %
                    (self.getId(), data[self.param]))

        return action, actionEx


    def getDbConnection(self):
        raise Exception("No connection function defined")


    def __checkDomain(self, domain, user = None):
        """Check if something listening for incomming SMTP connection
        for specified domain. First try to look in cached records
        in memory, then in database and the last step is to try connect
        to MX record(s) or if none exist then A record. For more details
        see RFC2821, chapter 5."""
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
                if user == None:
                    return 250, "Sender domain verification success"
                else:
                    return 250, "Sender verification success"
##             SMTPRecipientsRefused
##             SMTPAuthenticationError
##             SMTPConnectError
##             SMTPDataError
##             SMTPHeloError
##             SMTPSenderRefused
##             SMTPActionExException
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
    print ">>>>>>>>>>>>>>>>>>>>>>>>> GLOBAL CHECKS - BEGIN <<<<<<<<<<<<<<<<<<<<<<<<<"
    for checkClass in [ PPolicyServerCheckBase, DummyCheck, SimpleCheck,
                        OkCheck, Reject4xxCheck, Reject5xxCheck, RejectCheck,
                        DeferIfRejectCheck, DeferIfPermitCheck, DiscardCheck,
                        DunnoCheck, FilterCheck, HoldCheck, PrependCheck,
                        RedirectCheck, WarnCheck,
                        AndCheck, OrCheck, NotCheck, IfCheck, If3Check,
                        SwitchCheck,
                        ListCheck, ListWBCheck, SPFCheck, UserDomainCheck ]:
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
    print ">>>>>>>>>>>>>>>>>>>>>>>>> GLOBAL CHECKS - END <<<<<<<<<<<<<<<<<<<<<<<<<"

    dummyCheck = DummyCheck(debug=True)
    dummyCheck.doStartInt(factory=FakeFactory())
    okCheck = OkCheck(debug=True)
    okCheck.doStartInt(factory=FakeFactory())
    rejectCheck = RejectCheck(debug=True)
    rejectCheck.doStartInt(factory=FakeFactory())
    reject4xxCheck = Reject4xxCheck(debug=True, action='456', actionEx="reject4xx")
    reject4xxCheck.doStartInt(factory=FakeFactory())
    reject5xxCheck = Reject5xxCheck(debug=True, action='543', actionEx="reject5xx")
    reject5xxCheck.doStartInt(factory=FakeFactory())

    print ">>> AND <<<"
    test1AndCheck = AndCheck(debug=True, checks=[ okCheck, okCheck ])
    test1AndCheck.doStartInt(factory=FakeFactory())
    print test1AndCheck.doCheckInt(data)
    test2AndCheck = AndCheck(debug=True, checks=[ okCheck, rejectCheck ])
    test2AndCheck.doStartInt(factory=FakeFactory())
    print test2AndCheck.doCheckInt(data)

    print ">>> OR <<<"
    test1OrCheck = OrCheck(debug=True, checks=[ rejectCheck, rejectCheck ])
    test1OrCheck.doStartInt(factory=FakeFactory())
    print test1OrCheck.doCheckInt(data)
    test2OrCheck = OrCheck(debug=True, checks=[ okCheck, rejectCheck ])
    test2OrCheck.doStartInt(factory=FakeFactory())
    print test2OrCheck.doCheckInt(data)

    print ">>> NOT <<<"
    test1NotCheck = NotCheck(debug=True, check=okCheck)
    test1NotCheck.doStartInt(factory=FakeFactory())
    print test1NotCheck.doCheckInt(data)
    test2NotCheck = NotCheck(debug=True, check=rejectCheck)
    test2NotCheck.doStartInt(factory=FakeFactory())
    print test2NotCheck.doCheckInt(data)

    print ">>> IF <<<"
    test1IfCheck = IfCheck(debug=True, ifCheck=okCheck)
    test1IfCheck.doStartInt(factory=FakeFactory())
    print test1IfCheck.doCheckInt(data)
    test2IfCheck = IfCheck(debug=True, ifCheck=rejectCheck)
    test2IfCheck.doStartInt(factory=FakeFactory())
    print test2IfCheck.doCheckInt(data)
    test3IfCheck = IfCheck(debug=True, ifCheck=okCheck, okCheck=okCheck,
                           rejectCheck=rejectCheck)
    test3IfCheck.doStartInt(factory=FakeFactory())
    print test3IfCheck.doCheckInt(data)
    test4IfCheck = IfCheck(debug=True, ifCheck=rejectCheck, okCheck=okCheck,
                           rejectCheck=rejectCheck)
    test4IfCheck.doStartInt(factory=FakeFactory())
    print test4IfCheck.doCheckInt(data)

    print ">>> IF3 <<<"
    test1If3Check = If3Check(debug=True, ifCheck=okCheck)
    test1If3Check.doStartInt(factory=FakeFactory())
    print test1If3Check.doCheckInt(data)
    test2If3Check = If3Check(debug=True, ifCheck=rejectCheck)
    test2If3Check.doStartInt(factory=FakeFactory())
    print test2If3Check.doCheckInt(data)
    test3If3Check = If3Check(debug=True, ifCheck=okCheck,
                             okCheck=okCheck, rejectCheck=rejectCheck,
                             dunnoCheck=dummyCheck)
    test3If3Check.doStartInt(factory=FakeFactory())
    print test3If3Check.doCheckInt(data)
    test4If3Check = If3Check(debug=True, ifCheck=rejectCheck,
                             okCheck=okCheck, rejectCheck=rejectCheck,
                             dunnoCheck=dummyCheck)
    test4If3Check.doStartInt(factory=FakeFactory())
    print test4If3Check.doCheckInt(data)
    test5If3Check = If3Check(debug=True, ifCheck=None,
                             okCheck=okCheck, rejectCheck=rejectCheck,
                             dunnoCheck=dummyCheck)
    test5If3Check.doStartInt(factory=FakeFactory())
    print test5If3Check.doCheckInt(data)

