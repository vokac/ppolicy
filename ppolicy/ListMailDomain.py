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
from Base import Base, ParamError


__version__ = "$Revision: 38 $"


class ListMailDomain(Base):
    """Check mail address or its part is in database. Can be used for
    black/white listing sender or recipient mail addresses.

    Module arguments (see output of getParams method):
    param, table, column

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... parameter was found in db
        0 .... failed to check (request doesn't include required param, database error, ...)
        -1 ... parameter was not found in db

    Examples:
        # module for checking if sender is in database table list
        modules['list1'] = ( 'ListMailDomain', { param="sender" } )
        # check if sender domain is in database table my_list
        modules['list2'] = ( 'ListMailDomain', { param="sender", table="my_list" } )
    """

    PARAMS = { 'param': ('name of parameter to search in database', None),
               'table': ('name of database table where to search parameter', 'list_mail_domain'),
               'column': ('name of database column', 'mail'),
               }

    MAX_CACHE_SIZE = 1000

    def getId(self):
        return "%s[%s(%s,%s)]" % (self.type, self.name, self.getParam('table'), self.getParam('param'))


    def hashArg(self, data, *args, **keywords):
        param = self.getParam('param')
        return hash("=".join([ param, data.get(param, '') ]))


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for attr in [ 'param', 'table', 'column' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        table = self.getParam('table')
        column = self.getParam('column')

        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        sql = "CREATE TABLE IF NOT EXISTS `%s` (`%s` VARCHAR(255) NOT NULL, PRIMARY KEY (`%s`))" % (table, column, column)
        logging.getLogger().debug("SQL: %s" % sql)
        cursor.execute(sql)
        cursor.close()

        self.lock = threading.Lock()
        self.cache = {}


    def check(self, data, *args, **keywords):
        param = self.getParam('param')
        table = self.getParam('table')
        column = self.getParam('column')
        paramValue = data.get(param, '').lower()

        retEx = None
        try:
            conn = self.factory.getDbConnection()
            cursor = conn.cursor()

            searchList = []
            if paramValue.find('@') != -1:
                user, domain = paramValue.split('@', 2)
                searchList.append(paramValue)
                searchList.append("%s@" % user)
                paramValue = domain

            domain = paramValue.split('.')
            for i in range(0, len(domain)+1):
                searchList.append(".%s" % ".".join(domain[i:]))

            conn = self.factory.getDbConnection()
            cursor = conn.cursor()

            for key in searchList:
                retEx = self.__getCache(key)
                if retEx == ():
                    retEx = None
                    continue
                if retEx != None:
                    break
                sql = "SELECT * FROM `%s` WHERE `%s` = '%s'" % (table, column, key)
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
                if int(cursor.rowcount) > 0:
                    retEx = cursor.fetchone()
                    self.__setCache(key, retEx)
                    break
                else:
                    self.__setCache(key, ())

            cursor.close()
        except Exception, e:
            cursor.close()
            logging.getLogger().error("%s database error: %s" % (self.getId(), e))
            return 0, retEx

        if retEx != None: return 1, retEx
        else: return -1, retEx


    def __getCache(self, key):
        retVal = None
        self.lock.acquire()
        try:
            retVal = self.cache.get(key)
        finally:
            self.lock.release()
        return retVal


    def __setCache(self, key, value):
        self.lock.acquire()
        try:
            # XXXXX: cache expiration?
            if len(self.cache) > ListMailDomain.MAX_CACHE_SIZE:
                self.cache.clear()
            self.cache[key] = value
        finally:
            self.lock.release()
