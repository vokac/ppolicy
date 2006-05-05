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
    """This module use sender address and client IP to check SPF
    records in DNS if they are exist.

    More informations about SPF can be found at following address
    http://www.openspf.org
    http://en.wikipedia.org/wiki/Sender_Policy_Framework

    Module arguments (see output of getParams method):

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... SPF passed, second parameter contain values returned
               by tools.spf function (result, status, explanation)
        0 .... undefined SPF records or exception when checking SPF
        -1 ... SPF failed
        

    Examples:
        # define module for checking SPF
        modules['spf1'] = ( 'SPF', {} )
    """

    PARAMS = { }


    def hashArg(self, data, *args, **keywords):
        return hash("\n".join(map(lambda x: "%s=%s" % (x, data.get(x, '').lower()), [ 'sender', 'client_address', 'client_name' ])))


    def check(self, data, *args, **keywords):
        """ check Request against SPF results in 'deny', 'unknown', 'pass'"""
        sender = data.get('sender', '').lower()
        client_address = data.get('client_address')
        client_name = data.get('client_name', '').lower()

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
            return 0, None


        if result.lower() == 'deny':
            return -1, (result, mtastatus, mtaexpl)
        if result.lower() == 'pass':
            return 1, (result, mtastatus, mtaexpl)

        return 0, (result, mtastatus, mtaexpl)
