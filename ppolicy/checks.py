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



class CheckError(Exception):
    """Base exception class for check modules."""
    def __init__(self, args = ""):
        Exception.__init__(self, args)


class NotImplementedError(CheckError):
    """Exception for some methods in base classes that should be implemented
    in derived classes."""
    def __init__(self, args = ""):
        CheckError.__init__(self, args)


class ParamError(CheckError):
    """Error when setting module parameters. Used when required parametr
    is not specified."""
    def __init__(self, args = ""):
        CheckError.__init__(self, args)



class IPPolicyCheck(components.Interface):
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



class PPolicyCheckBase:
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

    __implements__ = (IPPolicyCheck, )


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
        log.msg("[DBG] %s: Starting" % self.getId())
        self.factory = keywords.get('factory', self.factory)
        if self.factory != None:
            self.getDbConnection = self.factory.getDbConnection
        if self.cacheResult:
            self.cacheResultData = getattr(self, 'cacheResultData', None);
            if self.cacheResultData == None:
                self.cacheResultData = tools.MemCache(self.cacheResultLifetime,
                                                      self.cacheResultSize)
            self.cacheResultData.clean()
        else:
            self.cacheResultData = None
        self.setState('start', *args, **keywords)


    def doStart(self, *args, **keywords):
        """Called when changing state to 'ready'."""
        pass


    def doStopInt(self, *args, **keywords):
        """Called by protocol factory before shutdown."""
        log.msg("[DBG] %s: Stopping" % self.getId())
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
        log.msg("[DBG] %s: Checking..." % self.getId())
        if self._state != 'ready':
            return self.defaultAction, self.defaultActionEx

        dataHash = self.dataHash(data)
        if self.cacheResult:
            action, actionEx = self.cacheResultData.get(dataHash, (None, None))
            if action != None:
                log.msg("[DBG] %s: result cache hit (%s, %s)" %
                        (self.getId(), action, actionEx))
                return action, actionEx
        action, actionEx = self.doCheck(data)
        log.msg("[DBG] %s: result (%s, %s)" %
                (self.getId(), action, actionEx))
        if self.cacheResult:
            self.cacheResultData.set(dataHash, (action, actionEx))
        return action, actionEx


    def doCheck(self, data):
        """This method will be called according configuration to
        check input data. If chaching is enabled (default) it will
        be called only if actionEx for requested data is not in cache.
        This method has to be implemented in child classes."""
        raise NotImplementedError("Don't call base class directly")


    def getDbConnection(self):
        """Get database connection from factory connection pool. You
        have to provide reference to factory in doStartInt(factory=factory)
        otherwise this method will throw exception because of no access
        to the factory connection pool (in fact it use factory method
        getDbConnection()"""
        raise NotImplementedError("No connection function defined")



class DummyCheck(PPolicyCheckBase):
    """Dummy check module for testing."""


    def __init__(self, *args, **keywords):
        PPolicyCheckBase.__init__(self, *args, **keywords)


    #def getId(self):
    #    return self.id


    #def setParams(self, *args, **keywords):
    #    lastState = self.setState('stop')
    #    PPolicyCheckBase.setParams(self, *args, **keywords)
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



class SimpleCheck(PPolicyCheckBase):
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
        PPolicyCheckBase.__init__(self, *args, **keywords)


    def setParams(self, *args, **keywords):
        PPolicyCheckBase.setParams(self, *args, **keywords)
        self.action = keywords.get('action', self.action)
        self.actionEx = keywords.get('actionEx', self.actionEx)


    def dataHash(self, data):
        return 0


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())

        if self.action == None:
            action = self.defaultAction
        else:
            action = self.action

        if self.actionEx == None:
            actionEx = self.defaultActionEx
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



