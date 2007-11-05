#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# This module provide general access add/remove/check to the database table
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
from Base import Base, ParamError


__version__ = "$Revision$"


class ListDyn(Base):
    """This module provide general access (add/remove/check) to the
    persistent data store in database. You can use this module for
    black/white lists, persistent data cache for result from other
    modules, ...

    One of the most important parameter is "mapping". It is used to
    map request parameters database columns. Its syntax is [
    'dictName': ('columnName', 'columnType'), ...],
    where dictName is attribude name comming in check method in data
    dictionary, columnName is database column name, column type is
    database column type in SQL syntax. If don't define mapping for
    concrete column, than default is used 'dictName':
    ('dictName', 'VARCHAR(255)')

    Second very important parametr is "operation". With this parameter
    you specify what this module should do by default with passed request.
    Also result returned from check method depends on this operation.
    add ...... add new data to database
    remove ... remove all matching data from database
    check .... check if database include data from request

    You can also set soft and hard expiration time for the
    records. For example you can specify, that after 1 hour it will
    return SOFT_NEGATIVE constant and after 2 hours
    HARD_NEGATIVE. This can be usefull when you use this module as
    persistent cache for some other module and you are not sure that
    the its results are always reachable (e.g. when it uses DNS and it
    is temporarly unreachable).

    Module arguments (see output of getParams method):
    table, columns, [ (paramName, tableColumn), ...], expiration

    Check arguments:
        data ... all input data in dict
        operation ... add/remove/check operation that overide the default

    Check returns:
        add, remove
            1 .... operation was successfull
            0 .... error (database error, ...)
        check
            2 .... parameters are in list, but soft expired
            1 .... parameters are in list
            0 .... failed to check (database error, ...)
            -1 ... parameters are not in list

    Examples:
        # module for checking if sender is in database table list1
        modules['list1'] = ( 'ListDyn', { 'table': 'list1',
                'mapping': { "sender": "mail", } } )
        # module for checking/getting if sender row values in database table list2
        modules['list2'] = ( 'ListDyn', { 'table': 'list2',
                'param': 'sender', 'retcols': [ "recip" ],
                'mapping': { "sender": ("mail", "VARCHAR(50)"),
                             "recip": ("rmail", "VARCHAR(50)") },
                 } )
        # module with soft/hard expiration and 'add' as default operation
        modules['list3'] = ( 'ListDyn', { 'table': 'list3', 'operation': 'add',
                'softExpire': 60*10, 'hardExpire': 60*30 } )
    """

    CHECK_SOFT_EXPIRED=2

    PARAMS = { 'param': ('names of input data keys used to identify data row(s)', None),
               'table': ('name of database table where to search parameter', 'list'),
               'retcols': ('names of columns to be returned (None mean no related data)', None),
               'softExpire': ('information that record will be soon expired (0 == never))', None),
               'hardExpire': ('expiration time for the record (0 == never)', None),
               'mapping': ('mapping between params and database columns', {}),
               'operation': ('list operation (add/remove/check)', 'check'),
               'cachePositive': (None, 0), # don't cache results in memory
               'cacheUnknown': (None, 0),  # it is possible to use this cache, but it
               'cacheNegative': (None, 0), # needs some changes in current code
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


    def getId(self):
        return "%s[%s(%s,%s)]" % (self.type, self.name, self.getParam('table'), self.getParam('operation'))


    def hashArg(self, data, *args, **keywords):
        param = self.getParam('param')
        return hash("\n".join([ lambda x: "%s=%s" % (x, data.get(x)) for x in param ]))


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for attr in [ 'table', 'param', 'operation', 'softExpire', 'hardExpire' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        param = self.getParam('param')
        table = self.getParam('table')
        retcols = self.getParam('retcols', [])
        operation = self.getParam('operation')
        mapping = self.getParam('mapping', {})
        softExpire = int(self.getParam('softExpire'))
        hardExpire = int(self.getParam('hardExpire'))

        if len(param) == 0:
            raise ParamError("you have to specify at least on param")

        if type(param) == str:
            param = [ param ]

        if operation not in [ 'add', 'remove', 'check' ]:
            raise ParamError("unknown operation %s" % operation)

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
        for dictName in retcols:
            self.__addCol(self.mapping, dictName, mappingType.get(dictName), cols, colsCreate)

        idx = []
        if len(idxNames) > 0:
            idx.append("INDEX `autoindex_key` (`%s`)" % "`,`".join(idxNames))
        logging.getLogger().debug("mapping: %s" % mapping)

        # create database table if not exist
        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        try:
            sql = "CREATE TABLE IF NOT EXISTS `%s` (%s) %s" % (table, ",".join(colsCreate+idx), ListDyn.DB_ENGINE)
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)
            if hardExpire > 0:
                colName = self.mapping['hard_expire']
                sql = "DELETE FROM `%s` WHERE UNIX_TIMESTAMP(`%s`) < UNIX_TIMESTAMP()" % (table, colName)
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
            cursor.close()
            conn.commit()
        except Exception, e:
            cursor.close()
            raise e
        #self.factory.releaseDbConnection(conn)


    def check(self, data, *args, **keywords):
        operation = self.dataArg(0, 'operation', None, *args, **keywords)
        value = self.dataArg(1, 'value', None, *args, **keywords)
        softExpire = self.dataArg(2, 'softExpire', None, *args, **keywords)
        hardExpire = self.dataArg(3, 'hardExpire', None, *args, **keywords)

        table = self.getParam('table')
        param = self.getParam('param')
        retcols = self.getParam('retcols', [])
        if operation == None: operation = self.getParam('operation')
        if softExpire == None: softExpire = int(self.getParam('softExpire'))
        if hardExpire == None: hardExpire = int(self.getParam('hardExpire'))

        if type(param) == str:
            param = [ param ]

        logging.getLogger().debug("%s; %s; %s; %s; %s; %s; %s; %s" % (data, operation, value, softExpire, hardExpire, table, param, retcols))

        # create all parameter combinations (cartesian product)
        valX = []
        for dictName in param:
            colName = self.mapping[dictName]
            dictVal = data.get(dictName, '')
            if type(dictVal) == tuple:
                dictVal = list(tuple)
            if type(dictVal) != list:
                dictVal = [ dictVal ]
            if dictVal == []:
                dictVal = [ '' ]
            if len(valX) == 0:
                for val in dictVal:
                    valX.append([(dictName, colName, val)])
            else:
                valXnew = []
                for pX in valX:
                    for val in dictVal:
                        valXnew.append(pX + [(dictName, colName, val)])
                valX = valXnew

        colNVadd = {}
        if operation == 'add':
            for dictName in retcols:
                colName = self.mapping[dictName]
                colNVadd[colName] = value.get(dictName, '')

        # add/remove/check data in database
        retCode = -1
        retVal = []

        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        try:

            for val in valX:
                colNV = {}
                for dictName, colName, dictValue in val:
                    colNV[colName] = dictValue
                whereAnd = []
                whereData = []
                for cn, cv in colNV.items():
                    whereAnd.append("`%s`=%%s" % cn)
                    whereData.append(cv)
                where = " AND ".join(whereAnd)
                # add
                if operation == 'add':
                    sql = "SELECT 1 FROM `%s` WHERE %s" % (table, where)
                    logging.getLogger().debug("SQL: %s %s" % (sql, str(tuple(whereData))))
                    cursor.execute(sql, tuple(whereData))
                    if int(cursor.rowcount) == 0:
                        colNames = colNVadd.keys()
                        colValues = colNVadd.values()
                        colExpire = []
                        if softExpire != 0:
                            colNames.append(self.mapping['soft_expire'])
                            colExpire.append("FROM_UNIXTIME(UNIX_TIMESTAMP()+%i)" % softExpire)
                        if hardExpire != 0:
                            colNames.append(self.mapping['hard_expire'])
                            colExpire.append("FROM_UNIXTIME(UNIX_TIMESTAMP()+%i)" % hardExpire)
                        sql = "INSERT INTO `%s` (`%s`) VALUES (%s)" % (table, "`,`".join(colNames), ",".join([ "\%s" for x in colValues ] + colExpire))
                        logging.getLogger().debug("SQL: %s %s" % (sql, str(tuple(colValues))))
                        cursor.execute(sql, tuple(colValues))
                    else:
                        if len(retcols) > 0 or softExpire != 0 or hardExpire != 0:
                            sfExp = []
                            sfVal = []
                            if softExpire != 0:
                                colName = self.mapping['soft_expire']
                                sfExp.append("`%s`=FROM_UNIXTIME(UNIX_TIMESTAMP()+%i)" % (colName, softExpire))
                            if hardExpire != 0:
                                colName = self.mapping['hard_expire']
                                sfExp.append("`%s`=FROM_UNIXTIME(UNIX_TIMESTAMP()+%i)" % (colName, hardExpire))
                            for dictName in retcols:
                                colName = self.mapping[dictName]
                                sfExp.append("`%s`=%%s" % colName)
                                sfVal.append(colNVadd[colName])
                            sql = "UPDATE `%s` SET %s WHERE %s" % (table, ",".join(sfExp), where)
                            logging.getLogger().debug("SQL: %s %s" % (sql, str(tuple(sfVal+whereData))))
                            cursor.execute(sql, tuple(sfVal+whereData))
                # remove
                elif operation == 'remove':
                    sql = "DELETE FROM `%s` WHERE %s" % (table, where)
                    logging.getLogger().debug("SQL: %s %s" % (sql, str(tuple(whereData))))
                    cursor.execute(sql, tuple(whereData))
                # check
                elif operation == 'check':
                    sfExp = []
                    if softExpire != 0:
                        colName = self.mapping['soft_expire']
                        sfExp.append("UNIX_TIMESTAMP(`%s`) - UNIX_TIMESTAMP() AS `%s`" % (colName, colName))
                    else:
                        sfExp.append("1") # fake column
                    if hardExpire != 0:
                        colName = self.mapping['hard_expire']
                        sfExp.append("UNIX_TIMESTAMP(`%s`) - UNIX_TIMESTAMP() AS `%s`" % (colName, colName))
                    else:
                        sfExp.append("1") # fake column
                    for dictName in retcols:
                        colName = self.mapping[dictName]
                        sfExp.append("`%s`" % colName)
                    if len(sfExp) == 0:
                        sfExp.append("1")
                    sql = "SELECT %s FROM `%s` WHERE %s" % (",".join(sfExp), table, where)
                    logging.getLogger().debug("SQL: %s %s" % (sql, str(tuple(whereData))))
                    cursor.execute(sql, tuple(whereData))
                    retCodeNew = -1
                    if int(cursor.rowcount) > 0:
                        retCodeNew = 1
                        row = cursor.fetchone()
                        if softExpire != 0 and row[0] < 0:
                            retCodeNew = 2
                        if hardExpire != 0 and row[1] < 0:
                            retCodeNew = -1
                        if len(retcols) > 0:
                            retValRow = [ retCodeNew ]
                            for i in range(0, len(retcols)):
                                retValRow.append(row[i+2])
                            retVal.append(retValRow)
                    if retCodeNew > retCode:
                        retCode = retCodeNew
                    if len(retcols) == 0 and retCode > 0:
                        break

            if operation != 'check':
                retCode = 1

            cursor.close()
            conn.commit()
        except Exception, e:
            try:
                cursor.close()
            except:
                pass
            expl = "%s: database error" % self.getId()
            logging.getLogger().error("%s: %s" % (expl, e))
            return 0, expl
        #self.factory.releaseDbConnection(conn)

        if operation == 'add':
            return 1, '%s: add operation successfull' % self.getId()
        elif operation == 'remove':
            return 1, '%s: remove operation successfull' % self.getId()
        elif operation == 'check':
            if retcols != None:
                return retCode, retVal
            else:
                return retCode, "%s: check operation" % self.getId()
