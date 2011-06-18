#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Limit rate of requests according equality of specified parameter
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
import time
from Base import Base, ParamError


__version__ = "$Revision$"


class DOS(Base):
    """Limit number of incomming mail that has same parameters. You
    can e.g. limit number of messages that can be accepted by one
    recipient from one sender in defined period of time. It will
    divide time interval into several parts and agregate information
    about number of incomming mails. Be carefull setting this module,
    because badly choosed parameters can exhause a lot of memory.

    Some mail should not be blocked (e.g. to postmaster@your.domain.com,
    from <>, ...) and your configuration should take care of it.

    Module arguments (see output of getParams method):
    params, limitCount, limitTime, limitGran

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... frequency reached defined limit
        0 .... unrelated error (e.g. database problem)
        -1 ... frequency is acceptable

    Examples:
        # limit number of mail from one sender to 1000/hod
        modules['dos1'] = ( 'DOS', { 'params': "sender" } )
        # limit number of mail from one sender
        # and one mailserver to 100 in 10 minutes
        modules['dos2'] = ( 'DOS', { 'params': ["sender","client_address"],
                            'limitCount': 100, 'limitTime': 10 } )
    """

    PARAMS = { 'params': ('parameters that will be used to test equality', None),
               'limitCount': ('number of messages accepted during limitTime period', 1000),
               'limitTime': ('time period for limitCount messages', 60*60),
               'limitGran': ('data collection granularity', 10),
               'perRecipient': ('limit computed for each recipient (False make sense only in "DATA" and "END-OF-MESSAGE" stages)', True),
               'caseSensitive': ('case sensitive parameters', False),
               'countOver': ('count messages even we reached given limitCount', False),
               'cachePositive': (None, 0),
               'cacheUnknown': (None, 0),
               'cacheNegative': (None, 0),
               }
    PERSIST_VERSION = 1
    PERSIST_DATA = [ 'cache' ]

    def start(self):
        params = self.getParam('params')
        if params == None:
            raise ParamError('params has to be specified for this module')

        # normalize parameters
        if type(params) == str:
            params = [ params ]
        elif type(params) == tuple:
            params = list(params)
        self.setParam('params', params)

        self.cache = {}


    def stop(self):
        self.cache = {}


    def hashArg(self, data, *args, **keywords):
        params = self.getParam('params')
        hashKey = "\n".join([ "=".join([x, data.get(x, '')]) for x in params ])
        if bool(self.getParam('caseSensitive')):
            return hash(hashKey)
        else:
            return hash(hashKey.lower())


    def check(self, data, *args, **keywords):
        # normalize data and get all possible keys
        params = self.getParam('params')
        limitCount = int(self.getParam('limitCount'))

        # create all parameter combinations (cartesian product)
        valX = []
        for param in params:
            paramVal = data.get(param, '')
            if type(paramVal) == tuple:
                paramVal = list(tuple)
            if type(paramVal) != list:
                paramVal = [ paramVal ]
            if len(paramVal) == 0:
                paramVal = [ '' ]
            if len(valX) == 0:
                for val in paramVal:
                    valX.append([(param, val)])
            else:
                valXnew = []
                for pX in valX:
                    for val in paramVal:
                        valXnew.append(pX + [(param, val)])
                valX = valXnew

        perRecipient = bool(self.getParam('perRecipient'))
        incNum = 1.
        if not perRecipient and int(data.get('recipient_count', 1)) > 0:
            incNum = 1. / int(data.get('recipient_count', 1))

        # test frequency for all keys
        ddetail = []
        hasDosKey = False
        for paramsVal in valX:
            keyStr = "\n".join([ "%s=%s" % (x,y) for x,y in paramsVal ])
            key = hash(keyStr)
            if not bool(self.getParam('caseSensitive')):
                key = hash(keyStr.lower())
            hitsum = self.__checkDos(key, incNum)
            ddetail.append((key, hitsum))
            if not hasDosKey and hitsum > limitCount:
                hasDosKey = True

        logging.getLogger().debug("%s: size %i" % (self.getId(), len(self.cache)))
        if hasDosKey:
            return 1, ddetail
        else:
            return -1, ddetail


    def __checkDos(self, key, incNum = 1.):
        limitCount = int(self.getParam('limitCount'))
        limitTime = int(self.getParam('limitTime'))
        limitGran = int(self.getParam('limitGran'))
        limitInt = int(limitTime / limitGran)
        countOver = bool(self.getParam('countOver'))

        if self.cache.has_key(key):
            data, nextUpdate = self.cache.get(key, (None, None))
            if nextUpdate < time.time():
                sh = long((time.time() - nextUpdate) / limitInt) + 1
                if sh > len(data):
                    data = [ 0 ]
                else:
                    for i in range(0, sh):
                        data.insert(0, 0)
                        if len(data) > limitGran:
                            data.pop()
                nextUpdate = time.time() + limitInt
            # don't increase if we reached DOS treshold,
            # because otherwise it can block such mail forever
            if countOver or sum(data) <= limitCount:
                data[0] += incNum
        else:
            data = [ incNum ]
            nextUpdate = time.time() + limitInt

        self.cache[key] = (data, nextUpdate)

        return sum(data)