class LogicCheck(PPolicyCheckBase):
    """Base class for logical operations and conditions between
    some group of check modules.
    """

    def __init__(self, *args, **keywords):
        PPolicyCheckBase.__init__(self, *args, **keywords)


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
            return self.defaultAction, self.defaultActionEx

        dunno = False
        for check in self.checks:
            action, actionEx = check.doCheckInt(data)
            logic = self.getLogicValue(action)
            if logic == None:
                dunno = True
            elif not logic:
                return action, actionEx

        if dunno:
            return self.defaultAction, self.defaultActionEx
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
            return self.defaultAction, self.defaultActionEx

        dunno = False
        for check in self.checks:
            action, actionEx = check.doCheckInt(data)
            logic = self.getLogicValue(action)
            if logic == None:
                dunno = True
            elif logic:
                return action, actionEx

        if dunno:
            return self.defaultAction, self.defaultActionEx
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
            return self.defaultAction, self.defaultActionEx

        action, actionEx = self.check.doCheckInt(data)
        logic = self.getLogicValue(action)
        if logic == None:
            return self.defaultAction, self.defaultActionEx
        elif logic:
            return 'OK', "%s ok" % self.getId()
        else:
            return 'REJECT', "%s failed" % self.getId()



class EqCheck(LogicCheck):
    """Run defined check and compare if result is equal.

    --------+-------+-------+
    | EQ    | AAAAA | BBBBB |
    +-------+-------+-------+
    | AAAAA | TRUE  | FALSE |
    +-------+-------+-------+
    | BBBBB | FALSE | TRUE  |
    +-------+-------+-------+

    Parameters:
      checks
        "check" class instances to compare (default: [])
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


    def doChecks(self, data):
        log.msg("[DBG] %s: running checks" % self.getId())

        if self.checks == []:
            log.msg("[WRN] %s: no checks defined" % self.getId())
            return self.defaultAction, self.defaultActionEx

        firstAction = None
        eq = True
        for check in self.checks:
            action, actionEx = check.doCheckInt(data)
            if firstAction == None:
                firstAction = action
            elif action != firstAction:
                eq = False

        if eq:
            return 'OK', "%s equal" % self.getId()
        else:
            return 'REJECT', "%s not equal" % self.getId()



class IfCheck(LogicCheck):
    """Run check and according result run first (ok) or second (reject)
    check. It provide IF functionality for module configuration. If some
    error occurs than it returns defaultAction ('DUNNO')

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
            return self.defaultAction, self.defaultActionEx

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
            return self.defaultAction, self.defaultActionEx

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
            return self.defaultAction, self.defaultActionEx

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
            return self.defaultAction, self.defaultActionEx

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
            return self.defaultAction, self.defaultActionEx

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
            return self.defaultAction, self.defaultActionEx

        return check.doCheckInt(data)



class AccessCheck(PPolicyCheckBase):
    """Check if item is in specified list and return corresponding
    action, actionEx. It is simalar to postfix access(5) table.

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
        database table with whitelist (default: access)
      cols
        dictionary { 'name': 'name',
                     'action': [ 'action', 'actionEx' ] }
      cacheExpire
        expiration time of records in memory cache - longer time is better
        for performance but worser in propagating changes in Db (default: 900s)
      cacheSize
        memory cache size, for best performance should be 0 - means
        load all records in memory (default: 0)
    """


    def __init__(self, *args, **keywords):
        self.param = None
        self.paramFunction = None
        self.table = 'access'
        self.cols = { 'name': 'name',
                      'value': [ 'action', 'actionEx' ] }
        self.cacheExpire = 900
        self.cacheSize = 0
        self.cache = None
        PPolicyCheckBase.__init__(self, *args, **keywords)


    def getId(self):
        return "%s[%s]" % (self.id, self.table)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        PPolicyCheckBase.setParams(self, *args, **keywords)
        self.param = keywords.get('param', self.param)
        self.paramFunction = keywords.get('paramFunction', self.paramFunction)
        self.table = keywords.get('table', self.table)
        self.cols =keywords.get('cols', self.cols)
        self.cacheExpire = keywords.get('cacheExpire', self.cacheExpire)
        self.cacheSize = keywords.get('cacheSize', self.cacheSize)
        self.setState(lastState)


    def dataHash(self, data):
        if self.param == None:
            return 0
        else:
            return hash("=".join([ self.param, data.get(self.param) ]))


    def doStart(self, *args, **keywords):
        self.cache = tools.DbCache(self, self.table, self.cols, True,
                                   self.cacheExpire, self.cacheSize)


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())

        if self.param == None:
            return self.defaultAction, self.defaultActionEx

        if self.paramFunction == None:
            dtaArr = [ data.get(self.param) ]
        else:
            dtaArr = self.paramFunction(data.get(self.param))

        if dtaArr in [ None, [], [ None ] ]:
            log.msg("[WRN] %s: no test data for %s" %
                    (self.getId(), self.param))
            return self.defaultAction, self.defaultActionEx

        for dta in dtaArr:
            action, actionEx = self.cache.get(dta, (None, None))
            if action == None:
                return self.defaultAction, self.defaultActionEx
            else:
                return action, actionEx

        return self.defaultAction, self.defaultActionEx



