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
from tools import dnsbl, dnscache


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
        modules['dnsbl1'] = ( 'DnsblDynamic', { 'dnsbl': [ 'NJABLDYNA', 'SORBSDUL' ] } )
    """

    PARAMS = { 'dnsbl': ('list of DNS blacklists', None),
               'check_name': ('check format of client name (e.g. xxx-yyy-zzz.dsl.provider.com)', True),
               'cachePositive': (None, 6*60*60),
               'cacheUnknown': (None, 30*60),
               'cacheNegative': (None, 12*60*60),
               }


    def start(self):
        if self.getParam('dnsbl') == None:
            raise ParamError("parameter \"dnsbl\" has to be specified for this module")

        dnsblNames = self.getParam('dnsbl')
        for dnsblName in dnsblNames:
            if not dnsbl.getInstance().has_config(dnsblName):
                raise ParamError("there is not %s dnsbl list in config file" % dnsblName)

        self.patternInclude = []
        self.patternExclude = []
        check_name = self.getParam('check_name', False)

        if check_name:
            # match domain name looking like something.xxx-yyy-zzz.provider.com
            self.patternInclude.append(re.compile('(\d{1,3}[.x-]){2}\d{1,3}\.[^.]+\.[^.]+'))
            # match domain name looking like ip-123-123.provider.com
            self.patternInclude.append(re.compile('ip(-\d{1,3}){2}\.[^.]+\.[^.]+'))
            # match domain name looking like abc-123-abc-123.provider.com
            self.patternInclude.append(re.compile('(\w+-){3}\w+\.[^.]+\.[^.]+'))
            # match domain name looking like 087206149137.provider.com
            self.patternInclude.append(re.compile('\d{12,}\w*\.[^.]+\.[^.]+'))
            # match domain name looking like net220216005.provider.com
            self.patternInclude.append(re.compile('net\d{9,}\w*\.[^.]+\.[^.]+'))
            # match domain name looking like pool12-34.provider.com
            self.patternInclude.append(re.compile('(user|host|pool|dial|dialup|dip0|ppp(oe)?|dhcp|(a|s|x)?dsl|internetdsl|dynamic|dyn-ip|dyn|static|cable|catv|broadband\d*)(|\.|x|-)\d+([.x-]\d+)+\.[^.]+\.[^.]+'))
#            # match domain name looking like 01234567.provider.com
#            self.patternInclude.append(re.compile('[0-9a-fA-F]{8}\w*\.[^.]+\.[^.]+'))
            # match domain name looking like something.dhcp.level1.level2
            self.patternInclude.append(re.compile('[.-](user|host|pool|dial|dialup|dip0|ppp(oe)?|dhcp|(a|s|x)?dsl|internetdsl|dynamic|dyn-ip|dyn|static|cable|catv|broadband\d*)(|-[^.]+)\.[^.]+\.[^.]+'))
            # match domain name looking like dlp-14.as2.tz-1.bih.net.ba
            # at least six parts and on of them end with -123 or 123
            self.patternInclude.append(re.compile('.+-?\d+(\..+){5,}|(\..+){1,}.+-?\d+(\..+){4}|(\..+){2,}.+-?\d+(\..+){3}|(\..+){3,}.+-?\d+(\..+){2}'))


    def hashArg(self, data, *args, **keywords):
        return hash(data.get('client_address'))


    def check(self, data, *args, **keywords):
        client_address = data.get('client_address')
        sender = None # FIXME: we should check also sender domain!!!
        reverse_client_name = data.get('reverse_client_name')
        dnsblNames = self.getParam('dnsbl', [])
        check_name = self.getParam('check_name', False)

        # postfix < 2.2 does have only client_name which values
        # is not what we realy want here, try to do reverse DNS lookup
        if reverse_client_name == None:
            names = dnscache.getNameForIp(client_address)
            if len(names) > 0:
                reverse_client_name = names[0]
            else:
                reverse_client_name = ''

        # check reverse_client_name format
        if check_name:
            excluded = False
            for pattern in self.patternExclude:
                if pattern.search(reverse_client_name) != None:
                    excluded = True
                    break
            if not excluded:
                for pattern in self.patternInclude:
                    if pattern.search(reverse_client_name) != None:
                        return 1, "%s (%s) is dynamic identified by regex" % (client_address, reverse_client_name)
        
        # check listing in dnsbl
        resHit, resScore = dnsbl.check(client_address, sender, dnsblNames, False)
        if resHit > 0:
            return 1, "%s (%s) is dynamic listed, score %s" % (client_address, reverse_client_name, resScore)

        return -1, "%s (%s) is not in dynamic range" % (client_address, reverse_client_name)



if __name__ == "__main__":
    import sys
    import socket
    import twisted.python.log
    twisted.python.log.startLogging(sys.stdout)

    if len(sys.argv) <= 1:
        print "usage: %s IP [domain.name.tld]" % sys.argv[0]
        sys.exit(1)

    hostIP = sys.argv[1]
    if len(sys.argv) > 2:
        hostName = sys.argv[2]
    else:
        try:
            hostName = socket.gethostbyaddr(hostIP)[0]
        except socket.herror:
            hostName = hostIP

    obj = DnsblDynamic('DnsblDynamic')
    obj.start()
    print obj.check({ 'client_address': hostIP, 'reverse_client_name': hostName })
    obj.stop()

