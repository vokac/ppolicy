#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Whois module to get whois information for IP address
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


class Whois(Base):
    """Whois module can be used to return IP whois informations

    Module arguments (see output of getParams method):
    param

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... ok 
        0 .... undefined (default for this module)
        -1 ... failed

    Examples:
        # make instance of dummy module
        modules['whois1'] = ( 'Whois', {} )
        # make instance of dummy module with parameters
        modules['whois2'] = ( 'Whois', { 'param': "client_address" } )
    """

    PARAMS = { 'test1': ('test parameter 1', 'client_address'),
               'cachePositive': (None, 60*60),
               'cacheUnknown': (None, 60*15),
               'cacheNegative': (None, 60*60),
               }


    def start(self):
        """Called when changing state to 'started'."""
        pass


    def stop(self):
        """Called when changing state to 'stopped'."""
        pass


    def hashArg(self, data, *args, **keywords):
        return 0


    def check(self, data, *args, **keywords):
        return 0, None