class ListWBCheck(PPolicyCheckBase):
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
      cacheExpire
        expiration time of records in memory cache - longer time is better
        for performance but worser in propagating changes in Db (default: 900s)
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
        self.cacheExpire = 900
        self.cacheSize = 0
        PPolicyCheckBase.__init__(self, *args, **keywords)


    def getId(self):
        return "%s[%s,%s]" % (self.id, self.whitelistTable,
                              self.blacklistTable)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        PPolicyCheckBase.setParams(self, *args, **keywords)
        self.param = keywords.get('param', self.param)
        self.paramFunction = keywords.get('paramFunction', self.paramFunction)
        self.whitelistTable = keywords.get('whitelistTable', self.whitelistTable)
        self.whitelistColumn = keywords.get('whitelistColumn', self.whitelistColumn)
        self.blacklistTable = keywords.get('blacklistTable', self.blacklistTable)
        self.blacklistColumn = keywords.get('blacklistColumn', self.blacklistColumn)
        self.cacheExpire = keywords.get('cacheExpire', self.cacheExpire)
        self.cacheSize = keywords.get('cacheSize', self.cacheSize)
        self.setState(lastState)


    def dataHash(self, data):
        if self.param == None:
            return 0
        else:
            return hash("=".join([ self.param, data.get(self.param) ]))


    def doStart(self, *args, **keywords):
        self.wlCache = tools.DbCache(self, self.whitelistTable,
                                     { 'name': self.whitelistColumn },
                                     True, self.cacheExpire, self.cacheSize)
        self.blCache = tools.DbCache(self, self.blacklistTable,
                                     { 'name': self.blacklistColumn },
                                     True, self.cacheExpire, self.cacheSize)


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())

        if self.param == None:
            return self.defaultAction, self.defaultActionEx

        if self.paramFunction == None:
            dtaArr = [ data.get(self.param) ]
        else:
            dtaArr = self.paramFunction(data.get(self.param))

        if dtaArr in [ None, [], [ None ] ]:
            log.msg("[WRN] %s: no test data for %s" %
                    (self.getId(), self.param))
            return self.defaultAction, self.defaultActionEx

        for dta in dtaArr:
            if self.wlCache.get(dta, False):
                return 'OK', "%s %s is on whitelist" % (self.param, dta)
            if self.blCache.get(dta, False):
                return 'REJECT', "%s %s is on blacklist" % (self.param, dta)

        return self.defaultAction, self.defaultActionEx



class SPFCheck(PPolicyCheckBase):
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
        PPolicyCheckBase.__init__(self, *args, **keywords)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        PPolicyCheckBase.setParams(self, *args, **keywords)
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
            return self.defaultAction, self.defaultActionEx

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



