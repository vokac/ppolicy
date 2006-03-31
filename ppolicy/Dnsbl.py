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
from Base import Base


__version__ = "$Revision$"


class Dnsbl(Base):
    """Check if client address is listed in specified DNS blacklist.
    !!! This module is not yet finished !!!

    Module arguments (see output of getParams method):
    name

    Check arguments:
        None

    Check returns:
        1 .... listed in dnsbl
        0 .... unknown error (e.g. DNS problems)
        -1 ... not listed

    Examples:
        # check if sender mailserver is in ORDB blacklist
        define('dnsbl1', 'Dnsbl', name="ORDB")
    """

    PARAMS = { 'name': ('name of DNS blacklist defined in this module', None),
               }


    def hashArg(self, *args, **keywords):
        client_address = args[0]
        return hash("client_address=%s" % client_address)


    def check(self, *args, **keywords):
        client_address = args[0]

#        if dnsbl.check(client_address, self.dns, self.type, self.retval):
#            return 1, "%s blacklisted in %s" % (client_address, self.dns)
#        else:
#            return -1, "%s is not in %s blacklist" % (client_address, self.dns)

        return 0, 'not implemented'
