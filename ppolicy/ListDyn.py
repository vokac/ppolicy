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
    map request parameters (or its data returned by paramFunction) to
    database columns.

    Second very important parametr is "operation". With this parameter
    you specify what this module should do with passed request. Also
    result returned from check method depends on this operation.
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
    tableName, [ (paramName, paramFunction, tableColumn), ...], expiration

    Check arguments:
        data ... all input data in dict

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
        define('list1', 'ListDyn', tableName='list', mapping=[ ("sender", None, None), ])
    """

    PARAMS = { 'tableName': ('name of database table where to search parameter', 'list'),
               'mapping': ('mapping between params and database columns', None),
               'operation': ('list operation (add/remove/check)', 'check'),
               'softExpire': ('information that record will be soon expired', None),
               'hardExpire': ('expiration time for the record', None),
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
        return "%s[%s(%s,%s)]" % (self.type, self.name, self.getParam('tableName'), self.getParam('operation'))


    def hashArg(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        mapping = self.getParam('mapping')
        return hash("\n".join(map(lambda x: "%s=%s" % (x[0], data.get(x[0])), mapping)))


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for attr in [ 'tableName', 'mapping', 'operation' ]:
            if self.getParam(attr) == None:
                raise ParamError("%s has to be specified for this module" % attr)

        tableName = self.getParam('tableName')
        mapping = self.getParam('mapping')
        operation = self.getParam('operation')

        if operation not in [ 'add', 'remove', 'check' ]:
            raise ParamError("unknown operation %s" % operation)

        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        cols = []
        for param in mapping:
            if param[2] == None:
                paramCol = param[0]
            else:
                paramCol = param[2]
            cols.append("`%s` VARCHAR(%i) NOT NULL" % (paramCol, ListDyn.COLSIZE.get(paramCol, 255)))
        softExpire = self.getParam('softExpire')
        hardExpire = self.getParam('hardExpire')
        if softExpire == None or softExpire == 0:
            softExpire = ""
        else:
            softExpire = ",`soft_expire` DATETIME"
        if hardExpire == None or hardExpire == 0:
            hardExpire = ""
        else:
            hardExpire = ", `hard_expire` DATETIME"
        sql = "CREATE TABLE IF NOT EXISTS `%s` (%s%s%s)" % (tableName, ",".join(cols), softExpire, hardExpire)
        logging.getLogger().debug("SQL: %s" % sql)
        cursor.execute(sql)
        if hardExpire != "":
            sql = "DELETE FROM `%s` WHERE UNIX_TIMESTAMP(`hard_expire`) < UNIX_TIMESTAMP()" % tableName
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)
        cursor.close()


    def check(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        tableName = self.getParam('tableName')
        mapping = self.getParam('mapping')
        operation = self.getParam('operation')
        softExpire = self.getParam('softExpire')
        hardExpire = self.getParam('hardExpire')

        expireCols = ""
        expireVals = ""
        expireCheck = ""
        expireUpdate = ""
        if softExpire != None and softExpire != 0:
            expireCols += ", `soft_expire`"
            expireVals += ", FROM_UNIXTIME(UNIX_TIMESTAMP()+%i)" % softExpire
            expireCheck += ", UNIX_TIMESTAMP(`soft_expire`) - UNIX_TIMESTAMP() AS `soft_expire`"
            expireUpdate += "`soft_expire` = FROM_UNIXTIME(UNIX_TIMESTAMP()+%i)" % softExpire
        else:
            softExpire = None
        if hardExpire != None and hardExpire != 0:
            expireCols += ", `hard_expire`"
            expireVals += ", FROM_UNIXTIME(UNIX_TIMESTAMP()+%i)" % hardExpire
            expireCheck += ", UNIX_TIMESTAMP(`hard_expire`) - UNIX_TIMESTAMP() AS `hard_expire`"
            if len(expireUpdate): expireUpdate += ", "
            expireUpdate += "`hard_expire` = FROM_UNIXTIME(UNIX_TIMESTAMP()+%i)" % hardExpire
        else:
            hardExpire = None

        # create all parameter combinations (cartesian product)
        parX = []
        for param in mapping:
            paramName = param[0]
            paramFunc = param[1]
            if param[2] == None:
                paramCol = param[0]
            else:
                paramCol = param[2]

            if paramFunc == None:
                paramVal = data.get(paramName, '')
            else:
                paramVal = paramFunc(data.get(paramName))
            if type(paramVal) == tuple:
                paramVal = list(tuple)
            if type(paramVal) != list:
                paramVal = [ paramVal ]
            if paramVal == []:
                paramVal = [ '' ]
            if len(parX) == 0:
                for par in paramVal:
                    parX.append([(paramName, paramCol, par)])
            else:
                parXnew = []
                for pX in parX:
                    for par in paramVal:
                        parXnew.append(pX + [(paramName, paramCol, par)])
                parX = parXnew

        # add/remove/check data in database
        retVal = 0
        try:
            conn = self.factory.getDbConnection()
            cursor = conn.cursor()

            for par in parX:
                parCols = []
                parValues = []
                parCV = []
                for parName, parCol, parValue in par:
                    parCols.append(parCol)
                    parValues.append(parValue)
                    parCV.append("`%s`='%s'" % (parCol, parValue))

                if operation == 'add':
                    sql = "SELECT 1 AS `xxx` FROM `%s` WHERE %s" % (tableName, " AND ".join(parCV))
                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)
                    if int(cursor.rowcount) == 0:
                        sql = "INSERT INTO `%s` (`%s`%s) VALUES ('%s'%s)" % (tableName, "`,`".join(parCols), expireCols, "','".join(parValues), expireVals)
                        logging.getLogger().debug("SQL: %s" % sql)
                        cursor.execute(sql)
                    else:
                        if len(expireUpdate) > 0:
                            sql = "UPDATE `%s` SET %s WHERE %s" % (tableName, expireUpdate, " AND ".join(parCV))
                            logging.getLogger().debug("SQL: %s" % sql)
                            cursor.execute(sql)
                elif operation == 'remove':
                    sql = "DELETE FROM `%s` WHERE %s" % (tableName, " AND ".join(parCV))
                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)
                elif operation == 'check':
                    sql = "SELECT 1 AS `xxx`%s FROM `%s` WHERE %s" % (expireCheck, tableName, " AND ".join(parCV))
                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)
                    if int(cursor.rowcount) > 0:
                        row = cursor.fetchone()
                        retVal = 1
                        if softExpire != None:
                            if row[1] < 0:
                                retVal = 2
                        if hardExpire != None:
                            if softExpire != None:
                                if row[2] < 0:
                                    retVal = -1
                            else:
                                if row[1] < 0:
                                    retVal = -1
                        break

            if operation != 'check':
                retVal = 1

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
            if retVal > 0: return 1, '%s: request parameter is in list' % self.getId()
            else: return -1, '%s: request parameter is not in list' % self.getId()
