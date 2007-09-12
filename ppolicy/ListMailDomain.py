#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Check if mail address or its part is in database
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id: ListMailDomain.py 38 2006-05-01 17:51:37Z vokac $
#
import logging
import time
from ListBW import ListBW


__version__ = "$Revision: 38 $"


class ListMailDomain(ListBW):
    """Check mail address or its part is in database. Can be used for
    black/white listing sender or recipient mail addresses.

    Module arguments (see output of getParams method):
    paramMailDomain

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... parameter was found in whitelist, second parameter include selected row
        0 .... parameter was not found in whitelist/blacklist or failed to check
               (request doesn't include required param, database error, ...)
               second parameter - None in case of error
                      not None in case record was not found in b/w list
        1 .... parameter was found in blacklist, second parameter include selected row

    Examples:
        # module for checking if sender is in database b/w list
        modules['list1'] = ( 'ListMailDomain', { paramMailDomain="sender" } )
        # check if sender domain is in database table my_blacklist, my_whitelist
        modules['list2'] = ( 'ListMailDomain', { paramMailDomain="sender",
                                                 tableBlacklist="my_blacklist",
                                                 tableWhitelist="my_whitelist",
                                                 column="my_column",
                                                 retcol="*" } )
    """

    PARAMS = { 'cacheAll': (None, True),
               'cacheAllRefresh': (None, 15*60),
               }


    def __searchList(self, paramValue):
        """This should be compatible with Amavis lookup list
        except we don't care for recipient delimiter '+'
            - lookup for user+foo@example.com
            - lookup for user@example.com (only if $recipient_delimiter is '+')
            - lookup for user+foo (only if domain part is local)
            - lookup for user     (only local; only if $recipient_delimiter is '+')
            - lookup for @example.com
            - lookup for @.example.com
            - lookup for @.com
            - lookup for @.       (catchall)
        """
        searchList = []

        if paramValue == None:
            return []

        if paramValue.rfind('@') != -1:
            user = paramValue[:paramValue.rfind('@')]
            domain = paramValue[paramValue.rfind('@')+1:]
            searchList.append(paramValue)         # user@domain.tld
            searchList.append(user)               # user
            searchList.append("@%s" % domain)     # @domain.tld
            paramValue = domain

        if len(paramValue) == 0:
            return [ '@.' ]

        domain = paramValue.split('.')
        for i in range(0, len(domain)+1):         # @.domainl.tld, @.tld, @.
            searchList.append("@.%s" % ".".join(domain[i:]))

        return searchList


    def check(self, data, *args, **keywords):
        param = self.getParam('param')

        paramValue = str(data.get(param, '')).lower()

        for checkValue in self.__searchList(paramValue):
            ret, retEx = ListBW.check(self, { param: checkValue }, *args, **keywords)
            if ret != 0:
                return ret, retEx

        return 0, None

