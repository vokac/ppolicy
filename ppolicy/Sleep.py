#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Sleep module for debugging
#
# Copyright (c) 2007 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
import time
from Base import Base


__version__ = "$Revision$"


class Sleep(Base):
    """Sleep module for debugging

    Module arguments (see output of getParams method):
    sleep

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... ok 
        0 .... undefined (default for this module)
        -1 ... failed

    Examples:
        # make instance of Sleep module
        modules['Sleep1'] = ( 'Sleep', {} )
        # make instance of Sleep module with parameters
        modules['Sleep2'] = ( 'Sleep', { 'sleep': 10 } )
    """

    PARAMS = { 'sleep': ('sleep interval in seconds (default 1s)', 1),
               }


    def start(self):
        self.sleep = self.getParam('sleep')


    def stop(self):
        pass


    def hashArg(self, data, *args, **keywords):
        return 0


    def check(self, data, *args, **keywords):
        time.sleep(self.sleep)
        return 0, 'Sleep'
