#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Module for checking equality of ip to name translation
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
from Base import Base, ParamError
from tools import dnscache


__version__ = "$Revision$"


class Resolve(Base):
    """Try to resolve ip->name, name->ip, name->mx, ip->name->ip,
    name->ip->name, ip1->name->ip2, ip->name->mx, name1->ip->name2.

    Module arguments (see output of getParams method):
    param, type

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... all tranlation were successfull and equal
        0 .... problem resolving ip or name (DNS error)
        -1 ... translation failed

    Examples:
        # check if sender domain exist
        modules['resolve1'] = ( 'Resolve', { param="sender",
                                             type="name->ip" } )
        # check if remote mailserver has reverse records in DNS
        modules['resolve2'] = ( 'Resolve', { param="client_address",
                                             type="ip->name" } )
        # check if remote mailserver has reverse records in DNS
        # and translating back returns set of IP that contains original IP
        modules['resolve3'] = ( 'Resolve', { param="client_address",
                                             type="ip->name->ip" } )
    """

    PARAMS = { 'param': ('which request parameter should be used', None),
               'type': ('ip->name, name->ip, name->mx, ip->name->ip, name->ip->name, ip1->name->ip2, ip->name->mx, name1->ip->name2', None),
               'cachePositive': (None, 24*60*60),
               'cacheUnknown': (None, 30*60),
               'cacheNegative': (None, 6*60*60),
               }


    def start(self):
        for attr in [ 'param', 'type' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        resolveType = self.getParam('type')
        if resolveType not in [ 'ip->name', 'name->ip', 'name->mx', 'ip->name->ip', 'name->ip->name', 'ip1->name->ip2', 'ip->name->mx', 'name1->ip->name2' ]:
            raise ParamError("type \"%s\" is not supported" % resolveType)


    def hashArg(self, data, *args, **keywords):
        param = self.getParam('param')
        return hash("%s=%s" % (param, data.get(param)))


    def check(self, data, *args, **keywords):
        param = self.getParam('param')
        resolveType = self.getParam('type')
        paramValue = data.get(param, [])

        if type(paramValue) == tuple:
            paramValue = list(tuple)
        if type(paramValue) != list:
            paramValue = [ paramValue ]

        if paramValue in [ None, [], [ None ] ]:
            expl = "%s: no test data for %s" % (self.getId(), param)
            logging.getLogger().warn(expl)
            return 0, expl

        for dta in paramValue:
            try:
                if not self.__testResolve(dta, resolveType.lower()):
                    return -1, "%s can't resolve %s or DNS misconfiguration" % (self.getId(), dta)
            except dnscache.DNSCacheError, e:
                logging.getLogger().debug("%s can't resolve %s, DNS error: %s" % (self.getId(), dta, e))
                return -1, "%s can't resolve %s, DNS error" % (self.getId(), dta)

        return 1, "%s resolve ok" % self.getId()


    def __testResolve(self, dta, resType):
        retval = False
        if resType == 'ip->name':
            if len(dnscache.getNameForIp(dta)) > 0:
                retval = True
        elif resType == 'name->ip':
            if len(dnscache.getIpForName(dta)) > 0:
                retval = True
        elif resType == 'name->mx':
            if len(dnscache.getDomainMailhosts(dta, local=False)) > 0:
                retval = True
        elif resType == 'ip->name->ip' or resType == 'ip1->name->ip2' or resType == 'ip->name->mx':
            names = dnscache.getNameForIp(dta)
            if len(names) > 0:
                for name in names:
                    if resType == 'ip->name->mx':
                        ips = dnscache.getDomainMailhosts(name, local=False)
                        if len(ips) > 0: retval = True
                    else:
                        ips = dnscache.getIpForName(name)
                        if resType == 'ip1->name->ip2':
                            if len(ips) > 0: retval = True
                        else:
                            if dta in ips: retval = True
        elif resType == 'name->ip->name' or resType == 'name1->ip->name2':
            ips = dnscache.getIpForName(dta)
            if len(ips) > 0:
                for ip in ips:
                    names = map(lambda x: x.lower(), dnscache.getNameForIp(ip))
                    if resType == 'name1->ip->name2':
                        if len(names) > 0: retval = True
                    else:
                        if dta.lower() in names: retval = True
        return retval
