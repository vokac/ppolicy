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
    'dictName': ('columnName', 'columnType', escape, lower), ...],
    where dictName is attribude name comming in check method in data
    dictionary, columnName is database column name, column type is
    database column type in SQL syntax, escape is boolean value that
    identifies text columns that's text should be escaped and lower
    sais that data will be comparet case-insensitive. If don't define
    mapping for concrete column, than default is used 'dictName':
    ('dictName', 'VARCHAR(255)', True, False)

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
        modules['list1'] = ( 'ListDyn', { table='list1',
                                          mapping={ "sender": "mail", } } )
        # module for checking/getting if sender row values in database table list2
        modules['list2'] = ( 'ListDyn', { table='list2',
                                          mapping={ "sender": ("mail", "VARCHAR(50)", True, True), },
                                          value=["data1"] } )
        # module with soft/hard expiration and 'add' as default operation
        modules['list3'] = ( 'ListDyn', { table='list3', operation='add',
                                          softExpire=60*10, hardExpire=60*30 } )
    """

    CHECK_SOFT_EXPIRED=2

    PARAMS = { 'table': ('name of database table where to search parameter', 'list'),
               'criteria': ('names of input data keys used to identify data row(s)', None),
               'value': ('names of value columns (None mean no related data)', None),
               'softExpire': ('information that record will be soon expired (0 == never))', None),
               'hardExpire': ('expiration time for the record (0 == never)', None),
               'mapping': ('mapping between params and database columns', {}),
               'operation': ('list operation (add/remove/check)', 'check'),
               'cachePositive': (None, 0), # don't cache results in memory
               'cacheUnknown': (None, 0),  # it is possible to use this cache, but it
               'cacheNegative': (None, 0), # needs some changes in current code
               }
    DB_ENGINE="ENGINE=InnoDB"


    def __mapping(self, dictName, defType = 'VARCHAR(255)', defEsc = True, defLower = False):
        mapping = self.getParam('mapping')
        colDef = mapping.get(dictName)

        if colDef == None:
            mapping[dictName] = (dictName, defType, defEsc, defLower)
        elif type(colDef) == str:
            mapping[dictName] = (colDef, defType, defEsc, defLower)
        elif type(colDef) != list and type(colDef) != tuple:
            raise ParamError("invalid arguments for %s: %s" % (dictName, str(colDef)))
        elif len(colDef) == 1:
            mapping[dictName] = (colDef[0], defType, defEsc, defLower)
        elif len(colDef) == 2:
            mapping[dictName] = (colDef[0], colDef[1], defEsc, defLower)
        elif len(colDef) == 3:
            mapping[dictName] = (colDef[0], colDef[1], colDef[2], defLower)
        elif len(colDef) >= 4:
            if len(colDef) > 4:
                logging.getLogger().warn("too many arguments for %s: %s" % (dictName, str(colDef)))
            mapping[dictName] = (colDef[0], colDef[1], colDef[2], colDef[3])

        colDef = list(mapping.get(dictName))
        if colDef[0] == None: colDef[0] = dictName
        if colDef[1] == None: colDef[1] = defType
        if colDef[2] == None: colDef[2] = defEsc
        if colDef[3] == None: colDef[3] = defEsc
        mapping[dictName] = (colDef[0], colDef[1], colDef[2], colDef[3])
        
        return mapping.get(dictName)


    def getId(self):
        return "%s[%s(%s,%s)]" % (self.type, self.name, self.getParam('table'), self.getParam('operation'))


    def hashArg(self, data, *args, **keywords):
        criteria = self.getParam('criteria')
        return hash("\n".join(map(lambda x: "%s=%s" % (x, data.get(x)), criteria)))


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for attr in [ 'table', 'criteria', 'operation', 'softExpire', 'hardExpire' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        table = self.getParam('table')
        criteria = self.getParam('criteria')
        value = self.getParam('value', [])
        operation = self.getParam('operation')
        softExpire = int(self.getParam('softExpire'))
        hardExpire = int(self.getParam('hardExpire'))

        if len(criteria) == 0:
            raise ParamError("you have to specify at least on criteria")

        if operation not in [ 'add', 'remove', 'check' ]:
            raise ParamError("unknown operation %s" % operation)

        # hash to table columns mapping
        cols = []
        idx = []
        for dictName in criteria:
            colName, colType, colEsc, colLower = self.__mapping(dictName)
            cols.append("`%s` %s" % (colName, colType))
        for dictName in value:
            colName, colType, colEsc, colLower = self.__mapping(dictName)
            cols.append("`%s` %s" % (colName, colType))
            idx.append("INDEX `autoindex_%s` (`%s`)" % (colName, colName))
        if softExpire > 0:
            dictName = 'soft_expire'
            colName, colType, colEsc, colLower = self.__mapping(dictName, 'DATETIME NOT NULL', False)
            cols.append("`%s` %s" % (colName, colType))
        if hardExpire > 0:
            dictName = 'hard_expire'
            colName, colType, colEsc, colLower = self.__mapping(dictName, 'DATETIME NOT NULL', False)
            cols.append("`%s` %s" % (colName, colType))
        logging.getLogger().debug("mapping: %s" % self.getParam('mapping'))

        # create database table if not exist
        conn = self.factory.getDbConnection()
        try:
            cursor = conn.cursor()
            sql = "CREATE TABLE IF NOT EXISTS `%s` (%s) %s" % (table, ",".join(cols+idx), ListDyn.DB_ENGINE)
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)
            if hardExpire > 0:
                colName, colType, colEsc, colLower = self.__mapping(dictName)
                sql = "DELETE FROM `%s` WHERE UNIX_TIMESTAMP(`%s`) < UNIX_TIMESTAMP()" % (table, colName)
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
            cursor.close()
            conn.commit()
        except Exception, e:
            cursor.close()
            raise e


    def check(self, data, *args, **keywords):
        operation = self.dataArg(0, 'operation', None, *args, **keywords)
        value = self.dataArg(1, 'value', None, *args, **keywords)
        softExpire = self.dataArg(2, 'softExpire', None, *args, **keywords)
        hardExpire = self.dataArg(3, 'hardExpire', None, *args, **keywords)

        table = self.getParam('table')
        criteria = self.getParam('criteria')
        valueCols = self.getParam('value', [])
        if operation == None: operation = self.getParam('operation')
        if softExpire == None: softExpire = int(self.getParam('softExpire'))
        if hardExpire == None: hardExpire = int(self.getParam('hardExpire'))

        logging.getLogger().debug("%s; %s; %s; %s; %s; %s; %s; %s" % (data, operation, value, softExpire, hardExpire, table, criteria, valueCols))

        # create all parameter combinations (cartesian product)
        valX = []
        for dictName in criteria:
            colName, colType, colEsc, colLower = self.__mapping(dictName)
            dictVal = data.get(dictName, '')
            if type(dictVal) == tuple:
                dictVal = list(tuple)
            if type(dictVal) != list:
                dictVal = [ dictVal ]
            if dictVal == []:
                dictVal = [ '' ]
            if len(valX) == 0:
                for val in dictVal:
                    if colEsc: val = "'%s'" % val.replace("'", "\\'")
                    if colLower: val = "LOWER(%s)" % val
                    valX.append([(dictName, colName, val)])
            else:
                valXnew = []
                for pX in valX:
                    for val in dictVal:
                        if colEsc: val = "'%s'" % val.replace("'", "\\'")
                        if colLower: val = "LOWER(%s)" % val
                        valXnew.append(pX + [(dictName, colName, val)])
                valX = valXnew

        colNVadd = {}
        if operation == 'add':
            for dictName in valueCols:
                colName, colType, colEsc, colLower = self.__mapping(dictName)
                dictVal = value.get(dictName, '')
                if colEsc: dictVal = "'%s'" % dictVal.replace("'", "\\'")
                if colLower: dictVal = "LOWER(%s)" % dictVal
                colNVadd[colName] = dictVal
        if softExpire != 0:
            colName, colType, colEsc, colLower = self.__mapping('soft_expire')
            colNVadd[colName] = "FROM_UNIXTIME(UNIX_TIMESTAMP()+%i)" % softExpire
        if hardExpire != 0:
            colName, colType, colEsc, colLower = self.__mapping('hard_expire')
            colNVadd[colName] = "FROM_UNIXTIME(UNIX_TIMESTAMP()+%i)" % hardExpire

        # add/remove/check data in database
        retCode = -1
        retVal = []
        try:
            conn = self.factory.getDbConnection()
            cursor = conn.cursor()

            for val in valX:
                colNV = {}
                for dictName, colName, dictValue in val:
                    colNV[colName] = dictValue
                where = " AND ".join([ "`%s`=%s" % (x,y) for x,y in colNV.items() ])
                # add
                if operation == 'add':
                    sql = "SELECT 1 FROM `%s` WHERE %s" % (table, where)
                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)
                    if int(cursor.rowcount) == 0:
                        colNames = "`" + "`,`".join(colNV.keys() + colNVadd.keys()) + "`"
                        colValues = ",".join([ str(x) for x in colNV.values() + colNVadd.values() ])
                        sql = "INSERT INTO `%s` (%s) VALUES (%s)" % (table, colNames, colValues)
                        logging.getLogger().debug("SQL: %s" % sql)
                        cursor.execute(sql)
                    else:
                        if len(valueCols) > 0 or softExpire != 0 or hardExpire != 0:
                            sfExp = []
                            if softExpire != 0:
                                colName, colType, colEsc, colLower = self.__mapping('soft_expire')
                                sfExp.append("`%s`=%s" % (colName, colNVadd[colName]))
                            if hardExpire != 0:
                                colName, colType, colEsc, colLower = self.__mapping('hard_expire')
                                sfExp.append("`%s`=%s" % (colName, colNVadd[colName]))
                            for dictName in valueCols:
                                colName, colType, colEsc, colLower = self.__mapping(dictName)
                                sfExp.append("`%s`=%s" % (colName, colNVadd[colName]))
                            sql = "UPDATE `%s` SET %s WHERE %s" % (table, ",".join(sfExp), where)
                            logging.getLogger().debug("SQL: %s" % sql)
                            cursor.execute(sql)
                # remove
                elif operation == 'remove':
                    sql = "DELETE FROM `%s` WHERE %s" % (table, where)
                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)
                # check
                elif operation == 'check':
                    sfExp = []
                    if softExpire != 0:
                        colName, colType, colEsc, colLower = self.__mapping('soft_expire')
                        sfExp.append("UNIX_TIMESTAMP(`%s`) - UNIX_TIMESTAMP() AS `%s`" % (colName, colName))
                    else:
                        sfExp.append("1") # fake column
                    if hardExpire != 0:
                        colName, colType, colEsc, colLower = self.__mapping('hard_expire')
                        sfExp.append("UNIX_TIMESTAMP(`%s`) - UNIX_TIMESTAMP() AS `%s`" % (colName, colName))
                    else:
                        sfExp.append("1") # fake column
                    for dictName in valueCols:
                        colName, colType, colEsc, colLower = self.__mapping(dictName)
                        sfExp.append("`%s`" % colName)
                    if len(sfExp) == 0:
                        sfExp.append("1")
                    sql = "SELECT %s FROM `%s` WHERE %s" % (",".join(sfExp), table, where)
                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)
                    retCodeNew = -1
                    if int(cursor.rowcount) > 0:
                        retCodeNew = 1
                        row = cursor.fetchone()
                        if softExpire != 0 and row[0] < 0:
                            retCodeNew = 2
                        if hardExpire != 0 and row[1] < 0:
                            retCodeNew = -1
                        if len(valueCols) > 0:
                            retValRow = [ retCodeNew ]
                            for i in range(0, len(valueCols)):
                                retValRow.append(row[i+2])
                            retVal.append(retValRow)
                    if retCodeNew > retCode:
                        retCode = retCodeNew
                    if len(valueCols) == 0 and retCode > 0:
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

        if operation == 'add':
            return 1, '%s: add operation successfull' % self.getId()
        elif operation == 'remove':
            return 1, '%s: remove operation successfull' % self.getId()
        elif operation == 'check':
            if valueCols != None:
                return retCode, retVal
            else:
                return retCode, "%s: check operation" % self.getId()
