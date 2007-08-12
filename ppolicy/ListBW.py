#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Check if array of defined parameters are in blacklist/whitelist
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id: ListBW.py 46 2006-05-09 21:20:49Z vokac $
#
import logging
import time
import threading
from Base import Base, ParamError


__version__ = "$Revision: 46 $"


class ListBW(Base):
    """Check if array of defined parameters are in blacklist/whitelist.
    Each parameter is searched in b/w list and first occurence is returned.

    Module arguments (see output of getParams method):
    param, tableBlacklist, tableWhitelist, column, columnBlacklist,
    columnWhitelist, caseSensitive, caseSensitiveParam,
    caseSensitiveDB, retcol, retcolWhitelist, retcolBlacklist,
    memCacheExpire, memCacheSize, cacheAll, cacheAllRefresh

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
        # module for checking if sender is in blacklist/whitelist
        modules['list1'] = ( 'ListBW', { param="sender_splitted" } )
        # check if sender in blacklist/whitelist
        # compare case-insensitive and return whole selected row
        modules['list2'] = ( 'ListBW', { param="sender_splitted",
                                         tableBlacklist="my_blacklist",
                                         tableWhitelist="my_whitelist",
                                         column="my_column",
                                         caseSensitive=False,
                                         caseSensitiveDB=True,
                                         retcol="*" } )
    """

    PARAMS = { 'param': ('name of parameter in data dictionary (value can be string or array)', None),
               'tableBlacklist': ('name of blacklist database table where to search parameter', None),
               'tableWhitelist': ('name of whitelist database table where to search parameter', None),
               'column': ('name of database column', None),
               'columnBlacklist': ('name of blacklist database column', None),
               'columnWhitelist': ('name of whitelist database column', None),
               'retcol': ('name of column returned by check method', None),
               'retcolBlacklist': ('name of blacklist column returned by check method', None),
               'retcolWhitelist': ('name of whitelist column returned by check method', None),
               'caseSensitive': ('case-sensitive search', True),
               'caseSensitiveParam': ('case-sensitive search - convert param to lowercase', None),
               'caseSensitiveDB': ('case-sensitive search - use SQL function LOWER', None),
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

        tableWhitelist = self.getParam('tableWhitelist')
        tableBlacklist = self.getParam('tableBlacklist')

        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        try:
            newCacheWhitelist = {}
            newCacheBlacklist = {}

            if tableWhitelist != None:
                sql = self.selectAllSQLWhitelist
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
                logging.getLogger().info("whitelist cached %s records for %ss" % (int(cursor.rowcount), self.getParam('cacheAllRefresh')))
                while True:
                    res = cursor.fetchone()
                    if res == None:
                        break
                    newCacheWhitelist[res[len(res)-1]] = res[:-1]

            if tableBlacklist != None:
                sql = self.selectAllSQLBlacklist
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
                logging.getLogger().info("blacklist cached %s records for %ss" % (int(cursor.rowcount), self.getParam('cacheAllRefresh')))
                while True:
                    res = cursor.fetchone()
                    if res == None:
                        break
                    newCacheBlacklist[res[len(res)-1]] = res[:-1]

            cursor.close()
            conn.commit()

            self.allDataCacheWhitelist = newCacheWhitelist
            self.allDataCacheBlacklist = newCacheBlacklist
            self.allDataCacheReady = True
            self.allDataCacheRefresh = time.time() + self.getParam('cacheAllRefresh')
        except Exception, e:
            cursor.close()
            self.allDataCacheReady = False
            self.allDataCacheRefresh = time.time() + 60
            logging.getLogger().error("caching all records failed: %s" % e)
        #self.factory.releaseDbConnection(conn)


    def getId(self):
        return "%s[%s(%s)]" % (self.type, self.name, self.getParam('param'))


    def hashArg(self, data, *args, **keywords):
        param = self.getParam('param')
        caseSensitive = self.getParam('caseSensitive', True)
        caseSensitiveParam = self.getParam('caseSensitiveParam', caseSensitive)

        paramValue = str(data.get(param, ''))
        if not caseSensitiveParam:
            paramValue = paramValue.lower()

        return hash("%s=%s" % (param, paramValue))


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for attr in [ 'param' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        tableWhitelist = self.getParam('tableWhitelist')
        tableBlacklist = self.getParam('tableBlacklist')
        column = self.getParam('column')
        columnWhitelist = self.getParam('columnWhitelist', column)
        columnBlacklist = self.getParam('columnBlacklist', column)
        retcol = self.getParam('retcol')
        retcolWhitelist = self.getParam('retcolWhitelist', retcol)
        retcolBlacklist = self.getParam('retcolBlacklist', retcol)
        caseSensitive = self.getParam('caseSensitive', True)
        #caseSensitiveParam = self.getParam('caseSensitiveParam', caseSensitive)
        caseSensitiveDB = self.getParam('caseSensitiveDB', caseSensitive)

        self.retcolSQLWhitelist = self.__retcolSQL(retcolWhitelist)
        self.retcolSQLBlacklist = self.__retcolSQL(retcolBlacklist)

        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        try:
            if tableWhitelist != None:
                sql = "CREATE TABLE IF NOT EXISTS `%s` (`%s` VARCHAR(100) NOT NULL, PRIMARY KEY (`%s`)) %s" % (tableWhitelist, columnWhitelist, columnWhitelist, ListBW.DB_ENGINE)
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
            if tableBlacklist != None:
                sql = "CREATE TABLE IF NOT EXISTS `%s` (`%s` VARCHAR(100) NOT NULL, PRIMARY KEY (`%s`)) %s" % (tableBlacklist, columnBlacklist, columnBlacklist, ListBW.DB_ENGINE)
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
            cursor.close()
            conn.commit()
        except Exception, e:
            cursor.close()
            raise e
        #self.factory.releaseDbConnection(conn)

        if not self.getParam('cacheAll', False):
            self.lock = threading.Lock()
            self.cache = {}
        else:
            self.allDataCacheWhitelist = {}
            self.allDataCacheBlacklist = {}
            self.allDataCacheReady = False
            self.allDataCacheRefresh = 0
            self.allDataCacheLock = threading.Lock()

            self.setParam('cachePositive', 0) # don't use global result
            self.setParam('cacheUnknown', 0)  # cache when all records
            self.setParam('cacheNegative', 0) # are cached by this module

            if not caseSensitiveDB:
                columnSQLWhitelist = 'LOWER(`%s`)' % columnWhitelist
                columnSQLBlacklist = 'LOWER(`%s`)' % columnBlacklist
                groupBySQLWhitelist = " GROUP BY LOWER(`%s`)" % columnWhitelist
                groupBySQLBlacklist = " GROUP BY LOWER(`%s`)" % columnBlacklist
            else:
                columnSQLWhitelist = '`%s`' % columnWhitelist
                columnSQLBlacklist = '`%s`' % columnBlacklist
                groupBySQLWhitelist = " GROUP BY `%s`" % columnWhitelist
                groupBySQLBlacklist = " GROUP BY `%s`" % columnBlacklist
            if self.retcolSQLWhitelist.find('(') == -1:
                groupBySQLWhitelist = ''
            if self.retcolSQLBlacklist.find('(') == -1:
                groupBySQLBlacklist = ''
            if tableWhitelist != None:
                self.selectAllSQLWhitelist = "SELECT %s, %s FROM `%s`%s" % (self.retcolSQLWhitelist, columnSQLWhitelist, tableWhitelist, groupBySQLWhitelist)
            if tableBlacklist != None:
                self.selectAllSQLBlacklist = "SELECT %s, %s FROM `%s`%s" % (self.retcolSQLBlacklist, columnSQLBlacklist, tableBlacklist, groupBySQLBlacklist)

            self.allDataCacheLock.acquire()
            try:
                self.__cacheAllRefresh()
            finally:
                self.allDataCacheLock.release()


    def check(self, data, *args, **keywords):
        param = self.getParam('param')
        paramValue = data.get(param, [ '' ])
        if type(paramValue) == str:
            paramValue = [ paramValue ]

        caseSensitive = self.getParam('caseSensitive', True)
        caseSensitiveParam = self.getParam('caseSensitiveParam', caseSensitive)
        caseSensitiveDB = self.getParam('caseSensitiveDB', caseSensitive)

        if not caseSensitiveParam:
            paramValue = [ x.lower() for x in paramValue ]

        ret = 0
        retEx = None

        if self.getParam('cacheAll', False):

            self.allDataCacheLock.acquire()
            try:
                self.__cacheAllRefresh()
                if not self.allDataCacheReady:
                    ret = 0
                else:
                    for paramVal in paramValue:
                        retEx = self.allDataCacheWhitelist.get(paramVal)
                        if retEx != None:
                            ret = 1
                            break
                        retEx = self.allDataCacheBlacklist.get(paramVal)
                        if retEx != None:
                            ret = -1
                            break

                if ret == 0:
                    retEx = ()

            finally:
                self.allDataCacheLock.release()

            return ret, retEx

        tableWhitelist = self.getParam('tableWhitelist')
        tableBlacklist = self.getParam('tableBlacklist')
        column = self.getParam('column')
        columnWhitelist = self.getParam('columnWhitelist', column)
        columnBlacklist = self.getParam('columnBlacklist', column)
        retcol = self.getParam('retcol')
        retcolWhitelist = self.getParam('retcolWhitelist', retcol)
        retcolBlacklist = self.getParam('retcolBlacklist', retcol)
        memCacheExpire = self.getParam('memCacheExpire')
        memCacheSize = self.getParam('memCacheSize')
        useMemCache = type(data.get(param, '')) != str and memCacheExpire != None and memCacheSize != None and memCacheSize > 0

        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        try:

            for paramVal in paramValue:

                if useMemCache:
                    ret, retEx = self.__getCache(paramVal)
                    if ret != None:
                        if retEx == None:
                            continue
                    else:
                        ret = 0

                if tableWhitelist != None:
                    if not caseSensitiveDB:
                        sqlWhere = "WHERE LOWER(`%s`) = LOWER('%s')" % (columnWhitelist, paramVal)
                    else:
                        sqlWhere = "WHERE `%s` = '%s'" % (columnWhitelist, paramVal)
                    sql = "SELECT %s FROM `%s` %s" % (self.retcolSQLWhitelist, tableWhitelist, sqlWhere)

                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)

                    if int(cursor.rowcount) > 0:
                        retEx = cursor.fetchone()
                        if retcolWhitelist != None or (retcolWhitelist == None and retEx[0] > 0):
                            ret = 1
                            if useMemCache:
                                self.__setCache(paramVal, (ret, retEx))
                            break
                        else:
                            retEx = None

                if tableBlacklist != None:
                    if not caseSensitiveDB:
                        sqlWhere = "WHERE LOWER(`%s`) = LOWER('%s')" % (columnBlacklist, paramVal)
                    else:
                        sqlWhere = "WHERE `%s` = '%s'" % (columnBlacklist, paramVal)
                    sql = "SELECT %s FROM `%s` %s" % (self.retcolSQLBlacklist, tableBlacklist, sqlWhere)

                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)
                    
                    if int(cursor.rowcount) > 0:
                        retEx = cursor.fetchone()
                        if retcolBlacklist != None or (retcolBlacklist == None and retEx[0] > 0):
                            ret = -1
                            if useMemCache:
                                self.__setCache(paramVal, (ret, retEx))
                            break
                        else:
                            retEx = None

                if useMemCache:
                    self.__setCache(paramVal, (ret, retEx))

            if ret == 0:
                retEx = ()

            cursor.close()
            conn.commit()
        except Exception, e:
            try:
                cursor.close()
            except:
                pass
            logging.getLogger().error("%s: database error %s" % (self.getId(), e))
            return 0, None
        #self.factory.releaseDbConnection(conn)

        return ret, retEx


    def __getCache(self, key):
        ret, retEx = (None, None)

        self.lock.acquire()
        try:
            (ret, retEx, expire) = self.cache.get(key, (None, None, 0))
            if time.time() > expire:
                del(self.cache[key])
                ret = (None, None)
        finally:
            self.lock.release()

        return ret, retEx


    def __setCache(self, key, value):
        expire = time.time() + self.getParam('memCacheExpire')
        memCacheSize = self.getParam('memCacheSize')

        self.lock.acquire()
        try:
            if len(self.cache) > memCacheSize:
                self.cache.clear()
            self.cache[key] = (value[0], value[1], expire)
        finally:
            self.lock.release()
