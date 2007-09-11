#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Check if defined parameter is in database
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
import time
import threading
from Base import Base, ParamError


__version__ = "$Revision$"


class List(Base):
    """Check if parameter is in specified database. Can be used for
    black/white listing any of parameter comming with ppolicy requests.

    Module arguments (see output of getParams method):
    param, table, column, retcol, cacheCaseSensitive
    memCacheExpire, memCacheSize, cacheAll, cacheAllRefresh

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... parameter was found in db, second parameter include selected row
        0 .... failed to check (request doesn't include required param,
               database error, ...)
        -1 ... parameter was not found in db

    Examples:
        # module for checking if sender is in database table list
        modules['list1'] = ( 'List', { param="sender" } )
        # check if sender domain is in database table my_list
        # compare case-insensitive and return whole selected row
        modules['list2'] = ( 'List', { param=[ "sender", "recipient" ],
                                       table="my_list",
                                       column=[ "my_column1", "my_column2" ],
                                       cacheCaseSensitive=False,
                                       retcol="*" } )
    """

    PARAMS = { 'param': ('name of parameter in data dictionary (value can be string or array)', None),
               'table': ('name of database table where to search parameter', None),
               'column': ('name of database column or array of columns according "param"', None),
               'retcol': ('name of column returned by check method', None),
               'cacheCaseSensitive': ('case-sensitive cache (set to True if you are using case-sensitive text comparator on DB column', False),
               'memCacheExpire': ('memory cache expiration - used only if param value is array', 15*60),
               'memCacheSize': ('memory cache max size - used only if param value is array', 1000),
               'cacheAll': ('cache all records in memory', False),
               'cacheAllRefresh': ('refresh time in case of caching all records', 15*60),
               }
    DB_ENGINE="ENGINE=InnoDB"
    

    def __retcolSQL(self, retcol):
        retcolSQL = ''

        if retcol == None:
            retcolSQL = 'COUNT(*)'
        elif type(retcol) == type([]):
            retcolSQL = "`%s`" % "`,`".join(retcol)
        elif retcol.find(',') != -1:
            retcolSQL = "`%s`" % "`,`".join(retcol.split(','))
        elif retcol != '*' and retcol.find('(') == -1:
            retcolSQL = "`%s`" % retcol
        else: # *, COUNT(*), AVG(column), ...
            retcolSQL = retcol

        return retcolSQL


    def __cacheAllRefresh(self):
        """This method has to be called from synchronized block."""
        if self.allDataCacheRefresh > time.time():
            return

        column = self.getParam('column')
        cacheCaseSensitive = self.getParam('cacheCaseSensitive', True)

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
                if type(column) == str:
                    cKey = res[len(res)-1]
                    if not cacheCaseSensitive:
                        cKey = cKey.lower()
                    newCache[cKey] = res[:-1]
                else:
                    cKey = res[-len(column):]
                    if not cacheCaseSensitive:
                        cKey = [ x.lower() for x in cKey ]
                    newCache[cKey] = res[:-len(column)]
            cursor.close()

            self.allDataCache = newCache
            self.allDataCacheReady = True
            self.allDataCacheRefresh = time.time() + self.getParam('cacheAllRefresh')
        except Exception, e:
            cursor.close()
            self.allDataCacheReady = False
            self.allDataCacheRefresh = time.time() + 60
            logging.getLogger().error("caching all records failed: %s" % e)


    def getId(self):
        return "%s[%s(%s,%s)]" % (self.type, self.name, self.getParam('table'), str(self.getParam('param')))


    def hashArg(self, data, *args, **keywords):
        cacheCaseSensitive = self.getParam('cacheCaseSensitive', True)
        param = self.getParam('param')
        if type(param) == str:
            param = [ param ]

        paramValue = []
        for par in param:
            parVal = str(data.get(par, ''))
            if cacheCaseSensitive:
                paramValue.append("%s=%s" % (par, parVal))
            else:
                paramValue.append("%s=%s" % (par, parVal.lower()))

        return hash("\n".join(paramValue))


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for attr in [ 'param', 'table', 'column' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        table = self.getParam('table')
        param = self.getParam('param')
        column = self.getParam('column')
        if type(param) != type(column):
            raise ParamError("type of \"param\" (%s) doesn't match type of \"column\" (%s)" % (param, column))
        if type(column) == str:
            column = [ column ]
        retcol = self.getParam('retcol')
        cacheCaseSensitive = self.getParam('cacheCaseSensitive', True)

        self.retcolSQL = self.__retcolSQL(retcol)

        conn = self.factory.getDbConnection()
        try:
            cursor = conn.cursor()
            sql = "CREATE TABLE IF NOT EXISTS `%s` (`%s` VARCHAR(100) NOT NULL, PRIMARY KEY (`%s`)) %s" % (table, "` VARCHAR(100) NOT NULL, `".join(column), "`, `".join(column), List.DB_ENGINE)
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)
            cursor.close()
            conn.commit()
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

            columnSQL = '`%s`' % "`, `".join(column)
            groupBySQL = " GROUP BY `%s`" % "`, `".join(column)
            if self.retcolSQL.find('(') == -1:
                groupBySQL = ''
            self.selectAllSQL = "SELECT %s, %s FROM `%s`%s" % (self.retcolSQL, columnSQL, table, groupBySQL)

            self.allDataCacheLock.acquire()
            try:
                self.__cacheAllRefresh()
            finally:
                self.allDataCacheLock.release()


    def check(self, data, *args, **keywords):
        cacheCaseSensitive = self.getParam('cacheCaseSensitive', True)

        param = self.getParam('param')
        if type(param) == str:
            paramValue = data.get(param, [ '' ])
            if type(paramValue) == str:
                paramValue = [ paramValue ]
            if not cacheCaseSensitiveParam:
                paramValue = [ x.lower() for x in paramValue ]
        else:
            paramVal = []
            paramValLen = -1
            for par in param:
                paramV = data.get(par, [ '' ])
                if type(paramV) == str:
                    paramV = [ paramV ]
                if not cacheCaseSensitiveParam:
                    paramV = [ x.lower() for x in paramV ]
                if paramValLen == -1:
                    paramValLen = len(paramV)
                elif paramValLen != len(paramV):
                    logging.getLogger().error("size of params values is different for %s" % par)
                    return 0, None
                paramVal.append(paramV)
            paramValue = [ () for x in range(0, paramValLen) ]
            for i in range(0, paramValLen):
                for paramV in paramVal:
                    paramValue[i] += ( paramV[i], )

        ret = -1
        retEx = None

        if self.getParam('cacheAll', False):

            self.allDataCacheLock.acquire()
            try:
                self.__cacheAllRefresh()
                if not self.allDataCacheReady:
                    ret = 0
                else:
                    for paramVal in paramValue:
                        retEx = self.allDataCache.get(paramVal)
                        if retEx != None:
                            ret = 1
                            break
            finally:
                self.allDataCacheLock.release()

            return ret, retEx

        table = self.getParam('table')
        column = self.getParam('column')
        retcol = self.getParam('retcol')
        memCacheExpire = self.getParam('memCacheExpire')
        memCacheSize = self.getParam('memCacheSize')
        useMemCache = len(paramValue) > 1 and memCacheExpire != None and memCacheSize != None and memCacheSize > 0

        try:
            conn = self.factory.getDbConnection()
            cursor = conn.cursor()

            for paramVal in paramValue:

                if useMemCache:
                    retEx = self.__getCache(paramVal)
                    if retEx == ():
                        retEx = None
                        continue
                    if retEx == None:
                        ret = 1
                        break

                sqlWhere = ''
                sqlWhereData = []
                if type(column) == str:
                    sqlWhere = "WHERE `%s` = %%s" % column
                    sqlWhereData.append(paramVal)
                else:
                    sqlWhereAnd = []
                    for i in range(0, len(column)):
                        sqlWhereAnd.append("`%s` = %%s" % column[i])
                        sqlWhereData.append(paramVal[i])
                    sqlWhere = "WHERE %s" % " AND ".join(sqlWhereAnd)

                sql = "SELECT %s FROM `%s` %s" % (self.retcolSQL, table, sqlWhere)

                if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                    logging.getLogger().debug("SQL: %s %s" % sql, str(list(sqlWhereData)))
                cursor.execute(sql, list(sqlWhereData))

                if int(cursor.rowcount) > 0:
                    retEx = cursor.fetchone()
                    if retcol != None or (retcol == None and retEx[0] > 0):
                        ret = 1
                        if useMemCache:
                            self.__setCache(paramVal, retEx)
                        break

                if useMemCache:
                    self.__setCache(paramVal, ())

            cursor.close()
            conn.commit()
        except Exception, e:
            try:
                cursor.close()
            except:
                pass
            logging.getLogger().error("%s: database error %s" % (self.getId(), e))
            return 0, None

        return ret, retEx


    def __getCache(self, key):
        ret = None

        self.lock.acquire()
        try:
            (ret, expire) = self.cache.get(key, (None, 0))
            if time.time() > expire:
                del(self.cache[key])
                ret = None
        finally:
            self.lock.release()

        return ret


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
