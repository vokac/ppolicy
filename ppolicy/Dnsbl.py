#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Check if client address is listed in specified DNS blacklist
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
from Base import Base, ParamError
from tools import dnsbl


__version__ = "$Revision$"


class Dnsbl(Base):
    """Check if client address is listed in specified DNS blacklist.
    see tools/dnsbl.txt for list of valid blacklist names - original
    file can be downloaded from http://moensted.dk/spam/drbsites.txt
    You can also run `python tools/dnsbl.py --list` to see formated
    output of configured balacklists.

    Module arguments (see output of getParams method):
    dnsbl

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... listed in dnsbl
        0 .... unknown error (e.g. DNS problems)
        -1 ... not listed

    Examples:
        # check if sender mailserver is in ORDB blacklist
        define('dnsbl1', 'Dnsbl', dnsbl="ORDB")
    """

    PARAMS = { 'dnsbl': ('name of DNS blacklist defined in this module', None),
               }


    def start(self):
        for attr in [ 'dnsbl' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        dnsblName = self.getParam('dnsbl')
        if not dnsbl.has_config(dnsblName):
            raise ParamError("there is not %s dnsbl list in config file" % dnsblName)


    def hashArg(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        return hash(data.get('client_address'))


    def check(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        client_address = data.get('client_address')
        dnsblName = self.getParam('dnsbl')

        res = dnsbl.check(dnsblName, client_address)
        if res == None:
            return 0, "error checking %s in %s" % (client_address, dnsblName)
        if res:
            return 1, "%s blacklisted in %s" % (client_address, dnsblName)
        else:
            return -1, "%s is not in %s blacklist" % (client_address, dnsblName)
