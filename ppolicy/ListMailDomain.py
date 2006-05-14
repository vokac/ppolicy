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
import threading
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

    PARAMS = { 'paramMailDomain': ('parameter with mail/domain to check', None),
               'param': (None, None),           # defined in start method
               'tableBlacklist': (None, 'blacklist'),
               'tableWhitelist': (None, 'whitelist'),
               'column': (None, 'key'),
               'caseSensitive': (None, False),  # don't use LOWER(`key`),
               'caseSensitiveDB': (None, True), # because of index performance
               'cacheAll': (None, True),
               'cacheAllRefresh': (None, 15*60),
               }


    def __searchList(self, paramValue):
        searchList = []

        if paramValue.find('@') != -1:
            user, domain = paramValue.split('@', 1)
            searchList.append(paramValue)
            searchList.append("%s@" % user)
            paramValue = domain

        domain = paramValue.split('.')
        for i in range(0, len(domain)+1):
            searchList.append(".%s" % ".".join(domain[i:]))

        return searchList


    def getId(self):
        return "%s[%s(%s)]" % (self.type, self.name, self.getParam('paramMailDomain'))


    def hashArg(self, data, *args, **keywords):
        param = self.getParam('paramMailDomain')
        paramValue = data.get(param, '')
        if type(paramValue) != str:
            logging.getLogger().error("parameter is not string: %s" % str(paramValue))
            return 0

        return hash("%s=%s" % (param, paramValue.lower()))


    def start(self):
        param = self.getParam('paramMailDomain')
        self.setParam('param', "%s_list_mail_domain" % param)

        ListBW.start(self)


    def check(self, data, *args, **keywords):
        param = self.getParam('paramMailDomain')
        paramValue = data.get(param, '')
        if type(paramValue) != str:
            logging.getLogger().error("parameter is not string: %s" % str(paramValue))
            return 0, None

        param = self.getParam('param')
        data[param] = paramValue.lower()

        return ListBW.check(self, data, *args, **keywords)
