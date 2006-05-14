#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Base interfaces and class for check modules
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
from twisted.python import components


__version__ = "$Revision$"


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

    def getName(self):
        """get module unique name defined in config file."""

    def getId(self):
        """get module id (class name)."""

    def setParams(self, *args, **keywords):
        """set module parameters."""

    def getParams(self):
        """get module parameters."""

    def setParam(self, key, value):
        """set module parameter."""

    def getParam(self, key, default):
        """get module parameter."""

    def start(self):
        """Called when changing state to 'ready'."""

    def stop(self):
        """Called when changing state to 'stopped'."""

    def hashArg(self, data, *args, **keywords):
        """Hash for data relevant for this module."""

    def check(self, data, *args, **keywords):
        """check request stored data againts policy and returns tuple
        of check status code and optional info. The meaning of status
        codes is folloving:
            < 0 check failed
            = 0 check uknown (e.g. required resource not available)
            > 0 check succeded
        arguments:
            data -- input data
        example: 
            1, None
            0, 'database connection failed'
            -1, 'sender IP in rbl'
            ...
        """



class Base(object):
    """Base class for postfix policy check modules. Normally you have
    to overide "check" method and in some cases also "start", "stop"
    and "hashArg"

    Module arguments (see output of getParams method):
    factory, cachePositive, cacheUnknown, cacheNegative, saveResult,
    saveResultPrefix

    Check arguments:
        None

    Check returns:
        throws NotImplementedError
    """

    __implements__ = (IPPolicyCheck, )

    CHECK_SUCCESS=1
    CHECK_UNKNOWN=0
    CHECK_FAILED=-1

    PARAMS = { 'factory': ('reference to factory instance', None),
               'cachePositive': ('maximum time for caching positive result', 60*15),
               'cacheUnknown': ('maximum time for caching unknown result', 60*15),
               'cacheNegative': ('maximum time for caching negative result', 60*15),
               'saveResult': ('save returned value in data hash for further modules', True),
               'saveResultPrefix': ('prefix for saved data', 'result_'),
#               'redefineDefaultValue': (None, 'abc'),
               }

    def __init__(self, name, factory = None, *args, **keywords):
        """Initialize base ppolicy checking module. It creates parameters
        and sets its default values. Then it call setParams with last
        argumets passed to this constructor.
        
        Arguments:
        name -- module name defined in config file
        factory -- reference to factory that created this object
        keywords -- options that will be passed to setParams method
        """
        self.name = name
        self.type = self.__class__.__name__
        self.factory = factory
        self.paramsHelp = {}
        self.paramsValue = {}
        self.__initParams()
        self.setParams(*args, **keywords)


    def getName(self):
        """get module identification."""
        return self.name


    def getId(self):
        """get module id."""
        return "%s[%s]" % (self.type, self.name)


    def getFactory(self):
        """Get reference to factory object that was used to create this
        module. This reference can be used e.g. to get DB connection
        from connection pool.
        """
        return self.factory


    def __initParams(self):
        hierarchy = self.__class__.mro()
        hierarchy.reverse()
        for clazz in hierarchy:
            if hasattr(clazz, 'PARAMS'):
                for k,v in getattr(clazz, 'PARAMS', {}).items():
                    if v[0] != None:
                        self.__addParam(k, v[0])
                    self.setParam(k, v[1])
                # if there is not PARAMS in subclass we don't
                # need to use parent PARAMS again
                # XXX: this is not good idea, because it change
                # class structure for all subclasses
                #delattr(clazz, 'PARAMS')


    def __addParam(self, key, help):
        if self.paramsHelp.has_key(key):
            logging.getLogger().warn("redefinition of %s" % key)
        self.paramsHelp[key] = help


    def setParams(self, *args, **keywords):
        """Set module parameters."""
        for k,v in keywords.items():
            self.setParam(k, v)


    def getParams(self):
        """Get module parameters."""
        retVal = {}
        for k,v in self.paramsValue.items():
            retVal[k] = (self.paramsHelp.get(k), v)
        return retVal


    def setParam(self, key, value):
        """Set module parameter."""
        if not self.paramsHelp.has_key(key):
            id = 'unknown'
            try:
                id = self.getId()
            except:
                pass
            logging.getLogger().error("trying to set undefined parameter \"%s\" for %s" % (key, id))
            return
        if value == None and self.paramsValue.has_key(key):
            del(self.paramsValue[key])
        else:
            self.paramsValue[key] = value


    def getParam(self, key, default = None):
        """Get module parameter."""
        if not self.paramsValue.has_key(key):
            id = 'unknown'
            try:
                id = self.getId()
            except:
                pass
            logging.getLogger().error("trying to get undefined parameter \"%s\" for %s" % (key, id))
        retVal = self.paramsValue.get(key)
        if retVal == None:
            retVal = default
        return retVal


    def start(self):
        """Called when changing state to 'ready'."""
        pass


    def stop(self):
        """Called when changing state to 'stopped'."""
        pass


    def dataArg(self, pos = -1, key = None, default = None, *args, **keywords):
        """We accept arguments in predefined order or as key=value pairs.
        This method can be used to return right value without regart whitch
        method was used."""
        if pos >= 0 and len(args) > pos:
            return args[pos]
        if key != None:
            return keywords.get(key, default)
        return default


    def hashArg(self, data, *args, **keywords):
        """Compute hash from parameters which is then used as index to
        the result cache. Changing this function in subclasses and
        using only required fields for hash can improve cache usage
        and performance.

        NOTE:
        For good hash better algorithm should be used, e.g. Item 7 in
        Joshua Bloch's Effective Java Programming Language Guide"""

        if type(data) == type({}):
            dataStr = "\n".join([ "%s=%s" % (k,v) for k,v in data.items() ])
        else:
            dataStr = str(data)
        keys = keywords.keys()
        keys.sort()
        keywordsTuple = tuple([ "=".join([x, str(keywords[x])]) for x in keys ])
        argsTuple = tuple([ str(x) for x in args ])
        return hash(dataStr) + hash(argsTuple) + hash(keywordsTuple)


    def check(self, data, *args, **keywords):
        """check request data againts policy and returns tuple of status
        code and optional info. The meaning of status codes is folloving:
            < 0 check failed
            = 0 check uknown (e.g. required resource not available)
            > 0 check succeded
        arguments:
            data -- input data
        example: 
            1, None
            0, 'database connection failed'
            -1, 'sender IP in rbl'
            ...
        """
        raise NotImplementedError("Don't call base class directly")
