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
    param, table, column

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... parameter was found in db
        0 .... failed to check (request doesn't include required param, database error, ...)
        -1 ... parameter was not found in db

    Examples:
        # module for checking if sender is in database table list
        modules['list1'] = ( 'List', { param="sender" } )
        # check if sender domain is in database table my_list
        modules['list2'] = ( 'List', { param="sender", table="my_list" } )
    """

    PARAMS = { 'param': ('name of parameter to search in database', None),
               'table': ('name of database table where to search parameter', None),
               'column': ('name of database column', None),
               }
               

    def getId(self):
        return "%s[%s(%s,%s)]" % (self.type, self.name, self.getParam('table'), self.getParam('param'))


    def hashArg(self, data, *args, **keywords):
        param = self.getParam('param')
        return hash("=".join([ param, data.get(param) ]))


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for attr in [ 'param', 'table', 'column' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        table = self.getParam('table')
        column = self.getParam('column')

        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        sql = "CREATE TABLE IF NOT EXISTS `%s` (`%s` VARCHAR(100) NOT NULL, PRIMARY KEY (`%s`))" % (table, column, column)
        logging.getLogger().debug("SQL: %s" % sql)
        cursor.execute(sql)
        cursor.close()


    def check(self, data, *args, **keywords):
        param = self.getParam('param')
        table = self.getParam('table')
        column = self.getParam('column')
        paramValue = data.get(param, '')

        found = False
        try:
            conn = self.factory.getDbConnection()
            cursor = conn.cursor()

            sql = "SELECT COUNT(*) FROM `%s` WHERE `%s` = '%s'" % (table, column, paramValue)
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)
            row = cursor.fetchone()
            if row[0] > 0:
                found = True
            cursor.close()
        except Exception, e:
            cursor.close()
            expl = "%s: database error" % self.getId()
            logging.getLogger().error("%s: %s" % (expl, e))
            return 0, expl

        if found: return 1, '%s: request parameter is in list' % self.getId()
        else: return -1, '%s: request parameter is not in list' % self.getId()
