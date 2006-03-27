#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Module whitch dump check data into the database
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import time
import logging
from Base import Base, ParamError


__version__ = "$Revision$"


class DumpDataDB(Base):
    """Dump data from incomming request into the database. These informations
    can be used to improve debugging of other modules or to gather
    statistical data for further analysis. This module should be safe to
    use in sense its check method doesn't raise any exception.

    Module arguments (see output of getParams method):
    tableName

    Check returns:
        this module always return 0 (undefined result)

    Examples:
        # definition for module for saving request info in default
        # database table 'dump'
        define('dumpdb1', 'DumpDataDB')
        # module that save info in custom defined table
        define('dumpdb2', 'DumpDataDB', tableName="my_dump")
    """

    PARAMS = { 'tableName': ('database where to dump data from requests', 'dump'),
               'cachePositive': (None, 0),
               'cacheNegative': (None, 0),
               }


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        tableName = self.getParam('tableName')
        if tableName == None:
            raise ParamError('tableName has to be specified for this module')

        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        sql = "CREATE TABLE IF NOT EXISTS `%s` (`id` INT NOT NULL, `key` VARCHAR(50) NOT NULL, `value` VARCHAR(1000), PRIMARY KEY (`id`, `key`))" % tableName
        logging.getLogger().debug("SQL: %s" % sql)
        cursor.execute(sql)
        cursor.close()


    def check(self, data):
        try:
            conn = self.factory.getDbConnection()
            conn.autocommit(False) # begin()
            try:
                tableName = self.getParam('tableName')
                cursor = conn.cursor()

                sql = "SELECT IF(MAX(`id`) IS NULL, 1, MAX(`id`)+1) FROM `%s`" % tableName
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)
                row = cursor.fetchone()
                newId = row[0]

                sql = "INSERT INTO `%s` (`id`, `key`, `value`) VALUES (%i, 'date', NOW())" % (tableName, newId)
                logging.getLogger().debug("SQL: %s" % sql)
                cursor.execute(sql)

                for k,v in data.items():
                    sql = "INSERT INTO `%s` (`id`, `key`, `value`) VALUES (%i, '%s', '%s')" % (tableName, newId, k, v)
                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)

                cursor.close()
                conn.commit()
            except Exception, e:
                cursor.close()
                conn.rollback
                raise e
        except Exception, e:
            logging.getLogger().error("can't write into database: %s" % e)

        return 0, "%s always return undefined" % self.getId()