class DbCacheCheck(PPolicyCheckBase):
    """Base class for check that uses Db to store results. Some methods has
    to be implemented in subclasses.

    Parameters:
      cacheTable
        database table name for caching data (default: None)
      cacheCols
        dictionary { 'name': 'name VARCHAR(255)',
                     'value': [ 'code VARCHAR(20)', 'ex VARCHAR(500)' ],
                     'expire': 'expire' }
        see RFC 2821, 4.5.3.1 Size limits and minimums
      cachePositive
        expiration time sucessfully verified records (default: month)
      cacheNegative
        expiration time if verification fail (def: 4 hours)
      cacheNegative5xx
        expiration time if verification fail with code 5xx (def: 2 days)
      cacheExpire
        expiration time for records in memory (default: 15 minutes)
      cacheSize
        max number of records in memory cache (default: 0 - all records)
    """


    def __init__(self, *args, **keywords):
        self.cacheTable = getattr(self, 'cacheTable', None)
        self.cacheCols = getattr(self, 'cacheCols',
                                 { 'name': 'name VARCHAR(255)',
                                   'value': [ 'code VARCHAR(20)',
                                              'ex VARCHAR(500)' ],
                                   'expire': 'expire' })
        self.cachePositive = getattr(self, 'cachePositive', 60*60*24*31)
        self.cacheNegative = getattr(self, 'cacheNegative', 60*60*4)
        self.cacheNegative5xx = getattr(self, 'cacheNegative5xx', 60*60*24*2)
        self.cacheExpire = getattr(self, 'cacheExpire', 60*15)
        self.cacheSize = getattr(self, 'cacheSize', 0)
        PPolicyCheckBase.__init__(self, *args, **keywords)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        PPolicyCheckBase.setParams(self, *args, **keywords)
        self.cacheTable = keywords.get('cacheTable', self.cacheTable)
        self.cacheCols = keywords.get('cacheCols', self.cacheCols)
        self.cachePositive = keywords.get('cachePositive', self.cachePositive)
        self.cacheNegative = keywords.get('cacheNegative', self.cacheNegative)
        self.cacheNegative5xx = keywords.get('cacheNegative5xx', self.cacheNegative5xx)
        self.cacheExpire = keywords.get('cacheExpire', self.cacheExpire)
        self.cacheSize = keywords.get('cacheSize', self.cacheSize)
        self.setState(lastState)


    def doStart(self, *args, **keywords):
        self.cache = tools.DbCache(self, self.cacheTable, self.cacheCols,
                                   True, self.cacheExpire, self.cacheSize)


    def doCheck(self, data):
        log.msg("[DBG] %s: running check" % self.getId())

        key = self.getKey(data)
        if key != None:
            action, actionEx = self.cache.get(key, (None, None))

        if action == None:

            action, actionEx = self.doCheckReal(data)

            actTest = action.lower()
            if len(actTest) == 3:
                if action[0] == '4': expire = self.cacheNegative
                elif action[0] == '5': expire = self.cacheNegative5xx
            elif actTest in [ 'ok', 'permit' ]:
                expire = self.cachePositive
            elif action in [ 'reject' ]:
                expire = self.cacheNegative5xx
            else:
                log.msg("[DBG] %s: unknown return action %s" %
                        (self.getId(), action))
                return self.defaultAction, self.defaultActionEx

            if key != None:
                self.cache.set(key, (action, actionEx), time.time() + expire)

        return action, actionEx


    def doCheckReal(self, data):
        raise NotImplementedError("You can't call base class %s directly" %
                                  self.getId())


    def getKey(self, data):
        return self.dataHash(data)



