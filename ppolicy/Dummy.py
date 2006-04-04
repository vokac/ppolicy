#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Dummy module skeleton for creating new modules
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
from Base import Base


__version__ = "$Revision$"


class Dummy(Base):
    """Dummy module skeleton for creating new modules

    Module arguments (see output of getParams method):
    test1, test2

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... ok 
        0 .... undefined (default for this module)
        -1 ... failed

    Examples:
        # make instance of dummy module
        define('dummy1', 'Dummy')
        # make instance of dummy module with parameters
        define('dummy1', 'Dummy', test1=1, test2="def")
    """

    PARAMS = { 'test1': ('test parameter 1', None),
               'test2': ('test parameter 2', 'abc'),
               'cachePositive': (None, 0), # define new default value
               'cacheUnknown': (None, 0), # define new default value
               'cacheNegative': (None, 0), # define new default value
               }


    def start(self):
        """Called when changing state to 'started'."""
        pass


    def stop(self):
        """Called when changing state to 'stopped'."""
        pass


    def hashArg(self, *args, **keywords):
        """Compute hash from data which is then used as index
        to the result cache. Changing this function in subclasses
        and using only required fields for hash can improve cache
        usage and performance."""
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        return 0


    def check(self, *args, **keywords):
        """check request data againts policy and returns tuple of status
        code and optional info. The meaning of status codes is folloving:
            < 0 check failed
            = 0 check uknown (e.g. required resource not available)
            > 0 check succeded
        """
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        return 0, 'dummy'
