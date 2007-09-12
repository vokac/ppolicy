#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Check if defined parameter is in database
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id: List.py 66 2007-09-11 12:00:26Z vokac $
#
import logging
import time
from Base import Base, ParamError


__version__ = "$Revision: 66 $"


class LookupDB(Base):
    """LookupDB module for searching records in DB.

    You can map incomming data to database columns using "mapping"
    parameter. Its syntax is [ 'dictName': ('columnName',
    'columnType'), ...], where dictName is attribude name comming in
    check method in data dictionary, columnName is database column
    name, column type is database column type in SQL syntax. If don't
    define mapping for concrete column, than default is used
    'dictName': ('dictName', 'VARCHAR(255)')

    Module arguments (see output of getParams method):
    param, table, column, retcols, cacheCaseSensitive, cacheAll, cacheAllRefresh

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... parameter was found in db, second parameter include selected row
        0 .... failed to check (request doesn't include required param,
               database error, ...)
        -1 ... parameter was not found in db

    Examples:
        # module for checking if sender is in database table
        modules['lookup1'] = ( 'LookupDB', { 'param': "sender" } )
        # check if sender domain is in database table my_list
        # compare case-insensitive and return whole selected row
        modules['lookup2'] = ( 'LookupDB', {
                'param': [ "sender", "recipient" ],
                'table': "my_list",
                'mapping': { "sender": ("mail", "VARCHAR(50)"), },
                'retcols': "*" } )
    """

    PARAMS = { 'param': ('name of parameter in data dictionary (value can be string or array)', None),
               'table': ('name of database table where to search parameter', None),
               'retcols': ('name of column returned by check method', None),
               'mapping': ('mapping between params and database columns', {}),
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

        if retcols == None:
            retcolsSQL = 'COUNT(*)'
        elif type(retcols) == type([]):
            retcolsSQL = "`%s`" % "`,`".join(retcols)
#        elif retcols.find(',') != -1:
#            retcolsSQL = "`%s`" % "`,`".join(retcols.split(','))
        elif retcols != '*' and retcols.find('(') == -1:
            retcolsSQL = "`%s`" % retcols
        else: # *, COUNT(*), AVG(column), ...
            retcolsSQL = retcols

        return retcolsSQL


    def __cacheAllRefresh(self):
        """This method has to be called from synchronized block."""
        if self.allDataCacheRefresh > time.time():
            return

        retcols = self.getParam('retcols')
        cacheCaseSensitive = self.getParam('cacheCaseSensitive')

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
                if type(retcols) == str:
                    cKey = res[-1]
                    if not cacheCaseSensitive:
                        cKey = cKey.lower()
                    newCache[cKey] = res[:-1]
                else:
                    cKey = res[-len(retcols):]
                    if not cacheCaseSensitive:
                        cKey = [ x.lower() for x in cKey ]
                    newCache[cKey] = res[:-len(retcols)]
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
        cacheCaseSensitive = self.getParam('cacheCaseSensitive')
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

        for attr in [ 'param', 'table' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        param = self.getParam('param')
        table = self.getParam('table')
        retcols = self.getParam('retcols')
        mapping = self.getParam('mapping', {})
        softExpire = int(self.getParam('softExpire'))
        hardExpire = int(self.getParam('hardExpire'))

        self.retcolsSQL = self.__retcolsSQL(retcols)

        # hash to table columns mapping
        (self.mapping, mappingType) = self.__defaultMapping(mapping)

        cols = []
        colsCreate = []
        idxNames = []
        for dictName in param:
            self.__addCol(self.mapping, dictName, mappingType.get(dictName), cols, colsCreate, idxNames)
        if softExpire > 0:
            self.__addCol(self.mapping, 'soft_expire', 'DATETIME NOT NULL', cols, colsCreate)
        if hardExpire > 0:
            self.__addCol(self.mapping, 'hard_expire', 'DATETIME NOT NULL', cols, colsCreate)
        if type(retcols) == type([]):
            for dictName in retcols:
                self.__addCol(self.mapping, dictName, mappingType.get(dictName), cols, colsCreate)

        idx = []
        if len(idxNames) > 0:
            idx.append("INDEX `autoindex_key` (`%s`)" % "`,`".join(idxNames))
        logging.getLogger().debug("mapping: %s" % mapping)

        conn = self.factory.getDbConnection()
        try:
            cursor = conn.cursor()
            sql = "CREATE TABLE IF NOT EXISTS `%s` (%s) %s" % (table, ",".join(colsCreate+idx), LookupDB.DB_ENGINE)
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)
            cursor.close()
            conn.commit()
        except Exception, e:
            cursor.close()
            raise e

        if self.getParam('cacheAll', False):
            self.allDataCache = {}
            self.allDataCacheReady = False
            self.allDataCacheRefresh = 0

            columnSQL = '`%s`' % "`, `".join(cols)
            groupBySQL = ''
            if self.retcolsSQL == '*':
                columnSQL = '*'
            else:
                columnSQL = "%s, %s" % (self.retcolsSQL, columnSQL)
                if self.retcolsSQL.find('(') != -1:
                    groupBySQL = " GROUP BY `%s`" % "`, `".join(cols)
            self.selectAllSQL = "SELECT %s FROM `%s`%s" % (columnSQL, table, groupBySQL)

            self.__cacheAllRefresh()


    def check(self, data, *args, **keywords):
        cacheCaseSensitive = self.getParam('cacheCaseSensitive')
        param = self.getParam('param')

        if type(param) == str:
            if not cacheCaseSensitive:
                paramValue = (data.get(param, '').lower(), )
            else:
                paramValue = (data.get(param, ''), )
        else:
            paramVal = []
            for par in param:
                if not cacheCaseSensitive:
                    paramVal.append(data.get(par, '').lower())
                else:
                    paramVal.append(data.get(par, ''))
            paramValue = list(paramVal)

        ret = -1
        retEx = None

        if self.getParam('cacheAll', False):

            self.__cacheAllRefresh()
            if not self.allDataCacheReady:
                ret = 0
            else:
                retEx = self.allDataCache.get(paramValue)
                if retEx != None:
                    ret = 1

            return ret, retEx

        table = self.getParam('table')
        retcols = self.getParam('retcols')

        try:
            conn = self.factory.getDbConnection()
            cursor = conn.cursor()

            if type(param) == str:
                sqlWhere = "WHERE `%s` = %%s" % self.mapping[param]
            else:
                sqlWhereAnd = []
                for par in param:
                    sqlWhereAnd.append("`%s` = %%s" % self.mapping[par])
                sqlWhere = "WHERE %s" % " AND ".join(sqlWhereAnd)

            sql = "SELECT %s FROM `%s` %s" % (self.retcolsSQL, table, sqlWhere)

            if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                logging.getLogger().debug("SQL: %s %s" % sql, str(paramValue))
            cursor.execute(sql, paramValue)

            if int(cursor.rowcount) > 0:
                retEx = cursor.fetchone()
                if retcols != None or (retcols == None and retEx[0] > 0):
                    ret = 1
                    break

            cursor.close()
        except Exception, e:
            try:
                cursor.close()
            except:
                pass
            logging.getLogger().error("%s: database error %s" % (self.getId(), e))
            return 0, None

        return ret, retEx

