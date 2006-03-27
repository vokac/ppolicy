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

    Module arguments (see output of getParams method):
    params, paramsFunction, limitCount, limitTime, limitGran

    Check returns:
        1 .... frequency reached defined limit
        0 .... unrelated error (e.g. database problem)
        -1 ... frequency is acceptable

    Examples:
        # limit number of mail from one sender to 1000/hod
        define('dos1', 'DOS', params="sender")
        # limit number of mail from one sender
        # and one mailserver to 100 in 10 minutes
        define('dos2', 'DOS', params=["sender","client_address"], limitCount=100, limitTime=10)
    """

    PARAMS = { 'params': ('parameters that will be used to test equality', None),
               'paramsFunction': ('function to run on parameter', None),
               'limitCount': ('number of messages accepted during limitTime period', 1000),
               'limitTime': ('time period for limitCount messages', 60*60),
               'limitGran': ('data collection granularity', 10),
               'cachePositive': (None, 0),
               'cacheNegative': (None, 0),
               }


    def start(self):
        params = self.getParam('params')
        if params == None:
            raise ParamError('params has to be specified for this module')

        # normalize parameters
        if type(params) == str:
            params = [ params ]
        elif type(params) == tuple:
            params = list(params)

        paramsFunction = self.getParam('paramsFunction')
        paramsFunct = []
        for i in range(0, len(params)):
            if paramsFunction == None:
                paramsFunct.append((params[i], None))
            else:
                if type(paramsFunction) == str:
                    paramsFunct.append((params[i], paramsFunction))
                elif type(paramsFunction) == list or type(paramsFunction) == tuple:
                    if len(paramsFunction) > i:
                        paramsFunct.append((params[i], paramsFunction[i]))

        self.paramsFunct = paramsFunct
        self.cache = {}


    def stop(self):
        del(self.cache)


    def dataHash(self, data):
        params = self.getParam('params')
        keys = sorted(data.keys())
        return hash("\n".join([ "=".join([x, data[x]]) for x in keys if x in params ]))


    def check(self, data):
        # normalize data and get all possible keys
        dtaArr = {}
        keyArr = []
        for param, paramFunct in self.paramsFunct:
            if paramFunct == None:
                dtaArr[param] = [ data.get(param) ]
            else:
                dtaArr[param] = paramFunct(data.get(param))
            keyArrNew = []
            for dta in dtaArr[param]:
                if len(keyArr) == 0:
                    keyArrNew.append((dta, ))
                else:
                    for key in keyArr:
                        keyArrNew.append(key + (dta, ))
            keyArr = keyArrNew

        # test frequency for all keys
        hasDosKey = False
        for key in keyArr:
            dos = self.__checkDos(key)
            if not hasDosKey and dos:
                hasDosKey = True

        logging.getLogger().debug("%s: size %i" % (self.getId(), len(self.cache)))
        if hasDosKey:
            return 1, "%s: DOS attack treshold reached" % self.getId()
        else:
            return -1, "%s: did not reach DOS treshold" % self.getId()


    def __checkDos(self, key):
        limitCount = int(self.getParam('limitCount'))
        limitTime = int(self.getParam('limitTime'))
        limitGran = int(self.getParam('limitGran'))
        limitInt = limitTime / limitGran

        data, nextUpdate = self.cache.get(key, (None, None))
        if data != None:
            if nextUpdate < time.time():
                sh = long((time.time() - nextUpdate) / limitInt) + 1
                if sh > len(data):
                    data = [ 0 ]
                else:
                    print sh
                    for i in range(0, sh):
                        data.insert(0, 0)
                        if len(data) > limitGran:
                            data.pop()
                nextUpdate = time.time() + limitInt
            # don't increase if we reached DOS treshold,
            # because otherwise it can block such mail forever
            if sum(data) <= limitCount:
                data[0] += 1
        else:
            data = [ 1 ]
            nextUpdate = time.time() + limitInt

        self.cache[key] = (data, nextUpdate)

        return sum(data) > limitCount
