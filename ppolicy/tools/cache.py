#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Data caching
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import time, threading
import logging

#
# Memory cache
#
class MemCache:
    """Base class for cache. It implements memory caching and provide
    interface for subclasses that can add e.g. database caching.

    parameters:
      memExpire - handle different expiration for different records if you
        set this variable > 0. Otherwise per record expiration is not used.
      memMaxSize - maximum cached record in memory
    """

    # How many record should stay in cache if its size reach memMaxSize limit.
    CLEAR_FACTOR = 2./3

    def __init__(self, memExpire = 0, memMaxSize = 0):
        self.memExpire = getattr(self, 'memExpire', memExpire)
        self.memMaxSize = getattr(self, 'memMaxSize', memMaxSize)
        self.cacheVal = {}
        self.cacheUse = {}
        self.cacheExp = {}
        self.lock = threading.Lock()


    def __clearCache(self, all = False):
        """If cache is full clear CLEAR_FACTOR. It is not thread safe
        and has to be called with acquired lock."""
        if all:
            self.cacheVal.clear()
            self.cacheUse.clear()
            self.cacheExp.clear()
        else:
            toDel = []
            sval = sorted(self.cacheUse.values())
            trh = sval[int(self.memMaxSize*self.CLEAR_FACTOR)]
            for keyToDel in self.cacheUse.keys():
                if self.cacheUse[keyToDel] <= trh or (self.memExpire > 0 and self.cacheExp[keyToDel] < time.time()):
                    toDel.append(keyToDel)
            for keyToDel in toDel:
                del self.cacheVal[keyToDel]
                del self.cacheUse[keyToDel]
                if self.memExpire != 0:
                    del self.cacheExp[keyToDel]


    def clear(self):
        """Clear all records in memory cache."""
        self.lock.acquire()
        try:
            self.__clearCache(True)
        finally:
            self.lock.release()


    def reload(self, data = None, cols = None):
        """Clear/Reload data cache."""
        self.lock.acquire()
        try:
            self.__clearCache(True)
            if data != None:
                # FIXME: cols
                nameLen = len(cols.get('name', []))
                valueLen = len(cols.get('value', []))
                for d in data:
                    if nameLen == 1:
                        key = d[0]
                    else:
                        key = tuple()
                        for i in range(0, nameLen):
                            key += (d[i], )
                    if valueLen == 0:
                        val = True
                    elif valueLen == 1:
                        val = d[nameLen]
                    else:
                        val = tuple()
                        for i in range(0, valueLen):
                            val += (d[nameLen+i], )
                    self.cacheVal[key] = val
                    if self.memExpire > 0:
                        self.cacheExp[key] = time.time() + self.memExpire
                        if cols.has_key('expire'):
                            exp = d[nameLen+valueLen]
                            if time.time() + self.memExpire > exp:
                                self.cacheExp[key] = exp
                    if self.memMaxSize > 0:
                        self.cacheUse[key] = time.time()
        finally:
            self.lock.release()


    def get(self, key, default = None):
        val = default
        self.lock.acquire()
        try:
            if self.cacheVal.has_key(key):
                if self.memMaxSize > 0:
                    self.cacheUse[key] = time.time()
                if self.memExpire == 0:
                    val = self.cacheVal[key]
                elif self.cacheExp[key] >= time.time():
                    val = self.cacheVal[key]
                else:
                    # remove memExpired record
                    del self.cacheVal[key]
                    del self.cacheExp[key]
                    if self.memMaxSize > 0:
                        del self.cacheUse[key]
        finally:
            self.lock.release()
        return val


    def set(self, key, val, exp = 0):
        self.lock.acquire()
        try:
            if self.memMaxSize > 0 and len(self.cacheUse) >= self.memMaxSize:
                self.__clearCache()
            self.cacheVal[key] = val
            if self.memExpire > 0:
                if exp == 0:
                    exp = self.memExpire
                self.cacheExp[key] = time.time() + exp
            if self.memMaxSize > 0:
                self.cacheUse[key] = time.time()
        finally:
            self.lock.release()



