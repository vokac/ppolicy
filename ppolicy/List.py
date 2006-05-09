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
from Base import Base, ParamError


__version__ = "$Revision$"


class List(Base):
    """Check if parameter is in specified database. Can be used for
    black/white listing any of parameter comming with ppolicy requests.

    Module arguments (see output of getParams method):
    param, table, column, lower, retcol

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
        modules['list2'] = ( 'List', { param="sender",
                                       table="my_list",
                                       column="my_column",
                                       lower=True,
                                       retcol="*" } )
    """

    PARAMS = { 'param': ('name of parameter to search in database', None),
               'table': ('name of database table where to search parameter', None),
               'column': ('name of database column', None),
               'lower': ('case-insensitive search', False),
               'retcol': ('name of column returned by check method', None),
               }
               

    def getId(self):
        return "%s[%s(%s,%s)]" % (self.type, self.name, self.getParam('table'), self.getParam('param'))


    def hashArg(self, data, *args, **keywords):
        param = self.getParam('param')
        paramValue = data.get(param, '')
        if self.getParam('lower', False):
            paramValue = paramValue.lower()
        return hash("%s=%s" % (param, paramValue))


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for attr in [ 'param', 'table', 'column' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        table = self.getParam('table')
        column = self.getParam('column')

        conn = self.factory.getDbConnection()
        try:
            cursor = conn.cursor()
            sql = "CREATE TABLE IF NOT EXISTS `%s` (`%s` VARCHAR(100) NOT NULL, PRIMARY KEY (`%s`))" % (table, column, column)
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)
            cursor.close()
        except Exception, e:
            cursor.close()
            raise e


    def check(self, data, *args, **keywords):
        param = self.getParam('param')
        table = self.getParam('table')
        column = self.getParam('column')
        lower = self.getParam('lower', False)
        retcol = self.getParam('retcol')
        paramValue = data.get(param, '')

        ret = -1
        retEx = None
        try:
            conn = self.factory.getDbConnection()
            cursor = conn.cursor()

            if retcol == None:
                retcolSQL = 'COUNT(*)'
            elif type(retcol) == type([]):
                retcolSQL = "`%s`" % "`,`".join(retcol)
            elif retcol.find(',') != -1:
                retcolSQL = "`%s`" % "`,`".join(retcol.split(','))
            elif retcol != '*':
                retcolSQL = "`%s`" % retcol
            else:
                retcolSQL = retcol

            if lower:
                sql = "SELECT %s FROM `%s` WHERE LOWER(`%s`) = LOWER('%s')" % (retcolSQL, table, column, paramValue)
            else:
                sql = "SELECT %s FROM `%s` WHERE `%s` = '%s'" % (retcolSQL, table, column, paramValue)

            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)

            if int(cursor.rowcount) > 0:
                retEx = cursor.fetchone()
                if retcol != None or (retcol == None and retEx[0] > 0):
                    ret = 1

            cursor.close()
        except Exception, e:
            try:
                cursor.close()
            except:
                pass
            logging.getLogger().error("%s: database error %s" % (self.getId(), e))
            return 0, None

        return ret, retEx
