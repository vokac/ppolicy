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
    paramName, paramFunction, tableName, tableColumn

    Check returns:
        1 .... parameter was found in db
        0 .... failed to check (request doesn't include required param, database error, ...)
        -1 ... parameter was not found in db

    Examples:
        # module for checking if sender is in database table list
        define('list1', 'List', paramName="sender")
        # check if sender domain is in database table list1
        define('list1', 'List', paramName="sender", paramFunction=mailToDomain, tableName="list1")
    """

    PARAMS = { 'paramName': ('name of parameter to search in database', None),
               'paramFunction': ('use this function to preproces parameter (e.g strip username from sender address)', None),
               'tableName': ('name of database table where to search parameter', 'list'),
               'tableColumn': ('name of database column', 'name'),
               }
               

    def getId(self):
        return "%s[%s(%s,%s)]" % (self.type, self.name, self.getParam('tableName'), self.getParam('paramName'))


    def dataHash(self, data):
        paramName = self.getParam('paramName')
        return hash("=".join([ paramName, data.get(paramName) ]))


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        for attr in [ 'paramName', 'tableName', 'tableColumn' ]:
            if self.getParam(attr) == None:
                raise ParamError("%s has to be specified for this module" % attr)

        tableName = self.getParam('tableName')
        tableColumn = self.getParam('tableColumn')

        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        sql = "CREATE TABLE IF NOT EXISTS `%s` (`%s` VARCHAR(100) NOT NULL, PRIMARY KEY (`%s`))" % (tableName, tableColumn, tableColumn)
        logging.getLogger().debug("SQL: %s" % sql)
        cursor.execute(sql)
        cursor.close()


    def check(self, data):
        paramName = self.getParam('paramName')
        paramFunction = self.getParam('paramFunction', None)

        if paramFunction == None: dtaArr = [ data.get(paramName) ]
        else: dtaArr = paramFunction(data.get(paramName))

        if dtaArr in [ None, [], [ None ] ]:
            expl = "%s: no test data for %s" % (self.getId(), paramName)
            logging.getLogger().warn(expl)
            return 0, expl

        tableName = self.getParam('tableName')
        tableColumn = self.getParam('tableColumn')

        found = False
        try:
            conn = self.factory.getDbConnection()
            cursor = conn.cursor()

            for dta in dtaArr:
                sql = "SELECT COUNT(`%s`) FROM `%s` WHERE `%s` = '%s'" % (tableColumn, tableName, tableColumn, dta)
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
                row = cursor.fetchone()
                if row[0] > 0:
                    found = True
                    break

        except Exception, e:
            cursor.close()
            expl = "%s: database error" % self.getId()
            logging.getLogger().error("%s: %s" % (expl, e))
            return 0, expl

        if found: return 1, '%s: request parameter is in list' % self.getId()
        else: return -1, '%s: request parameter is not in list' % self.getId()