#
# Database cache
#
class DbCache:
    """Pernament database cache. It can use MemCache for speedup access
    regularly requested records.

    Parameters:
      parent - reference to Check object (needed for db connection)
      table - database table to read/save cached items
      cols - database column to store data (dictionary of name, value, expire)
      error - propagate get/set error/exception (default: False)
      memCache - use memory cache (default: True)
      memExpire - expiration time of item in MemCache (default: 600s)
      memMaxSize - maximum item in MemCache (default: 0 - infinite)
    """

    # stop to use db after limit reached
    ERROR_LIMIT = 10
    # time after which errorLimit will be increased
    ERROR_SLEEP = 120

    class DbCacheError(Exception):
        """Base exception class."""
        def __init__(self, args = ""):
            Exception.__init__(self, args)

    def __init__(self, parent, table, cols, error = False,
                 memCache = True, memExpire = 600, memMaxSize = 0):
        if parent == None or table == None or cols == None:
            raise DbCache.DbCacheError("Undefined required param: %s, %s, %s" %
                                       (parent, table, cols))
        self.getId = parent.getId
        self.getDbConnection = parent.getDbConnection
        self.table = getattr(self, 'table', table)
        self.colsDef = getattr(self, 'colsDef', cols)
        if 'name' not in self.colsDef.keys():
            raise DbCache.DbCacheError("Name column is required for %s" %
                                       self.table)
        self.cols = {}
        self.colsTypes = {}
        for k, v in self.colsDef.items():
            if k not in [ 'name', 'value', 'expire' ]:
                raise DbCache.DbCacheError("Unknown column %s in table %s" %
                                           (k, self.table))
            self.__createDbColsDef(k, v)
        self.error = getattr(self, 'error', error)
        self.memCache = getattr(self, 'memCache', memCache)
        self.memExpire = getattr(self, 'memExpire', memExpire)
        self.memMaxSize = getattr(self, 'memMaxSize', memMaxSize)
        if self.memCache:
            self.cacheVal = MemCache(memExpire, memMaxSize)
        else:
            self.cacheVal = None
        self.errorLimit = self.ERROR_LIMIT
        self.errorSleep = 0
        self.useDb = True
        self.__createDb()
        self.lastReload = 0
        self.reload()
        self.lock = threading.Lock()


    def __createDbColsDef(self, key, values):
        vn = []
        if type(values) != type([]):
            values = [ values ]
        for val in values:
            if val.find(" ") != -1:
                v1, v2 = val.split(" ", 2)
                vn.append(v1)
                self.colsTypes[key + "=>" + v1] = v2
            else:
                vn.append(val)
        self.cols[key] = vn


    def __createDbCols(self, key, defType):
        retVal = []
        if type(self.cols[key]) != type([]):
            colName = self.cols[key]
            colType = self.colsTypes.get(key+"=>"+colName, defType)
            self.colsTypes[key+"=>"+colName] = colType
            retVal.append("`%s` %s" % (colName, colType))
        else:
            for colName in self.cols[key]:
                colType = self.colsTypes.get(key+"=>"+colName, defType)
                self.colsTypes[key+"=>"+colName] = colType
                retVal.append("`%s` %s" % (colName, colType))
        return retVal
        

    def __createDb(self):
        """Check if we can use db connection, check existence or required
        table and create new if doesn't exist."""
        try:
            sql = ""
            colsDef = []
            if self.cols.has_key('name'):
                colsDef += self.__createDbCols('name', 'VARCHAR(50)')
            if self.cols.has_key('value'):
                colsDef += self.__createDbCols('value', 'VARCHAR(200)')
            if self.cols.has_key('expire'):
                colsDef += self.__createDbCols('expire', 'TIMESTAMP NOT NULL')
            if self.cols.get('name'):
                colsDef += [ "PRIMARY KEY (`%s`)" % "`,`".join(self.cols['name']) ]
            sql = "CREATE TABLE IF NOT EXISTS %s" % self.table
            sql += " (%s) " % ",".join(colsDef)
            sql += ' ENGINE=MyISAM DEFAULT CHARSET=latin1'
            conn = self.getDbConnection()
            cursor = conn.cursor()
            try:
                cursor.execute(sql)
                sql = "SELECT %s FROM %s WHERE 1 = 2" % (self.__getSelectExprCols(), self.table)
                cursor.execute(sql)
            finally:
                cursor.close()
        except Exception, err:
            logging.log(logging.ERROR, "%s: query '%s': %s" % (self.getId(), sql, err))


    def __getAllCols(self):
        retval = []
        if self.cols.has_key('name'):
            for val in self.cols['name']:
                retval.append(val)
        if self.cols.has_key('value'):
            for val in self.cols['value']:
                retval.append(val)
        if self.cols.has_key('expire'):
            retval.append(self.cols['expire'][0])
        return ",".join(retval)


    def __getSelectExpr(self, key, val):
        if self.colsTypes.get(key+'=>'+val, "").find('TIMESTAMP') != -1:
            return 'UNIX_TIMESTAMP(`'+val+'`)'
        else:
            return val


    def __getSelectExprCols(self, cols = [ 'name', 'value', 'expire' ]):
        retval = []
        if 'name' in cols and self.cols.has_key('name'):
            for val in self.cols['name']:
                retval.append(self.__getSelectExpr('name', val))
        if 'value' in cols and self.cols.has_key('value'):
            for val in self.cols['value']:
                retval.append(self.__getSelectExpr('value', val))
        if 'expire' in cols and self.cols.has_key('expire'):
            retval.append(self.__getSelectExpr('expire', self.cols['expire'][0]))
        return ",".join(retval)


    def __getInsertExpr(self, key, val, pos = 0):
        colName = self.cols[key][pos]
        if type(val) != type(()):
            val = ( val, )
        if self.colsTypes.get(key+'=>'+colName, "").find('TIMESTAMP') != -1:
            return "FROM_UNIXTIME(%i)" % val[pos]
        else:
            return "'%s'" % val[pos]


    def __getWhere(self, key):
        retval = []
        if type(key) != type(()):
            key = [ key ]
        if self.cols.has_key('name'):
            pos = 0
            for val in self.cols['name']:
                if len(key) > pos and key[pos] != None:
                    retval.append("`%s` = '%s'" % (val, key[pos]))
                pos += 1
        return " AND ".join(retval)


    def __useDb(self):
        """Not thread safe - has to be called with acquired lock."""
        if self.errorLimit <= 0:
            if self.useDb:
                self.useDb = False
                self.errorSleep = time.time() + self.ERROR_SLEEP
            elif self.errorSleep < time.time():
                self.useDb = True
                self.errorLimit = self.ERROR_LIMIT
        return self.useDb


    def clear(self, db = False):
        if db:
            try:
                sql = "DELETE FROM %s" % self.table
                conn = self.getDbConnection()
                cursor = conn.cursor()
                try:
                    cursor.execute(sql)
                finally:
                    cursor.close()
            except Exception, err:
                logging.log(logging.ERROR, "%s: error clearing %s: %s" %
                            (self.getId(), self.table, err))
        if self.cacheVal != None:
            self.cacheVal.clear()


    def reload(self):
        if not self.memCache:
            return
        try:
            sql = ""
            conn = self.getDbConnection()
            cursor = conn.cursor()
            try:
                if self.memMaxSize > 0:
                    sql = "SELECT COUNT(*) FROM %s" % self.table
                    cursor.execute(sql)
                    row = cursor.fetchone()
                    if self.memMaxSize > row[0]:
                        self.cacheVal.clear()
                        return
                sql = "SELECT %s FROM %s" % (self.__getSelectExprCols(), self.table)
                cursor.execute(sql)
                self.cacheVal.reload(cursor.fetchall(), self.cols)
                logging.log(logging.INFO, "%s: loaded %s rows from %s" %
                            (self.getId(), cursor.rowcount, self.table))
            finally:
                cursor.close()
            self.lastReload = time.time()
        except Exception, err:
            # use only memory cache in case of DB problems
            logging.log(logging.ERROR, "%s: error loading %s: %s" %
                        (self.getId(), self.table, err))
            self.cacheVal.clear()


    def get(self, key, default = None):
        """Get data from cache."""
        retVal = default
        self.lock.acquire()
        try:
            if self.memExpire > 0 and self.memMaxSize == 0:
                if self.lastReload < time.time() - self.memExpire:
                    self.reload()
            if self.memCache:
                retVal = self.cacheVal.get(key, default)
            if retVal == default and self.__useDb() and self.memMaxSize > 0:
                sql = "SELECT %s FROM %s" % (self.__getSelectExprCols([ 'value', 'expire' ]), self.table)
                sql += " WHERE %s" % self.__getWhere(key)
                conn = self.getDbConnection()
                cursor = conn.cursor()
                try:
                    cursor.execute(sql)
                    if cursor.rowcount > 0:
                        if cursor.rowcount > 1:
                            logging.log(logging.WARN, "%s: more records in %s for %s" %
                                        (self.getId(), self.table, key))
                        row = cursor.fetchone()
                        if row != None:
                            value = True
                            if self.cols.has_key('value'):
                                valueLen = len(self.cols['value'])
                                if valueLen == 1:
                                    value = row[0]
                                else:
                                    value = tuple()
                                    for i in range(0, valueLen):
                                        value += (row[i], )
                            expire = time.time() + self.memExpire
                            if self.cols.has_key('expire') and time.time() + self.memExpire > row[len(row)-1]:
                                expire = row[len(row)-1]
                            if self.memCache:
                                self.cacheVal.set(key, value, expire)
                            if expire >= time.time():
                                retVal = value
                finally:
                    cursor.close()
        except Exception, err:
            logging.log(logging.ERROR, "%s: cache error (table: %s, key: %s, err: %s): %s" %
                        (self.getId(), self.table, key, self.errorLimit, err))
            if self.error:
                self.lock.release()
                raise err
            self.errorLimit -= 1
        self.lock.release()
        return retVal


    def set(self, key, val = True, exp = 0):
        """Set data in cache."""
        self.lock.acquire()
        try:
            if self.memCache:
                self.cacheVal.set(key, val, self.memExpire)
            if self.__useDb():
                sql = "SELECT COUNT(*) FROM %s" % self.table
                sql += " WHERE %s" % self.__getWhere(key)
                conn = self.getDbConnection()
                cursor = conn.cursor()
                try:
                    cursor.execute(sql)
                    row = cursor.fetchone ()
                    if row != None:
                        if row[0] == 0:
                            sqlVal = []
                            if self.cols.has_key('name'):
                                keyLen = len(self.cols.get('name', []))
                                if keyLen == 1:
                                    sqlVal.append(self.__getInsertExpr('name', key))
                                else:
                                    for i in range(0, keyLen):
                                        sqlVal.append(self.__getInsertExpr('name', key, i))
                            if self.cols.has_key('value'):
                                valLen = len(self.cols.get('value', []))
                                if valLen == 1:
                                    sqlVal.append(self.__getInsertExpr('value', val))
                                else:
                                    for i in range(0, valLen):
                                        sqlVal.append(self.__getInsertExpr('value', val, i))
                            if self.cols.has_key('expire'):
                                sqlVal.append(self.__getInsertExpr('expire', exp))
                            sql = "INSERT INTO %s (%s) VALUES (%s)" % (self.table, self.__getAllCols(), ",".join(sqlVal))
                            cursor.execute(sql)
                        else:
                            sqlVal = []
                            if self.cols.has_key('value'):
                                valLen = len(self.cols.get('value', []))
                                if valLen == 1:
                                    sqlVal.append("`%s` = %s" % (self.cols['value'][0], self.__getInsertExpr('value', val)))
                                else:
                                    for i in range(0, valLen):
                                        sqlVal.append("`%s` = %s" % (self.cols['value'][i], self.__getInsertExpr('value', val, i)))
                            if self.cols.has_key('expire'):
                                sqlVal.append("`%s` = %s " % (self.cols['expire'][0], self.__getInsertExpr('expire', exp)))
                            if len(sqlVal) > 1:
                                sql = "UPDATE %s SET " % self.table
                                sql += ",".join(sqlVal)
                                sql += "WHERE %s" % self.__getWhere(key)
                                cursor.execute(sql)
                finally:
                    cursor.close()
        except IndexError, err:
            logging.log(logging.ERROR, "%s: wrong number of parameters: %s" %
                        (self.getId(), err))
        except Exception, err:
            logging.log(logging.ERROR, "%s: cache error (table: %s, key: %s, err: %s): %s" %
                        (self.getId(), self.table, key, self.errorLimit, err))
            if self.error:
                self.lock.release()
                raise err
            self.errorLimit -= 1
        self.lock.release()




