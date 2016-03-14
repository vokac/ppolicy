#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Check if array of defined parameters are in blacklist/whitelist
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


class ListBW(Base):
    """Check if array of defined parameters are in blacklist/whitelist.
    Each parameter is searched in b/w list and first occurence is returned.

    Module arguments (see output of getParams method):
    param, tableBlacklist, tableWhitelist, retcolsBlacklist,
    retcolsWhitelist, mappingBlacklist, mappingWhitelist,
    cacheCaseSensitive, cacheAll, cacheAllRefresh, cacheAllExpire

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
        modules['list1'] = ( 'ListBW', { 'param': "sender_splitted" } )
        # check if sender in blacklist/whitelist
        # compare case-insensitive and return whole selected row
        modules['list2'] = ( 'ListBW', {
                'param': "sender_splitted",
                'tableBlacklist': "my_blacklist",
                'tableWhitelist': "my_whitelist",
                'mappingBlacklist': { "my_param": ("my_column", "VARCHAR(50)") },
                'mappingWhitelist': {"my_param": ("my_column", "VARCHAR(50)") },
                'cacheCaseSensitive': False,
                'retcol': "*" } )
    """

    PARAMS = { 'param': ('name of parameter in data dictionary (value can be string or array)', None),
               'tableBlacklist': ('name of blacklist database table where to search parameter', None),
               'tableWhitelist': ('name of whitelist database table where to search parameter', None),
               'retcolsBlacklist': ('name of blacklist columns returned by check method', None),
               'retcolsWhitelist': ('name of whitelist columns returned by check method', None),
               'mappingBlacklist': ('mapping between params and database columns for blacklist', {}),
               'mappingWhitelist': ('mapping between params and database columns for whitelist', {}),
               'cacheCaseSensitive': ('case-sensitive cache (set to True if you are using case-sensitive text comparator on DB column', False),
               'cacheAll': ('cache all records in memory', False),
               'cacheAllRefresh': ('refresh time in case of caching all records', 15*60),
               'cacheAllExpire': ('expire cache not successfuly refreshed during this time', 60*60),
               }
    DB_ENGINE="ENGINE=InnoDB"


    def __defaultMapping(self, mapping):
        mappingCols  = {}
        mappingType = {}
        for dictName, colDef in mapping.items():
            colName = dictName
            colType = 'VARCHAR(255)'
            if colDef == None or len(colDef) == 0:
                pass
            elif type(colDef) == str:
                colName = colDef
            elif type(colDef) != list and type(colDef) != tuple:
                raise ParamError("invalid arguments for %s: %s" % (dictName, str(colDef)))
            elif len(colDef) == 1:
                colName = colDef[0]
            else:
                if len(colDef) > 2:
                    logging.getLogger().warn("too many arguments for %s: %s" % (dictName, str(colDef)))
                colName = colDef[0]
                colType = colDef[1]
            mappingCols[dictName] = colName
            mappingType[dictName] = colType
        return mappingCols, mappingType


    def __retcolsSQL(self, retcols):
        retcolsSQL = ''
        retcolsNew = []

        if retcols == None:
            retcolsSQL = '1'
        elif type(retcols) == type([]):
            if len(retcols) == 0:
                retcolsSQL = '1'
            else:
                retcolsNew = retcols
                retcolsSQL = "`%s`" % "`,`".join(retcolsNew)
        elif retcols.find(',') != -1:
            retcolsNew = retcols.split(',')
            retcolsSQL = "`%s`" % "`,`".join(retcolsNew)
        elif retcols != '*' and retcols.find('(') == -1:
            retcolsNew = [ retcols ]
            retcolsSQL = "`%s`" % retcols
        else: # *, COUNT(*), AVG(column), ...
            retcolsSQL = retcols

        logging.getLogger().debug("retcols: %s %s %s" % (retcols, retcolsNew, retcolsSQL))

        return (retcolsSQL, retcolsNew)


    def __cacheAllRefresh(self):
        """This method has to be called from synchronized block."""
        allDataCacheUpdated = 0

        while not self.allDataCacheStop:
            conn = None
            cursor = None

            # in case of error try retry in 60 seconds
            allDataCacheRefresh = 60

            try:
                newCacheWhitelist = {}
                newCacheBlacklist = {}

                conn = self.factory.getDbConnection()
                cursor = conn.cursor()

                if self.tableWhitelist != None:
                    sql = self.selectAllSQLWhitelist
                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)
                    logging.getLogger().info("whitelist cached %s records for %ss (%ss)" % (int(cursor.rowcount), self.getParam('cacheAllRefresh'), self.getParam('cacheAllExpire')))
                    while True:
                        res = cursor.fetchone()
                        if res == None:
                            break
                        if len(self.param) == 1:
                            cKey = res[0]
                            if not self.cacheCaseSensitive and type(cKey) == str:
                                cKey = cKey.lower()
                            newCacheWhitelist[cKey] = tuple(res[1:])
                        else:
                            cKey = res[:len(self.param)]
                            if not self.cacheCaseSensitive:
                                x = []
                                for y in cKey:
                                    if type(y) == str: x.append(y.lower())
                                    else: x.append(y)
                                cKey = x
                            newCacheWhitelist[tuple(cKey)] = tuple(res[len(self.param):])

                if self.tableBlacklist != None:
                    sql = self.selectAllSQLBlacklist
                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)
                    logging.getLogger().info("blacklist cached %s records for %ss (%ss)" % (int(cursor.rowcount), self.getParam('cacheAllRefresh'), self.getParam('cacheAllExpire')))
                    while True:
                        res = cursor.fetchone()
                        if res == None:
                            break
                        if len(self.param) == 1:
                            cKey = res[0]
                            if not self.cacheCaseSensitive and type(cKey) == str:
                                cKey = cKey.lower()
                            newCacheBlacklist[cKey] = tuple(res[1:])
                        else:
                            cKey = res[:len(self.param)]
                            if not self.cacheCaseSensitive:
                                x = []
                                for y in cKey:
                                    if type(y) == str: x.append(y.lower())
                                    else: x.append(y)
                                cKey = x
                            newCacheBlacklist[tuple(cKey)] = tuple(res[len(self.param):])

                cursor.close()

                self.allDataCacheWhitelist = newCacheWhitelist
                self.allDataCacheBlacklist = newCacheBlacklist
                self.allDataCacheReady = True

                allDataCacheUpdated = time.time()
                allDataCacheRefresh = self.getParam('cacheAllRefresh')
            except Exception, e:
                logging.getLogger().error("caching all records failed: %s" % e)

                if allDataCacheUpdated + self.getParam('cacheAllExpire') < time.time():
                    # invalidate too old data in the cache
                    self.allDataCacheReady = False

                if cursor != None:
                    try:
                        cursor.close()
                    except Exception, e:
                        logging.getLogger().error("failed to close DB cursor: %s" % e)

            self.allDataCacheCondition.acquire()
            self.allDataCacheCondition.wait(allDataCacheRefresh)
            self.allDataCacheCondition.release()

            #self.factory.releaseDbConnection(conn)


    def getId(self):
        return "%s[%s(%s,%s,%s)]" % (self.type, self.name, self.getParam('param'), self.getParam('tableBlacklist'), self.getParam('tableWhitelist'))


    def hashArg(self, data, *args, **keywords):
        paramValue = []
        for par in self.param:
            parVal = str(data.get(par, ''))
            if self.cacheCaseSensitive and type(parVal) != str:
                paramValue.append("%s=%s" % (par, parVal))
            else:
                paramValue.append("%s=%s" % (par, parVal.lower()))

        return hash("\n".join(paramValue))


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for attr in [ 'param' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        param = self.getParam('param')
        self.tableWhitelist = self.getParam('tableWhitelist')
        self.tableBlacklist = self.getParam('tableBlacklist')
        mappingWhitelist = self.getParam('mappingWhitelist', {})
        mappingBlacklist = self.getParam('mappingBlacklist', {})
        retcolsWhitelist = self.getParam('retcolsWhitelist')
        retcolsBlacklist = self.getParam('retcolsBlacklist')
        self.cacheCaseSensitive = self.getParam('cacheCaseSensitive')

        self.wherecolsWhitelist = []
        self.wherecolsBlacklist = []

        if type(param) == str:
            self.param = [ param ]
        else:
            self.param = param[:]

        (self.retcolsSQLWhitelist, self.retcolsWhitelist) = self.__retcolsSQL(retcolsWhitelist)
        (self.retcolsSQLBlacklist, self.retcolsBlacklist) = self.__retcolsSQL(retcolsBlacklist)

        # hash to table columns mapping
        (self.mappingWhitelist, mappingTypeWhitelist) = self.__defaultMapping(mappingWhitelist)
        (self.mappingBlacklist, mappingTypeBlacklist) = self.__defaultMapping(mappingBlacklist)

        colsWhitelist = []
        colsCreateWhitelist = []
        for dictName in self.param:
            colName = self.mappingWhitelist.get(dictName, dictName)
            self.wherecolsWhitelist.append(colName)
            if colName in colsWhitelist: continue
            colType = mappingTypeWhitelist.get(dictName)
            if colType == None or colType == '':
                colType = 'VARCHAR(255)'
            colsWhitelist.append(colName)
            colsCreateWhitelist.append("`%s` %s" % (colName, colType))
        if type(self.retcolsWhitelist) == type([]):
            for dictName in self.retcolsWhitelist:
                colName = self.mappingWhitelist.get(dictName, dictName)
                if colName in colsWhitelist: continue
                colType = mappingTypeWhitelist.get(dictName)
                if colType == None or colType == '':
                    colType = 'VARCHAR(255)'
                colsWhitelist.append(colName)
                colsCreateWhitelist.append("`%s` %s" % (colName, colType))

        idxWhitelist = []
        if len(self.wherecolsWhitelist) > 0:
            idxWhitelist.append("INDEX `autoindex_key` (`%s`)" % "`,`".join(self.wherecolsWhitelist))
        logging.getLogger().debug("mapping: %s" % mappingWhitelist)

        colsBlacklist = []
        colsCreateBlacklist = []
        for dictName in self.param:
            colName = self.mappingBlacklist.get(dictName, dictName)
            self.wherecolsBlacklist.append(colName)
            if colName in colsBlacklist: continue
            colType = mappingTypeBlacklist.get(dictName)
            if colType == None or colType == '':
                colType = 'VARCHAR(255)'
            colsBlacklist.append(colName)
            colsCreateBlacklist.append("`%s` %s" % (colName, colType))
        if type(self.retcolsBlacklist) == type([]):
            for dictName in self.retcolsBlacklist:
                colName = self.mappingBlacklist.get(dictName, dictName)
                if colName in colsBlacklist: continue
                colType = mappingTypeBlacklist.get(dictName)
                if colType == None or colType == '':
                    colType = 'VARCHAR(255)'
                colsBlacklist.append(colName)
                colsCreateBlacklist.append("`%s` %s" % (colName, colType))

        idxBlacklist = []
        if len(self.wherecolsBlacklist) > 0:
            idxBlacklist.append("INDEX `autoindex_key` (`%s`)" % "`,`".join(self.wherecolsBlacklist))
        logging.getLogger().debug("mapping: %s" % mappingBlacklist)

        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        try:
            if self.tableWhitelist != None:
                cursor = conn.cursor()
                sql = "CREATE TABLE IF NOT EXISTS `%s` (%s) %s" % (self.tableWhitelist, ",".join(colsCreateWhitelist+idxWhitelist), ListBW.DB_ENGINE)
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
            if self.tableBlacklist != None:
                cursor = conn.cursor()
                sql = "CREATE TABLE IF NOT EXISTS `%s` (%s) %s" % (self.tableBlacklist, ",".join(colsCreateBlacklist+idxBlacklist), ListBW.DB_ENGINE)
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
            cursor.close()
            conn.commit()
        except Exception, e:
            cursor.close()
            raise e
        #self.factory.releaseDbConnection(conn)

        if self.getParam('cacheAll', False):
            if self.tableWhitelist != None:
                groupBySQLWhitelist = ''
                if self.retcolsSQLWhitelist == '*':
                    columnSQLWhitelist = "`%s`, `%s`" % ("`, `".join(self.wherecolsWhitelist), "`, `".join(colsBlacklist))
                else:
                    columnSQLWhitelist = "`%s`, %s" % ("`, `".join(self.wherecolsWhitelist), self.retcolsSQLWhitelist)
                    if self.retcolsSQLWhitelist.find('(') != -1:
                        groupBySQLWhitelist = " GROUP BY `%s`" % "`, `".join(colsWhitelist)
                self.selectAllSQLWhitelist = "SELECT %s FROM `%s`%s" % (columnSQLWhitelist, self.tableWhitelist, groupBySQLWhitelist)

            if self.tableBlacklist != None:
                groupBySQLBlacklist = ''
                if self.retcolsSQLBlacklist == '*':
                    columnSQLBlacklist = "`%s`, `%s`" % ("`, `".join(self.wherecolsBlacklist), "`, `".join(colsBlacklist))
                else:
                    columnSQLBlacklist = "`%s`, %s" % ("`, `".join(self.wherecolsBlacklist), self.retcolsSQLBlacklist)
                    if self.retcolsSQLBlacklist.find('(') != -1:
                        groupBySQLBlacklist = " GROUP BY `%s`" % "`, `".join(colsBlacklist)
                self.selectAllSQLBlacklist = "SELECT %s FROM `%s`%s" % (columnSQLBlacklist, self.tableBlacklist, groupBySQLBlacklist)

            self.allDataCacheWhitelist = {}
            self.allDataCacheBlacklist = {}
            self.allDataCacheStop = False
            self.allDataCacheReady = False
            self.allDataCacheCondition = threading.Condition()
            self.allDataCacheThread = threading.Thread(target=self.__cacheAllRefresh)
            self.allDataCacheThread.daemon = True
            self.allDataCacheThread.start()


    def stop(self):
        """Called when changing state to 'stopped'."""
        if getattr(self, 'allDataCacheThread') != None:
            self.allDataCacheStop = True

            self.allDataCacheCondition.acquire()
            self.allDataCacheCondition.notify_all()
            self.allDataCacheCondition.release()

            self.allDataCacheThread.join()
            self.allDataCacheThread = None


    def check(self, data, *args, **keywords):
        if len(self.param) == 1:
            p = data.get(self.param[0], '')
            if not self.cacheCaseSensitive and type(p) == str:
                paramValue = p.lower()
        else:
            paramVal = []
            for par in self.param:
                p = data.get(par, '')
                if not self.cacheCaseSensitive and type(p) == str:
                    paramVal.append(p.lower())
                else:
                    paramVal.append(p)
            paramValue = tuple(paramVal)

        ret = 0
        retEx = None

        if self.getParam('cacheAll', False):

            if self.allDataCacheReady:
                retEx = self.allDataCacheWhitelist.get(paramValue)
                if retEx != None:
                    ret = 1
                retEx = self.allDataCacheBlacklist.get(paramValue)
                if retEx != None:
                    ret = -1

            if ret == 0:
                retEx = ()

            return ret, retEx

        # next code require param value as tuple
        if len(self.param) == 1:
            paramValue = tuple((paramValue, ))

        try:
            conn = self.factory.getDbConnection()
            cursor = conn.cursor()

            if self.tableWhitelist != None:
                if len(self.param) == 1:
                    sqlWhere = "WHERE `%s` = %%s" % self.mappingWhitelist.get(self.param[0], self.param[0])
                else:
                    sqlWhereAnd = []
                    for par in self.param:
                        sqlWhereAnd.append("`%s` = %%s" % self.mappingWhitelist.get(par, par))
                    sqlWhere = "WHERE %s" % " AND ".join(sqlWhereAnd)

                sql = "SELECT %s FROM `%s` %s" % (self.retcolsSQLWhitelist, self.tableWhitelist, sqlWhere)

                if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                    logging.getLogger().debug("SQL: %s %s" % (sql, str(paramValue)))
                cursor.execute(sql, paramValue)

                if int(cursor.rowcount) > 0:
                    retEx = cursor.fetchone()
                    if self.retcolsWhitelist != None or (self.retcolsWhitelist == None and retEx[0] > 0):
                        ret = 1

            if self.tableBlacklist != None:
                if len(self.param) == 1:
                    sqlWhere = "WHERE `%s` = %%s" % self.mappingBlacklist.get(self.param[0], self.param[0])
                else:
                    sqlWhereAnd = []
                    for par in self.param:
                        sqlWhereAnd.append("`%s` = %%s" % self.mappingBlacklist.get(par, par))
                    sqlWhere = "WHERE %s" % " AND ".join(sqlWhereAnd)

                sql = "SELECT %s FROM `%s` %s" % (self.retcolsSQLBlacklist, self.tableBlacklist, sqlWhere)

                if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                    logging.getLogger().debug("SQL: %s %s" % (sql, str(paramValue)))
                cursor.execute(sql, paramValue)

                if int(cursor.rowcount) > 0:
                    retEx = cursor.fetchone()
                    if self.retcolsBlacklist != None or (self.retcolsBlacklist == None and retEx[0] > 0):
                        ret = -1

            cursor.close()
        except Exception, e:
            try:
                cursor.close()
            except:
                pass
            logging.getLogger().error("%s: database error %s" % (self.getId(), e))
            if logging.getLogger().getEffectiveLevel() <= logging.WARNING:
                import sys, traceback
                exc_info_type, exc_info_value, exc_info_traceback = sys.exc_info()
                logging.getLogger().warn(traceback.format_exception(exc_info_type, exc_info_value, exc_info_traceback))
            return 0, None

        return ret, retEx
