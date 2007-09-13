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
from Base import Base, ParamError


__version__ = "$Revision$"


class ListBW(Base):
    """Check if array of defined parameters are in blacklist/whitelist.
    Each parameter is searched in b/w list and first occurence is returned.

    Module arguments (see output of getParams method):
    param, tableBlacklist, tableWhitelist, retcolsBlacklist,
    retcolsWhitelist, mappingBlacklist, mappingWhitelist,
    cacheCaseSensitive, cacheAll, cacheAllRefresh

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


    def __addCol(self, mapping, dictName, colType, cols, colsCreate, idxNames = None):
        if not mapping.has_key(dictName):
            mapping[dictName] = dictName
        colName = mapping[dictName]
        if colType == None or colType == '':
            colType = 'VARCHAR(255)'
        cols.append(colName)
        colsCreate.append("`%s` %s" % (colName, colType))
        if idxNames != None:
            idxNames.append(mapping[dictName])


    def __retcolsSQL(self, retcols):
        retcolsSQL = ''
        retcolsNew = []

        if retcols == None:
            retcolsSQL = 'COUNT(*)'
        elif type(retcols) == type([]):
            if len(retcols) == 0:
                retcolsSQL = 'COUNT(*)'
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
        if self.allDataCacheRefresh > time.time():
            return

        tableBlacklist = self.getParam('tableBlacklist')
        tableWhitelist = self.getParam('tableWhitelist')
        retcolsBlacklist = self.getParam('retcolsBlacklist')
        retcolsWhitelist = self.getParam('retcolsWhitelist')
        cacheCaseSensitive = self.getParam('cacheCaseSensitive')

        conn = self.factory.getDbConnection()
        try:
            newCacheWhitelist = {}
            newCacheBlacklist = {}

            cursor = conn.cursor()

            if tableWhitelist != None:
                sql = self.selectAllSQLWhitelist
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
                logging.getLogger().info("whitelist cached %s records for %ss" % (int(cursor.rowcount), self.getParam('cacheAllRefresh')))
                while True:
                    res = cursor.fetchone()
                    if res == None:
                        break
                    if type(retcolsWhitelist) == str:
                        cKey = res[-1]
                        if not cacheCaseSensitive and type(cKey) == str:
                            cKey = cKey.lower()
                        newCacheWhitelist[cKey] = res[:-1]
                    else:
                        cKey = res[-len(retcolsWhitelist):]
                        if not cacheCaseSensitive:
                            x = []
                            for y in cKey:
                                if type(y) == str: x.append(y.lower())
                                else: x.append(y)
                            cKey = x
                        newCacheWhitelist[tuple(cKey)] = res[:-len(retcolsWhitelist)]

            if tableBlacklist != None:
                sql = self.selectAllSQLBlacklist
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
                logging.getLogger().info("blacklist cached %s records for %ss" % (int(cursor.rowcount), self.getParam('cacheAllRefresh')))
                while True:
                    res = cursor.fetchone()
                    if res == None:
                        break
                    if type(retcolsBlacklist) == str:
                        cKey = res[-1]
                        if not cacheCaseSensitive and type(cKey) == str:
                            cKey = cKey.lower()
                        newCacheBlacklist[cKey] = res[:-1]
                    else:
                        cKey = res[-len(retcolsBlacklist):]
                        if not cacheCaseSensitive:
                            x = []
                            for y in cKey:
                                if type(y) == str: x.append(y.lower())
                                else: x.append(y)
                            cKey = x
                        newCacheBlacklist[tuple(cKey)] = res[:-len(retcolsBlacklist)]

            cursor.close()

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
        return "%s[%s(%s,%s,%s)]" % (self.type, self.name, self.getParam('param'), self.getParam('tableBlacklist'), self.getParam('tableWhitelist'))


    def hashArg(self, data, *args, **keywords):
        cacheCaseSensitive = self.getParam('cacheCaseSensitive')
        param = self.getParam('param')
        if type(param) == str:
            param = [ param ]

        paramValue = []
        for par in param:
            parVal = str(data.get(par, ''))
            if cacheCaseSensitive and type(parVal) != str:
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
        tableWhitelist = self.getParam('tableWhitelist')
        tableBlacklist = self.getParam('tableBlacklist')
        mappingWhitelist = self.getParam('mappingWhitelist', {})
        mappingBlacklist = self.getParam('mappingBlacklist', {})
        retcolsWhitelist = self.getParam('retcolsWhitelist')
        retcolsBlacklist = self.getParam('retcolsBlacklist')

        if type(param) == str:
            param = [ param ]

        (self.retcolsSQLWhitelist, retcolsWhitelist) = self.__retcolsSQL(retcolsWhitelist)
        self.setParam('retcolsWhitelist', retcolsWhitelist)
        (self.retcolsSQLBlacklist, retcolsBlacklist) = self.__retcolsSQL(retcolsBlacklist)
        self.setParam('retcolsBlacklist', retcolsBlacklist)

        # hash to table columns mapping
        (self.mappingWhitelist, mappingTypeWhitelist) = self.__defaultMapping(mappingWhitelist)
        (self.mappingBlacklist, mappingTypeBlacklist) = self.__defaultMapping(mappingBlacklist)

        colsWhitelist = []
        colsCreateWhitelist = []
        idxNamesWhitelist = []
        for dictName in param:
            self.__addCol(self.mappingWhitelist, dictName, mappingTypeWhitelist.get(dictName), colsWhitelist, colsCreateWhitelist, idxNamesWhitelist)
        if type(retcolsWhitelist) == type([]):
            for dictName in retcolsWhitelist:
                self.__addCol(self.mappingWhitelist, dictName, mappingTypeWhitelist.get(dictName), colsWhitelist, colsCreateWhitelist)

        idxWhitelist = []
        if len(idxNamesWhitelist) > 0:
            idxWhitelist.append("INDEX `autoindex_key` (`%s`)" % "`,`".join(idxNamesWhitelist))
        logging.getLogger().debug("mapping: %s" % mappingWhitelist)

        colsBlacklist = []
        colsCreateBlacklist = []
        idxNamesBlacklist = []
        for dictName in param:
            self.__addCol(self.mappingBlacklist, dictName, mappingTypeBlacklist.get(dictName), colsBlacklist, colsCreateBlacklist, idxNamesBlacklist)
        if type(retcolsBlacklist) == type([]):
            for dictName in retcolsBlacklist:
                self.__addCol(self.mappingBlacklist, dictName, mappingTypeBlacklist.get(dictName), colsBlacklist, colsCreateBlacklist)

        idxBlacklist = []
        if len(idxNamesBlacklist) > 0:
            idxBlacklist.append("INDEX `autoindex_key` (`%s`)" % "`,`".join(idxNamesBlacklist))
        logging.getLogger().debug("mapping: %s" % mappingBlacklist)

        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        try:
            if tableWhitelist != None:
                cursor = conn.cursor()
                sql = "CREATE TABLE IF NOT EXISTS `%s` (%s) %s" % (tableWhitelist, ",".join(colsCreateWhitelist+idxWhitelist), ListBW.DB_ENGINE)
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
            if tableBlacklist != None:
                cursor = conn.cursor()
                sql = "CREATE TABLE IF NOT EXISTS `%s` (%s) %s" % (tableBlacklist, ",".join(colsCreateBlacklist+idxBlacklist), ListBW.DB_ENGINE)
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
            cursor.close()
            conn.commit()
        except Exception, e:
            cursor.close()
            raise e
        #self.factory.releaseDbConnection(conn)

        if self.getParam('cacheAll', False):
            self.allDataCacheWhitelist = {}
            self.allDataCacheBlacklist = {}
            self.allDataCacheReady = False
            self.allDataCacheRefresh = 0

            if tableWhitelist != None:
                columnSQLWhitelist = '`%s`' % "`, `".join(colsWhitelist)
                groupBySQLWhitelist = ''
                if self.retcolsSQLWhitelist == '*':
                    columnSQLWhitelist = '*'
                else:
                    columnSQLWhitelist = "%s, %s" % (self.retcolsSQLWhitelist, columnSQLWhitelist)
                    if self.retcolsSQLWhitelist.find('(') != -1:
                        groupBySQLWhitelist = " GROUP BY `%s`" % "`, `".join(colsWhitelist)
                self.selectAllSQLWhitelist = "SELECT %s FROM `%s`%s" % (columnSQLWhitelist, tableWhitelist, groupBySQLWhitelist)

            if tableBlacklist != None:
                columnSQLBlacklist = '`%s`' % "`, `".join(colsBlacklist)
                groupBySQLBlacklist = ''
                if self.retcolsSQLBlacklist == '*':
                    columnSQLBlacklist = '*'
                else:
                    columnSQLBlacklist = "%s, %s" % (self.retcolsSQLBlacklist, columnSQLBlacklist)
                    if self.retcolsSQLBlacklist.find('(') != -1:
                        groupBySQLBlacklist = " GROUP BY `%s`" % "`, `".join(colsBlacklist)
                self.selectAllSQLBlacklist = "SELECT %s FROM `%s`%s" % (columnSQLBlacklist, tableBlacklist, groupBySQLBlacklist)

            self.__cacheAllRefresh()


    def check(self, data, *args, **keywords):
        cacheCaseSensitive = self.getParam('cacheCaseSensitive')
        param = self.getParam('param')

        if type(param) == str:
            p = data.get(param, '')
            if not cacheCaseSensitive and type(p) == str:
                paramValue = (p.lower(), )
            else:
                paramValue = (p, )
        else:
            paramVal = []
            for par in param:
                p = data.get(par, '')
                if not cacheCaseSensitive and type(p) == str:
                    paramVal.append(p.lower())
                else:
                    paramVal.append(p)
            paramValue = tuple(paramVal)

        ret = 0
        retEx = None

        if self.getParam('cacheAll', False):
            self.__cacheAllRefresh()
            if not self.allDataCacheReady:
                ret = 0
            else:
                retEx = self.allDataCacheWhitelist.get(paramValue)
                if retEx != None:
                    ret = 1
                retEx = self.allDataCacheBlacklist.get(paramValue)
                if retEx != None:
                    ret = -1

            if ret == 0:
                retEx = ()

            return ret, retEx

        tableWhitelist = self.getParam('tableWhitelist')
        tableBlacklist = self.getParam('tableBlacklist')
        retcolsWhitelist = self.getParam('retcolsWhitelist')
        retcolsBlacklist = self.getParam('retcolsBlacklist')

        try:
            conn = self.factory.getDbConnection()
            cursor = conn.cursor()

            if tableWhitelist != None:
                if type(param) == str:
                    sqlWhere = "WHERE `%s` = %%s" % self.mappingWhitelist[param]
                else:
                    sqlWhereAnd = []
                    for par in param:
                        sqlWhereAnd.append("`%s` = %%s" % self.mappingWhitelist[par])
                    sqlWhere = "WHERE %s" % " AND ".join(sqlWhereAnd)

                sql = "SELECT %s FROM `%s` %s" % (self.retcolsSQLWhitelist, tableWhitelist, sqlWhere)

                if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                    logging.getLogger().debug("SQL: %s %s" % (sql, str(paramValue)))
                cursor.execute(sql, paramValue)

                if int(cursor.rowcount) > 0:
                    retEx = cursor.fetchone()
                    if retcolsWhitelist != None or (retcolsWhitelist == None and retEx[0] > 0):
                        ret = 1

            if tableBlacklist != None:
                if type(param) == str:
                    sqlWhere = "WHERE `%s` = %%s" % self.mappingBlacklist[param]
                else:
                    sqlWhereAnd = []
                    for par in param:
                        sqlWhereAnd.append("`%s` = %%s" % self.mappingBlacklist[par])
                    sqlWhere = "WHERE %s" % " AND ".join(sqlWhereAnd)

                sql = "SELECT %s FROM `%s` %s" % (self.retcolsSQLBlacklist, tableBlacklist, sqlWhere)

                if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                    logging.getLogger().debug("SQL: %s %s" % (sql, str(paramValue)))
                cursor.execute(sql, paramValue)

                if int(cursor.rowcount) > 0:
                    retEx = cursor.fetchone()
                    if retcolsBlacklist != None or (retcolsBlacklist == None and retEx[0] > 0):
                        ret = -1

            cursor.close()
        except Exception, e:
            try:
                cursor.close()
            except:
                pass
            logging.getLogger().error("%s: database error %s" % (self.getId(), e))
            return 0, None

        return ret, retEx