class FakeCheck:
    def getId(self):
        return "FakeCheck"
    def getDbConnection(self):
        import MySQLdb

        conn = None
        try:
            conn = MySQLdb.connect(host = "localhost",
                                   db = "ppolicy",
                                   user = "ppolicy",
                                   passwd = "ppolicy")
        except MySQLdb.Error, e:
            print "Error %d: %s" % (e.args[0], e.args[1])

        return conn


if __name__ == "__main__":
    print "Module tests:"
    import sys
    import twisted.python.log
    twisted.python.log.startLogging(sys.stdout)

    print "##### MemCache #####"
    memCache = MemCache(30, 10)
    for i in range(0, 20):
        memCache.set(i, i)
    for i in range(0, 20):
        print memCache.get(i)


    print "##### DbCache #####"
    print ">>>> test db 1 <<<<"
    FakeCheck().getDbConnection().cursor().execute("DROP TABLE IF EXISTS test1")
    dbCache = DbCache(FakeCheck(), 'test1',
                      { 'name': 'name VARCHAR(10)',
                        'value': 'value VARCHAR(123)',
                        'expire': 'expire' }, True, 900, 0)
    print ">> get"
    print dbCache.get('test')
    print dbCache.get('test1')
    print dbCache.get('test2', 'test')
    print ">> set"
    dbCache.set('test1', 'test1')
    dbCache.set('test2', 'test2', time.time() + 1234)
    print ">> get"
    print dbCache.get('test')
    print dbCache.get('test1')
    print dbCache.get('test2', 'test')
    print ">> set"
    dbCache.set('test1', 'test1')
    dbCache.set('test2', 'test2', time.time() + 1234)
    print ">> reload"
    dbCache.reload()
    print ">> get"
    print dbCache.get('test')
    print dbCache.get('test1')
    print dbCache.get('test2', 'test')

    print ">>>> test db 2 <<<<"
    FakeCheck().getDbConnection().cursor().execute("DROP TABLE IF EXISTS test2")
    dbCache = DbCache(FakeCheck(), 'test2',
                      { 'name': [ 'name1', 'name2' ],
                        'value': [ 'value1', 'value2' ],
                        'expire': 'expire' }, True, 900, 0)
    print ">> get"
    print dbCache.get('test')
    print dbCache.get(('test1', 'test1'))
    print dbCache.get(('test1', 'test2'), ('test', 'test'))
    print ">> set"
    dbCache.set(('test1', 'test1'), ('test1', 'test1'))
    dbCache.set(('test1', 'test2'), ('test1', 'test2'), time.time() + 1234)
    print ">> get"
    print dbCache.get('test')
    print dbCache.get(('test1', 'test1'))
    print dbCache.get(('test1', 'test2'), ('test', 'test'))
    print ">> set"
    dbCache.set(('test1', 'test1'), ('test1', 'test1'))
    dbCache.set(('test1', 'test2'), ('test1', 'test2'), time.time() + 1234)
    print ">> reload"
    dbCache.reload()
    print ">> get"
    print dbCache.get('test')
    print dbCache.get(('test1', 'test1'))
    print dbCache.get(('test1', 'test2'), ('test', 'test'))