class VerificationCheck(DbCacheCheck):
    """Base class for user and domain verification and subclass
    of DbCacheCheck. It check domain existence and then it try
    to establish SMTP connection with mailhost for the domain
    (MX, A or AAAA DNS records - see RFC2821, chapter 5).

    Parameters (see descriptionn of parent class L{VerificationCheck}):
      param
        string key for data item that should be verified (default: None)
    """


    def __init__(self, *args, **keywords):
        self.param = getattr(self, 'param', None)
        DbCacheCheck.__init__(self, *args, **keywords)


    def setParams(self, *args, **keywords):
        lastState = self.setState('stop')
        PPolicyCheckBase.setParams(self, *args, **keywords)
        self.param = keywords.get('param', self.param)
        self.setState(lastState)


    def dataHash(self, data):
        """Compute hash only from used data fields."""
        if self.param == None:
            return 0
        else:
            return hash("=".join([ self.param, data.get(self.param) ]))


    def doCheckReal(self, data):
        if self.param == None or not data.has_key(self.param):
            log.msg("[DBG] %s: no param" % self.getId())
            return self.defaultAction, self.defaultActionEx

        # RFC 2821, section 4.1.1.2
        # empty MAIL FROM: reverse address may be null
        if self.param == 'sender' and data[self.param] == '':
            return self.defaultAction, self.defaultActionEx

        # RFC 2821, section 4.1.1.3
        # see RCTP TO: grammar
        if self.param == 'recipient' and data[self.param] == 'Postmaster':
            return self.defaultAction, self.defaultActionEx

        user, domain = self.getUserDomain(data[self.param])
        if user == None or domain == None:
            log.msg("[WRN] %s: address for %s in unknown format: %s" %
                    (self.getId(), self.param, data[self.param]))
            return '550', "%s address format icorrect %s" % (self.param,
                                                             data[self.param])

        mailhosts = tools.getDomainMailhosts(domain)
        if len(mailhosts) == 0:
            log.msg("[INF] %s: no mailhost for %s" % (self.getId(), domain))
            return '450', "Can't find mailserver for %s" % domain

        action = self.defaultAction
        actionEx = self.defaultActionEx

        for mailhost in mailhosts:
            code, codeEx = self.checkMailhost(mailhost, domain, user)
            # FIXME: how many MX try? timeout?
            if code != None:
                if code < 400:
                    action = 'OK'
                    break
                elif code < 500:
                    action = '450'
                    actionEx = codeEx
                    continue
                else:
                    action = '550'
                    actionEx = codeEx
                    break
        if code == None:
            return self.defaultAction, self.defaultActionEx

        return action, actionEx


    def getUserDomain(self, address):
        raise NotImplementedError("Implemented in subclass %s" % self.getId())


    def _getUserDomain(self, address):
        user = None
        domain = None
        if self.param in [ 'sender', 'recipient' ]:
            try:
                user, domain = address.split("@")
            except ValueError:
                pass
        else:
            user = 'postmaster'
            domain = address
        return user, domain

        
    def checkMailhost(self, mailhost, domain, user):
        """Check if something listening for incomming SMTP connection
        for mailhost. For details about status that can occur during
        communication see RFC 2821, section 4.3.2"""
        import smtplib
        import socket

        try:
            conn = smtplib.SMTP(mailhost)
            conn.set_debuglevel(10) # FIXME: [DBG]
            code, retmsg = conn.helo()
            if code >= 400:
                return code, "%s verification HELO failed: %s" % (self.param,
                                                                  retmsg)
            code, retmsg = conn.mail("postmaster@%s" % socket.gethostname())
            if code >= 400:
                return code, "%s verification MAIL failed: %s" % (self.param,
                                                                  retmsg)
            code, retmsg = conn.rcpt("%s@%s" % (user, domain))
            if code >= 400:
                return code, "%s verification RCPT failed: %s" % (self.param,
                                                                  retmsg)
            code, retmsg = conn.rset()
            conn.quit()
            conn.close()
            return 250, "Domain verification success"
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

        return 450, "Domain verirication failed."



class DomainVerificationCheck(VerificationCheck):
    """Check if sender/recipient or whatever reasonable is has correct
    DNS records as mailhost and try to connect to this server.

    Parameters (see descriptionn of parent class L{VerificationCheck}):
      param
        reasonable values are 'sender','recipient','helo_name' (default: None)
      cacheTable
        default: verification_domain
    """


    def __init__(self, *args, **keywords):
        self.cacheTable = 'verification_domain'
        VerificationCheck.__init__(self, *args, **keywords)


    def getUserDomain(self, address):
        user, domain = self._getUserDomain(address)
        return 'postmaster', domain


    def getKey(self, data):
        user, domain = self.getUserDomain(data.get(self.param))
        return domain



class UserVerificationCheck(VerificationCheck):
    """Check if sender/recipient is accepted by mailserver. Be carefull
    when turning on verification and first read
    http://www.postfix.org/ADDRESS_VERIFICATION_README.html
    about its limitation

    Parameters (see descriptionn of parent class L{VerificationCheck}):
      param
        reasonable values are 'sender' and 'recipient' (default: None)
      cacheTable
        default: verification_sender/recipient
    """


    def __init__(self, *args, **keywords):
        self.cacheTable = 'verification_user'
        VerificationCheck.__init__(self, *args, **keywords)


    def getUserDomain(self, address):
        return self._getUserDomain(address)


    def getKey(self, data):
        user, domain = self.getUserDomain(data.get(self.param))
        return "%s@%s" % (user, domain)



