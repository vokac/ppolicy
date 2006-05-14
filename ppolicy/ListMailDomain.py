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
        1 .... parameter was found in db, second parameter contain
               database row that was selected
        0 .... failed to check (request doesn't include required param, database error, ...)
        -1 ... parameter was not found in db

    Examples:
        # module for checking if sender is in database table list
        modules['list1'] = ( 'ListMailDomain', { param="sender" } )
        # check if sender domain is in database table my_list
        modules['list2'] = ( 'ListMailDomain', { param="sender",
                                                 table="my_list",
                                                 column="my_column",
                                                 retcol="*" } )
    """

    PARAMS = { 'param': ('name of parameter to search in database', None),
               'table': ('name of database table where to search parameter', 'list_mail_domain'),
               'column': ('name of database column', 'mail'),
               'retcol': ('name of column returned by check method', None),
               'memCacheExpire': ('memory cache expiration', 15*60),
               'memCacheSize': ('memory cache max size', 1000),
               'cacheAll': ('cache all records in memory', False),
               'cacheAllRefresh': ('refresh time in case of caching all records', 15*60),
               }


    def __cacheAllRefresh(self):
        """This method has to be called from synchronized block."""
        if self.allDataCacheRefresh > time.time():
            return

        conn = self.factory.getDbConnection()
        try:
            newCache = {}
            cursor = conn.cursor()

            sql = self.selectAllSQL
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)
            logging.getLogger().info("cached %s records for %ss" % (int(cursor.rowcount), self.getParam('cacheAllRefresh')))
            while True:
                res = cursor.fetchone()
                if res == None:
                    break
                newCache[res[len(res)-1]] = res[:-1]
            cursor.close()

            self.allDataCache = newCache
            self.allDataCacheReady = True
            self.allDataCacheRefresh = time.time() + self.getParam('cacheAllRefresh')
        except Exception, e:
            cursor.close()
            self.allDataCacheReady = False
            self.allDataCacheRefresh = time.time() + 60
            logging.getLogger().error("caching all records failed: %s" % e)


    def __searchList(self, paramValue):
        searchList = []

        if paramValue.find('@') != -1:
            user, domain = paramValue.split('@', 2)
            searchList.append(paramValue)
            searchList.append("%s@" % user)
            paramValue = domain

        domain = paramValue.split('.')
        for i in range(0, len(domain)+1):
            searchList.append(".%s" % ".".join(domain[i:]))

        return searchList


    def getId(self):
        return "%s[%s(%s,%s)]" % (self.type, self.name, self.getParam('table'), self.getParam('param'))


    def hashArg(self, data, *args, **keywords):
        param = self.getParam('param')
        paramValue = data.get(param, '').lower()
        return hash("%s=%s" % (param, paramValue))


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for attr in [ 'param', 'table', 'column', 'memCacheExpire', 'memCacheSize' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        table = self.getParam('table')
        column = self.getParam('column')
        retcol = self.getParam('retcol')

        if retcol == None:
            self.retcolSQL = 'COUNT(*)'
        elif type(retcol) == type([]):
            self.retcolSQL = "`%s`" % "`,`".join(retcol)
        elif retcol.find(',') != -1:
            self.retcolSQL = "`%s`" % "`,`".join(retcol.split(','))
        elif retcol != '*' and retcol.find('(') == -1:
            self.retcolSQL = "`%s`" % retcol
        else: # *, COUNT(*), AVG(column), ...
            self.retcolSQL = retcol

        conn = self.factory.getDbConnection()
        try:
            cursor = conn.cursor()
            sql = "CREATE TABLE IF NOT EXISTS `%s` (`%s` VARCHAR(255) NOT NULL, PRIMARY KEY (`%s`))" % (table, column, column)
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)
            cursor.close()
        except Exception, e:
            cursor.close()
            raise e

        if not self.getParam('cacheAll', False):
            self.lock = threading.Lock()
            self.cache = {}
        else:
            self.allDataCache = {}
            self.allDataCacheReady = False
            self.allDataCacheRefresh = 0
            self.allDataCacheLock = threading.Lock()

            self.setParam('cachePositive', 0) # don't use global result
            self.setParam('cacheUnknown', 0)  # cache when all records
            self.setParam('cacheNegative', 0) # are cached by this module

            if self.retcolSQL.find('(') != -1:
                groupBySQL = " GROUP BY `%s`" % column
            else:
                groupBySQL = ''
            self.selectAllSQL = "SELECT %s, LOWER(`%s`) FROM `%s`%s" % (self.retcolSQL, column, table, groupBySQL)

            self.allDataCacheLock.acquire()
            try:
                self.__cacheAllRefresh()
            finally:
                self.allDataCacheLock.release()


    def check(self, data, *args, **keywords):
        param = self.getParam('param')
        paramValue = data.get(param, '').lower()

        if self.getParam('cacheAll', False):
            ret = -1
            retEx = None

            self.allDataCacheLock.acquire()
            try:
                self.__cacheAllRefresh()
                if not self.allDataCacheReady:
                    ret = 0
                else:
                    for key in self.__searchList(paramValue):
                        retEx = self.allDataCache.get(key)
                        if retEx != None:
                            ret = 1
                            break
            finally:
                self.allDataCacheLock.release()

            return ret, retEx

        table = self.getParam('table')
        column = self.getParam('column')
        retcol = self.getParam('retcol')

        retEx = None
        try:
            conn = self.factory.getDbConnection()
            cursor = conn.cursor()

            for key in self.__searchList(paramValue):
                retEx = self.__getCache(key)
                if retEx == ():
                    retEx = None
                    continue
                if retEx != None:
                    break

                sql = "SELECT %s FROM `%s` WHERE `%s` = '%s'" % (self.retcolSQL, table, column, key)

                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)

                if int(cursor.rowcount) > 0:
                    retEx = cursor.fetchone()
                    if retcol != None or (retcol == None and retEx[0] > 0):
                        self.__setCache(key, retEx)
                        break
                    else:
                        retEx = None
                        self.__setCache(key, ())
                else:
                    self.__setCache(key, ())

            cursor.close()
        except Exception, e:
            try:
                cursor.close()
            except:
                pass
            logging.getLogger().error("%s database error: %s" % (self.getId(), e))
            return 0, None

        if retEx != None:
            return 1, retEx
        else:
            return -1, None


    def __getCache(self, key):
        retVal = None

        self.lock.acquire()
        try:
            (retVal, expire) = self.cache.get(key, (None, 0))
            if time.time() > expire:
                retVal = None
        finally:
            self.lock.release()

        return retVal


    def __setCache(self, key, value):
        expire = time.time() + self.getParam('memCacheExpire')
        memCacheSize = self.getParam('memCacheSize')

        self.lock.acquire()
        try:
            if len(self.cache) > memCacheSize:
                self.cache.clear()
            self.cache[key] = (value, expire)
        finally:
            self.lock.release()
