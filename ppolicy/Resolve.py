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
    """Try to resolve ip->name, name->ip, ip->name->ip, name->ip->name.

    Module arguments (see output of getParams method):
    param, paramFunction, type

    Check returns:
        1 .... all tranlation were successfull and equal
        0 .... problem resolving ip or name (DNS error)
        -1 ... translation failed

    Examples:
        # check if sender domain exist
        define('resolve1', 'Resolve', param="sender", paramFunction="mailToDomain", type="name->ip")
        # check if remote mailserver has reverse records in DNS
        define('resolve2', 'Resolve', param="client_address", type="ip->name")
        # check if remote mailserver has reverse records in DNS
        # and translating back returns set of IP that contains original IP
        define('resolve3', 'Resolve', param="client_address", type="ip->name->ip")
    """

    PARAMS = { 'param': ('which request parameter should be used', None),
               'paramFunction': ('change parameter value with this function', None),
               'type': ('ip->name, name->ip, ip->name->ip, name->ip->name', None),
               }


    def start(self):
        for attr in [ 'param', 'type' ]:
            if self.getParam(attr) == None:
                raise ParamError("%s has to be specified for this module" % attr)


    def dataHash(self, data):
        param = self.getParam('param')
        return hash("%s=%s" % (param, data.get(param)))


    def check(self, data):
        param = self.getParam('param')
        paramFunction = self.getParam('paramFunction')
        resolveType = self.getParam('type')

        if paramFunction == None:
            dtaArr = [ data.get(param) ]
        else:
            dtaArr = paramFunction(data.get(param))

        if dtaArr in [ None, [], [ None ] ]:
            expl = "%s: no test data for %s" % (self.getId(), param)
            logging.getLogger().warn(expl)
            return 0, expl

        for dta in dtaArr:
            if not self.__testResolve(dta, resolveType.lower()):
                return -1, "%s can't resolve %s or DNS misconfiguration" % (self.getId(), dta)

        return 1, "%s resolve ok" % self.getId()


    def __testResolve(self, dta, resType):
        retval = False
        if resType == 'ip->name':
            if dnscache.getNameForIp(dta) != None:
                retval = True
        elif resType == 'name->ip':
            if dnscache.getIpForName(dta) != None:
                retval = True
        elif resType == 'ip->name->ip':
            names = dnscache.getNameForIp(dta)
            if names != None:
                for name in names:
                    ips = dnscache.getIpForName(name)
                    if ips != None and dta in ips:
                        retval = True
        elif resType == 'name->ip->name':
            ips = dnscache.getIpForName(dta)
            if ips != None:
                for ip in ips:
                    names = map(lambda x: x.lower(), dnscache.getNameForIp(ip))
                    if names != None and dta.lower() in names:
                        retval = True
        return retval
