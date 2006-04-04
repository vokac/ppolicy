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
    map request parameters database columns.

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
        # module for checking if sender is in database table list
        define('list1', 'ListDyn', table='list', mapping={ "sender": "mail", })
    """

    PARAMS = { 'table': ('name of database table where to search parameter', 'list'),
               'criteria': ('names of input data keys used to identify data row(s)', None),
               'value': ('data contains value column', True),
               'softExpire': ('information that record will be soon expired (0 == never))', None),
               'hardExpire': ('expiration time for the record (0 == never)', None),
               'mapping': ('mapping between params and database columns', {}),
               'operation': ('list operation (add/remove/check)', 'check'),
               }

    COLSIZE = { 'request': 25,
                'protocol_state': 10,
                'protocol_name': 10,
                'helo_name': 255,
                'queue_id': 25,
                'sender': 255,
                'recipient': 255,
                'client_address': 25,
                'client_name': 255,
                'reverse_client_name': 255,
                'instance': 50,
                'sasl_method': 25,
                'sasl_username': 50,
                'sasl_sender': 255,
                'ccert_subject': 100,
                'ccert_issuer': 100,
                'ccert_fingerprint': 100,
                'size': 25,
                }

    def getId(self):
        return "%s[%s(%s,%s)]" % (self.type, self.name, self.getParam('table'), self.getParam('operation'))


    def hashArg(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        criteria = self.getParam('criteria')
        return hash("\n".join(map(lambda x: "%s=%s" % (x, data.get(x)), criteria)))


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for attr in [ 'table', 'criteria', 'mapping', 'operation', 'softExpire', 'hardExpire' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        table = self.getParam('table')
        criteria = self.getParam('criteria')
        value = self.getParam('value')
        mapping = self.getParam('mapping')
        operation = self.getParam('operation')
        softExpire = int(self.getParam('softExpire'))
        hardExpire = int(self.getParam('hardExpire'))

        if len(criteria) == 0:
            raise ParamError("you have to specify at least on criteria")

        if operation not in [ 'add', 'remove', 'check' ]:
            raise ParamError("unknown operation %s" % operation)

        # hash to table columns mapping
        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        cols = []
        for dictName in criteria:
            colName = mapping.get(dictName, dictName)
            cols.append("`%s` VARCHAR(%i) NOT NULL" % (colName, ListDyn.COLSIZE.get(colName, 255)))
        if value:
            colName = mapping.get('value', 'value')
            cols.append("`%s` VARCHAR(%i) NOT NULL" % (colName, ListDyn.COLSIZE.get(colName, 255)))
        if softExpire > 0:
            colName = mapping.get('soft_expire', 'soft_expire')
            cols.append("`%s` DATETIME NOT NULL" % colName)
        if hardExpire > 0:
            colName = mapping.get('hard_expire', 'hard_expire')
            cols.append("`%s` DATETIME NOT NULL" % colName)

        # create database table if not exist
        sql = "CREATE TABLE IF NOT EXISTS `%s` (%s)" % (table, ",".join(cols))
        logging.getLogger().debug("SQL: %s" % sql)
        cursor.execute(sql)
        if hardExpire > 0:
            colName = mapping.get('hard_expire', 'hard_expire')
            sql = "DELETE FROM `%s` WHERE UNIX_TIMESTAMP(`%s`) < UNIX_TIMESTAMP()" % (table, colName)
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)
        cursor.close()


    def check(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        operation = self.dataArg(1, 'operation', None, *args, **keywords)
        value = self.dataArg(2, 'value', '', *args, **keywords)
        softExpire = self.dataArg(3, 'softExpire', None, *args, **keywords)
        hardExpire = self.dataArg(4, 'hardExpire', None, *args, **keywords)

        table = self.getParam('table')
        criteria = self.getParam('criteria')
        useValue = self.getParam('value')
        mapping = self.getParam('mapping')
        if operation == None: operation = self.getParam('operation')
        if softExpire == None: softExpire = int(self.getParam('softExpire'))
        if hardExpire == None: hardExpire = int(self.getParam('hardExpire'))

        # create all parameter combinations (cartesian product)
        valX = []
        for dictName in criteria:
            colName = mapping.get(dictName, dictName)

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
        if softExpire != 0:
            colNVadd[mapping.get('soft_expire', 'soft_expire')] = "FROM_UNIXTIME(UNIX_TIMESTAMP()+%i)" % softExpire
        if hardExpire != 0:
            colNVadd[mapping.get('hard_expire', 'hard_expire')] = "FROM_UNIXTIME(UNIX_TIMESTAMP()+%i)" % hardExpire
        if useValue:
            colNVadd[mapping.get('value', 'value')] = "'%s'" % value

        # add/remove/check data in database
        retCode = -1
        retVal = []
        try:
            conn = self.factory.getDbConnection()
            cursor = conn.cursor()

            for val in valX:
                colNV = {}
                for dictName, colName, dictValue in val:
                    colNV[colName] = "'%s'" % dictValue

                where = " AND ".join([ "`%s`=%s" % (x,y) for x,y in colNV.items() ])
                if operation == 'add':
                    sql = "SELECT 1 FROM `%s` WHERE %s" % (table, where)
                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)
                    if int(cursor.rowcount) == 0:
                        colNames = "`" + "`,`".join(colNV.keys() + colNVadd.keys()) + "`"
                        colValues = ",".join(colNV.values() + colNVadd.values())
                        sql = "INSERT INTO `%s` (%s) VALUES (%s)" % (table, colNames, colValues)
                        logging.getLogger().debug("SQL: %s" % sql)
                        cursor.execute(sql)
                    else:
                        if useValue or softExpire != 0 or hardExpire != 0:
                            sfExp = []
                            if softExpire != 0:
                                colName = mapping.get('soft_expire', 'soft_expire')
                                sfExp.append("`%s`=%s" % (colName, colNVadd[colName]))
                            if hardExpire != 0:
                                colName = mapping.get('hard_expire', 'hard_expire')
                                sfExp.append("`%s`=%s" % (colName, colNVadd[colName]))
                            if useValue:
                                colName = mapping.get('value', 'value')
                                sfExp.append("`%s`=%s" % (colName, colNVadd[colName]))
                            sql = "UPDATE `%s` SET %s WHERE %s" % (table, ",".join(sfExp), where)
                            logging.getLogger().debug("SQL: %s" % sql)
                            cursor.execute(sql)
                elif operation == 'remove':
                    sql = "DELETE FROM `%s` WHERE %s" % (table, where)
                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)
                elif operation == 'check':
                    sfExp = []
                    if softExpire != 0:
                        colName = mapping.get('soft_expire', 'soft_expire')
                        sfExp.append("UNIX_TIMESTAMP(`%s`) - UNIX_TIMESTAMP() AS `%s`" % (colName, colName))
                    if hardExpire != 0:
                        colName = mapping.get('hard_expire', 'hard_expire')
                        sfExp.append("UNIX_TIMESTAMP(`%s`) - UNIX_TIMESTAMP() AS `%s`" % (colName, colName))
                    if useValue:
                        colName = mapping.get('value', 'value')
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
                        if useValue:
                            valPos = 0
                            if softExpire != 0: valPos += 1
                            if hardExpire != 0: valPos += 1
                            retVal.append((retCodeNew, row[valPos]))
                    if retCodeNew > retCode:
                        retCode = retCodeNew
                    if not useValue and retCode > 0:
                        break

            if operation != 'check':
                retCode = 1

            cursor.close()
        except Exception, e:
            cursor.close()
            expl = "%s: database error" % self.getId()
            logging.getLogger().error("%s: %s" % (expl, e))
            return 0, expl

        if operation == 'add':
            return 1, '%s: add operation successfull' % self.getId()
        elif operation == 'remove':
            return 1, '%s: remove operation successfull' % self.getId()
        elif operation == 'check':
            if useValue:
                return retCode, retVal
            else:
                return retCode, "%s: check operation" % self.getId()
