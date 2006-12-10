#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Country module for recognizing country according IP address
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
import os, re
from Base import Base, ParamError
import GeoIP


__version__ = "$Revision$"


class Country(Base):
    """Country module for recognizing country according IP address
    or domain name.

    Module arguments (see output of getParams method):
    param, country

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... ok, country match, second parameter is country name
        0 .... undefined (some error)
        -1 ... failed, country doesn't match, second parameter is country name

    Examples:
        # return country for client_address
        modules['country1'] = ( 'Country', { 'param': 'client_address',
                                             'dataPath': '/usr/share/GeoIP/GeoIP.dat' } )
        # check if client_address is 'cz'
        modules['country2'] = ( 'Country', { 'param': 'client_address',
                                             'dataPath': '/usr/share/GeoIP/GeoIP.dat',
                                             'country': 'CZ' } )
    """

    PARAMS = { 'param': ('name of parameter in data dictionary', None),
               'country': ('check if IP is in this country', None),
               'dataPath': ('path to GeoIP.dat file', None),
               'cachePositive': (None, 0), #
               'cacheUnknown': (None, 0),  # don't cache Country informations
               'cacheNegative': (None, 0), #
               }


    def start(self):
        """Called when changing state to 'started'."""
        for attr in [ 'param', 'dataPath' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        dataPath = self.getParam('dataPath')
        if not os.access(dataPath, os.R_OK):
            raise ParamError("can't access GeoIP data in %s" % dataPath)

        self.reIPv4 = re.compile("^([012]?\d{1,2}\.){3}[012]?\d{1,2}$")
        self.reIPv6 = re.compile('^([0-9a-fA-F]{0,4}:){0,7}([0-9a-fA-F]{0,4}|([012]?\d{1,2}\.){3}[012]?\d{1,2})$')

        try:
            self.gi = GeoIP.open(dataPath, GeoIP.GEOIP_MEMORY_CACHE)
        except SystemError, e:
            raise ParamError("can't create GeoIP instance: %s"  % e)


    def stop(self):
        """Called when changing state to 'stopped'."""
        del(self.gi)


    def hashArg(self, data, *args, **keywords):
        """Don't cache results of this module - always return 0"""
        return 0


    def check(self, data, *args, **keywords):
        param = self.getParam('param', None, keywords)
        country = self.getParam('country', None, keywords)
        paramValue = data.get(param, '')

        if self.gi == None:
            return 0, None

        if self.reIPv4.match(paramValue) != None:
            pc = self.gi.country_code_by_addr(paramValue)
        elif self.reIPv6.match(paramValue) != None:
            logging.getLogger().info("GeoIP doesn't support IPv6 lookup for %s" % paramValue)
            return 0, None
        else:
            pc = self.gi.country_code_by_name(paramValue)

        if pc == None:
            return 0, None

        if country == None:
            return 1, pc

        if country.lower() == pc.lower():
            return 1, pc
        else:
            return -1, pc
