#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# This module check SPF records
# http://www.openspf.org/
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
from Base import Base
from tools import spf


__version__ = "$Revision$"


class SPF(Base):
    """This module use sender address and client IP and check SPF
    records in DNS if they are exist. It can run in permissive or
    restrictive mode. Permissive mode is default and recomended for
    general usage. Restrictive marks too many correct mail and should
    be used only in special cases when you really know what you are
    doing...

    More informations about SPF can be found at following address
    http://www.openspf.org
    http://en.wikipedia.org/wiki/Sender_Policy_Framework

    Module arguments (see output of getParams method):
    restrictive

    Check returns:
        1 .... SPF passed
        0 .... exception checking SPF (unknown result
        -1 ... SPF failed

    Examples:
        # define module for checking SPF
        define('spf1', 'SPF')
        # define module for checking SPF in restrictive mode
        define('spf1', 'SPF', restrictive=True)
    """

    PARAMS = { 'restrictive': ('very strict SPF checking, be very carefull setting to True', False),
               }


    def getId(self):
        return "%s[%s(%s)]" % (self.type, self.name, self.getParam('restrictive'))


    def dataHash(self, data):
        return hash("\n".join(map(lambda x: "%s=%s" % (x, data.get(x)), [ 'sender', 'client_address', 'client_name' ])))


    def check(self, data):
        """ check Request against SPF results in 'deny', 'unknown', 'pass'"""
        sender = data.get('sender')
        client_address = data.get('client_address')
        client_name = data.get('client_name')
        if len(sender) > 0 and sender[0] == '<': sender = sender[1:]
        if len(sender) > 0 and sender[-1] == '>': sender = sender[:-1]

        try:
            logging.getLogger().debug("%s: spf.check('%s', '%s', '%s')" %
                                      (self.getId(), client_address, sender, client_name))
            result, mtastatus, mtaexpl = spf.check(i=client_address,
                                                   s=sender, h=client_name)
            logging.getLogger().debug("%s: result: %s, %s, %s" %
                                      (self.getId(), result, mtastatus, mtaexpl))
        except Exception, error:
            logging.getLogger().error("%s: checking SPF failed: %s" %
                                      (self.getId(), error))
            return 0, 'SPF check error'

        if self.getParam('restrictive'):
            if result.lower() == 'unknown':
                return -1, 'SPF Policy violation'
            else:
                return 1, mtaexpl
        else:
            if result.lower() != 'deny':
                return 1, 'SPF Policy success'
            else:
                return -1, mtaexpl
