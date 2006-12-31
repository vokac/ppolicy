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
    dnsbl, scoreOnly

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... listed in dnsbl
        0 .... unknown error (e.g. DNS problems)
        -1 ... not listed

    Examples:
        # check if sender mailserver is in ORDB blacklist
        modules['dnsbl1'] = ( 'Dnsbl', { dnsbl="ORDB" } )
    """

    PARAMS = { 'dnsbl': ('name of DNS blacklists defined in this module', None),
               'cachePositive': (None, 6*60*60),
               'cacheUnknown': (None, 30*60),
               'cacheNegative': (None, 12*60*60),
               }


    def start(self):
        for attr in [ 'dnsbl' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        dnsblName = self.getParam('dnsbl')
        if not dnsbl.getInstance().has_config(dnsblName):
            raise ParamError("there is not %s dnsbl list in config file" % dnsblName)


    def hashArg(self, data, *args, **keywords):
        return hash(data.get('client_address'))


    def check(self, data, *args, **keywords):
        client_address = data.get('client_address')
        sender = None # FIXME: we should check also sender domain!!!
        dnsblName = self.getParam('dnsbl')

        resHit, resScore = dnsbl.check(client_address, sender, [ dnsblName ], False)
        return resHit, resScore
