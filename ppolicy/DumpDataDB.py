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
import logging
from Base import Base, ParamError


__version__ = "$Revision$"


class DumpDataDB(Base):
    """Dump data from incomming request into the database. These informations
    can be used to improve debugging of other modules or to gather
    statistical data for further analysis. This module should be safe to
    use in sense its check method doesn't raise any exception.

    Module arguments (see output of getParams method):
    table

    Check arguments:
        data ... all input data in dict

    Check returns:
        this module always return 0 (undefined result)

    Examples:
        # definition for module for saving request info in default
        # database table 'dump'
        modules['dumpdb1'] = ( 'DumpDataDB', {} )
        # module that save info in custom defined table
        modules['dumpdb2'] = ( 'DumpDataDB', { table="my_dump" } )
    """

    PARAMS = { 'table': ('database where to dump data from requests', 'dump'),
               'cachePositive': (None, 0),
               'cacheUnknown': (None, 0),
               'cacheNegative': (None, 0),
               }


    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        table = self.getParam('table')
        if table == None:
            raise ParamError('table has to be specified for this module')

        conn = self.factory.getDbConnection()
        try:
            cursor = conn.cursor()
            sql = "CREATE TABLE IF NOT EXISTS `%s` (`id` INT NOT NULL, `key` VARCHAR(50) NOT NULL, `value` VARCHAR(1000), PRIMARY KEY (`id`, `key`))" % table
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)

            sql = "SELECT IFNULL(MAX(`id`), 1) FROM `%s`" % table
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)
            row = cursor.fetchone()
            self.newId = row[0]

            cursor.close()
        except Exception, e:
            cursor.close()
            raise e


    def check(self, data, *args, **keywords):
        newId = 0
        try:
            conn = self.factory.getDbConnection()
            try:
                table = self.getParam('table')
                cursor = conn.cursor()

                # XXX: object.lock.acquire()
                newId = self.newId
                self.newId += 1
                # XXX: object.lock.release()

                sqlData = []
                sqlData.append("(%i, 'date', NOW())" % newId)
                if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                    logging.getLogger().debug("%s" % sqlData[len(sqlData)-1])

                for k,v in data.items():
                    sqlData.append("(%i, '%s', '%s')" % (newId, k, str(v).replace("'", "\\'")))
                    if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                        logging.getLogger().debug("%s" % sqlData[len(sqlData)-1])

                sql = "INSERT INTO `%s` (`id`, `key`, `value`) VALUES %s" % (table, ",".join(sqlData))
                #logging.getLogger().debug("SQL: %s" % sql) # this is too verbose
                cursor.execute(sql)

                cursor.close()
            except Exception, e:
                cursor.close()
                raise e
        except Exception, e:
            logging.getLogger().error("can't write into database: %s" % e)

        return 0, "%s always return undefined, record #%i" % (self.getId(), newId)
