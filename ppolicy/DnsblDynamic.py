#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Check if client address is in dynamic allocated ranges.
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import re
import logging
from Base import Base, ParamError
from tools import dnsbl


__version__ = "$Revision$"


class DnsblDynamic(Base):
    """Check if client address is in dynamic allocated ranges. It use
    corresponding dnsbl and also domain name (e.g. format
    xxx-yyy-zzz.dsl.provider.com).

    There will by probably many "correct" mailservers sitting on IP
    address from dynamic alocated space. Use the result as one of the
    decision rule and don't reject mail only relaying on this result.

    Module arguments (see output of getParams method):
    dnsbl

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... client address seems to be in dynamic ip range
        0 .... unknown error (e.g. DNS problems)
        -1 ... client address doesn't seem to be in dynamic ip range

    Examples:
        # check if sender mailserver is in ORDB blacklist
        modules['dnsbl1'] = ( 'DnsblDynamic', {} )
    """

    PARAMS = { 'dnsbl': ('list of DNS blacklists', [ 'NJABLDYNA', 'KROPKADUL', 'SORBSDUL' ]),
               'check_name': ('check format of client name (e.g. xxx-yyy-zzz.dsl.provider.com)', True),
               'cachePositive': (None, 6*60*60),
               'cacheUnknown': (None, 30*60),
               'cacheNegative': (None, 12*60*60),
               }


    def start(self):
        self.patterns = []
        check_name = self.getParam('check_name', False)

        if check_name:
            # match domain name looking like something.xxx-yyy-zzz.provider.com
            self.patterns.append(re.compile('(\d{1,3}[.x-]){2}\d{1,3}\.[^.]+\.[^.]+'))
            # match domain name looking like ip-123-123.provider.com
            self.patterns.append(re.compile('ip(-\d{1,3}){2}\.[^.]+\.[^.]+'))
            # match domain name looking like abc-123-abc-123.provider.com
            self.patterns.append(re.compile('(\w+-){3}\w+\.[^.]+\.[^.]+'))
            # match domain name looking like 087206149137.provider.com
            self.patterns.append(re.compile('\d{12,}\w*\.[^.]+\.[^.]+'))
            # match domain name looking like net220216005.provider.com
            self.patterns.append(re.compile('net\d{9,}\w*\.[^.]+\.[^.]+'))
            # match domain name looking like pool12-34.provider.com
            self.patterns.append(re.compile('(user|host|pool|dial|ppp(oe)?|dhcp|(a|x)?dsl|internetdsl|dynamic|dyn-ip|cable|catv)(|\.|x|-)\d+([.x-]\d+)+\.[^.]+\.[^.]+'))
#            # match domain name looking like 01234567.provider.com
#            self.patterns.append(re.compile('[0-9a-fA-F]{8}\w*\.[^.]+\.[^.]+'))
            # match domain name looking like something.dhcp.level1.level2
            self.patterns.append(re.compile('[.-](user|host|pool|dial|ppp(oe)?|dhcp|(a|x)?dsl|internetdsl|dynamic|dyn-ip|cable|catv)(|-[^.]+)\.[^.]+\.[^.]+'))
            # match domain name looking like dlp-14.as2.tz-1.bih.net.ba
            # at least six parts and on of them end with -123 or 123
            self.patterns.append(re.compile('.+-?\d+(\..+){5,}|(\..+){1,}.+-?\d+(\..+){4}|(\..+){2,}.+-?\d+(\..+){3}|(\..+){3,}.+-?\d+(\..+){2}'))


    def hashArg(self, data, *args, **keywords):
        return hash(data.get('client_address'))


    def check(self, data, *args, **keywords):
        client_address = data.get('client_address')
        client_name = data.get('client_name')
        dnsblNames = self.getParam('dnsbl', [])
        check_name = self.getParam('check_name', False)

        # check client_name format
        if check_name:
            for pattern in self.patterns:
                if pattern.search(client_name) != None:
                    return 1, "%s is in dynamic range (identified by regex)" % client_name
        
        # check listing in dnsbl
        for dnsblName in dnsblNames:
            res = dnsbl.check(dnsblName, client_address)
            if res != None and res:
                return 1, "%s is in dynamic range (listed in %s)" % (client_address, dnsblName)

        return -1, "%s is not in dynamic range" % client_address
