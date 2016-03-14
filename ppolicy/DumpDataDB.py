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
import time
import threading
from Base import Base, ParamError


__version__ = "$Revision$"


class DumpDataDB(Base):
    """Dump data from incomming request into the database. These informations
    can be used to improve debugging of other modules or to gather
    statistical data for further analysis. This module should be safe to
    use in sense its check method doesn't raise any exception.

    Module arguments (see output of getParams method):
    table, split, interval

    Check arguments:
        data ... all input data in dict

    Check returns:
        this module always return 1 and resEx is set to the new database ID

    Examples:
        # definition for module for saving request info in default
        # database table 'dump'
        modules['dumpdb1'] = ( 'DumpDataDB', {} )
        # module that save info in custom defined table
        modules['dumpdb2'] = ( 'DumpDataDB', { table="my_dump" } )
    """

    PARAMS = { 'table': ('database where to dump data from requests', 'dump'),
               'split': ('split database (None, "records", "date")', None),
               'interval': ('split interval (value depends on split type)', None),
               # 'rotate': ('drop old tables (number you want to preserve)', None)
               'cachePositive': (None, 0),
               'cacheUnknown': (None, 0),
               'cacheNegative': (None, 0),
               }
    DB_ENGINE="ENGINE=InnoDB"


    def __getTable(self):
        table = self.getParam('table')
        split = self.getParam('split')
        if split == None:
            if self.newId == None:
                self.__createTable()
            return
        if split == 'records':
            
            if self.rowCount == None:
                conn = self.factory.getDbConnection()
                cursor = conn.cursor()
                try:
                    sql = "SELECT COUNT(*) FROM `%s`" % table
                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)
                    (self.rowCount, ) = cursor.fetchone()
                except Exception, e:
                    cursor.close()
                    raise e
                cursor.close()
                conn.commit()
                #self.factory.releaseDbConnection(conn)
            interval = self.getParam('interval')
            if interval == None:
                raise Exception('unknown interval for number of records')
            if self.rowCount > interval:
                self.rowCount = 0
                newName = "%s%s" % (table, time.strftime("%Y%m%d%H%M", time.localtime()))
                self.__renameTable(newName)
                self.__createTable()
            return
        if split == 'date':
            if self.rowDate == None:
                conn = self.factory.getDbConnection()
                cursor = conn.cursor()
                try:
                    sql = "SELECT `value` FROM `%s` WHERE `key` = 'date' ORDER BY `id` LIMIT 1" % table
                    logging.getLogger().debug("SQL: %s" % sql)
                    cursor.execute(sql)
                    if cursor.rowcount == 0:
                        self.rowDate = time.localtime()
                    else:
                        self.rowDate = time.strptime(cursor.fetchone()[0], "%Y-%m-%d %H:%M:%S")
                except Exception, e:
                    cursor.close()
                    raise e
                cursor.close()
                #self.factory.releaseDbConnection(conn)
            newName = None
            curDate = time.localtime()
            interval = self.getParam('interval')
            if interval == 'day' and (self.rowDate[0] != curDate[0] or self.rowDate[1] != curDate[1] or self.rowDate[2] != curDate[2]):
                newName = "%s%s" % (table, time.strftime("%Y%m%d", time.localtime()))
            elif interval == 'week' and ((self.rowDate[6] != curDate[6] and curDate[7] == 0) or curDate[7] - self.rowDate[7] > 7):
                newName = "%s%s" % (table, time.strftime("%Y%m%d", time.localtime()))
            elif interval == 'month' and (self.rowDate[0] != curDate[0] or self.rowDate[1] != curDate[1]):
                newName = "%s%s" % (table, time.strftime("%Y%m", time.localtime()))
            elif interval == 'year' and (self.rowDate[0] != curDate[0]):
                newName = "%s%s" % (table, time.strftime("%Y", time.localtime()))
            else:
                raise Exception("unknown date interval %s" % interval)
            if newName != None:
                self.rowDate = time.localtime()
                self.__renameTable(newName)
                self.__createTable()
            return
        raise Exception("unknown split type %s" % split)


    def __createTable(self):
        table = self.getParam('table')
        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        try:
            sql = "CREATE TABLE IF NOT EXISTS `%s` (`id` INT NOT NULL, `key` VARCHAR(50) NOT NULL, `value` VARCHAR(1000), PRIMARY KEY (`id`, `key`)) %s" % (table, DumpDataDB.DB_ENGINE)
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)

            sql = "SELECT IFNULL(MAX(`id`), 0) FROM `%s`" % table
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)
            row = cursor.fetchone()
            self.newId = row[0]+1
        except Exception, e:
            cursor.close()
            raise e
        cursor.close()
        conn.commit()
        #self.factory.releaseDbConnection(conn)

        
    def __renameTable(self, newName):
        table = self.getParam('table')
        conn = self.factory.getDbConnection()
        cursor = conn.cursor()
        try:
            sql = "RENAME TABLE `%s` TO `%s`" % (table, newName)
            logging.getLogger().debug("SQL: %s" % sql)
            cursor.execute(sql)
        except Exception, e:
            cursor.close()
            raise e
        cursor.close()
        conn.commit()
        #self.factory.releaseDbConnection(conn)

        
    def start(self):
        if self.factory == None:
            raise ParamError("this module need reference to fatory and database connection pool")

        table = self.getParam('table')
        if table == None:
            raise ParamError('table has to be specified for this module')

        # initialize database table and newId, rowCount, ...
        self.newId = None
        self.newIdLock = threading.Lock()
        self.rowCount = None
        self.rowDate = None
        self.__getTable()


    def check(self, data, *args, **keywords):
        newId = 0
        try:
            conn = self.factory.getDbConnection()
            cursor = conn.cursor()
            try:
                table = self.getParam('table')

                with self.newIdLock:
                    newId = self.newId
                    self.newId += 1

                sqlData = []
                sqlData.append("(%i, 'date', NOW())" % newId)
                if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                    logging.getLogger().debug("%s" % sqlData[len(sqlData)-1])

                for k,v in data.items():
                    sqlData.append("(%i, '%s', '%s')" % (newId, k, str(v).replace('\\', '\\\\').replace(r"'",r"\'")))
                    if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
                        logging.getLogger().debug("%s" % sqlData[len(sqlData)-1])

                sql = "INSERT INTO `%s` (`id`, `key`, `value`) VALUES %s" % (table, ",".join(sqlData))
                #logging.getLogger().debug("SQL: %s" % sql) # this is too verbose
                cursor.execute(sql)

                cursor.close()
                conn.commit()
            except Exception, e:
                cursor.close()
                raise e
            #self.factory.releaseDbConnection(conn)
        except Exception, e:
            logging.getLogger().error("can't write into database: %s" % e)
            return -1, None

        return 1, newId