class GreylistCheck(PPolicyCheckBase):
    """Greylist implementation.

    Parameters:
      table:
        greylist database table (default: greylist)
      cacheCols
        dictionary of greylist table columns
      cacheExpire
        expiration time for records in memory (default: 15 minutes)
      cacheSize
        max number of records in memory cache (default: 1000), 0 = all records
      greyTime:
        time we temporary reject unknown triplet sen+rec+ip (default: 10 min)
      greyExpire:
        expiration time of greylist record (default: 31 days)
    """


    def __init__(self, *args, **keywords):
        self.table = 'greylist'
        self.cols = { 'name': [ 'sender VARCHAR(255)',
                                'recipient VARCHAR(255)',
                                'client_address VARCHAR(50)' ],
                      'value':  'value TIMESTAMP',
                      'expire': 'expire' }
        self.cacheExpire = 60*15
        self.cacheSize = 1000
        self.greyTime = 60*10
        self.greyExpire = 60*60*24*31
        PPolicyCheckBase.__init__(self, *args, **keywords)


    def setParameters(self, *args, **keywords):
        lastState = self.setState('stop')
        PPolicyCheckBase.setParams(self, *args, **keywords)
        self.table = keywords.get('table', self.table)
        self.cols = keywords.get('cols', self.cols)
        self.cacheExpire = keywords.get('cacheExpire', self.cacheExpire)
        self.cacheSize = keywords.get('cacheSize', self.cacheSize)
        self.greyTime = keywords.get('greyTime', self.greyTime)
        self.greyExpire = keywords.get('greyExpire', self.greyExpire)
        self.setState(lastState)


    def dataHash(self, data):
        """Compute hash only from used data fields."""
        keys = sorted(data.keys())
        return hash("\n".join([ "=".join([x, data[x]]) for x in keys if x in [ "sender", "recipient", "client_address" ] ]))


    def doStart(self, *args, **keywords):
        self.cache = tools.DbCache(self, self.table, self.cols, True,
                                   self.cacheExpire, self.cacheSize)


    def doCheck(self, data):
        import spf
        log.msg("[DBG] %s: running check" % self.getId())

        sender = data.get('sender')
        recipient = data.get('recipient')
        client_name = data.get('client_name')
        client_address = data.get('client_address')

        # RFC 2821, section 4.1.1.2
        # empty MAIL FROM: reverse address may be null
        if sender == '':
            return self.defaultAction, self.defaultActionEx

        # RFC 2821, section 4.1.1.3
        # see RCTP TO: grammar
        if recipient == 'Postmaster':
            return self.defaultAction, self.defaultActionEx

        try:
            user, domain = sender.split("@")
        except ValueError:
            log.msg("[WRN] %s: sender address in unknown format: %s" %
                    (self.getId(), sender))
            return '550', "sender address format icorrect %s" % sender

        mailhosts = tools.getDomainMailhosts(domain)
        spfres, spfstat, spfexpl = spf.check(i=client_address,
                                             s=sender, h=client_name)
        if client_address in mailhosts or spfres == 'pass':
            greysubj = domain
        else:
            greysubj = client_address

        greyTime = self.cache.get((sender, recipient, greysubj), None)
        if greyTime == None:
            greyTime = self.greyTime + time.time()
        if greyTime > time.time():
            action = '451'
            actionEx = "You have been greylisted. This is part of our antispam procedure for %s domain. Your mail will be accepted in %ss" % (domain, int(greyTime - time.time()))
        else:
            action = self.defaultAction
            actionEx = self.defaultActionEx

        self.cache.set((sender, recipient, greysubj), greyTime,
                       time.time() + self.greyExpire)

        return action, actionEx



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
    if len(sys.argv) > 1:
        obj = eval(sys.argv[1])
        obj.doStartInt(factory=FakeFactory())
        print obj.doCheckInt(data)
        obj.doStopInt()
        sys.exit()
    print ">>>>>>>>>>>>>>>>>>>>>>>>> GLOBAL CHECKS - BEGIN <<<<<<<<<<<<<<<<<<<<<<<<<"
    for checkClass in [ PPolicyCheckBase, DummyCheck, SimpleCheck,
                        OkCheck, Reject4xxCheck, Reject5xxCheck, RejectCheck,
                        DeferIfRejectCheck, DeferIfPermitCheck, DiscardCheck,
                        DunnoCheck, FilterCheck, HoldCheck, PrependCheck,
                        RedirectCheck, WarnCheck,
                        AndCheck, OrCheck, NotCheck, IfCheck, If3Check,
                        SwitchCheck,
                        AccessCheck, ListWBCheck, SPFCheck,
                        DomainVerificationCheck, UserVerificationCheck,
                        GreylistCheck ]:
        check = checkClass(debug=True, param='sender')
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

