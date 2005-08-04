#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Tasks:
#   Dummy
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import time
from twisted.python import log


class NotImplementedException(Exception):
    pass



class PPolicyServerTaskBase:


    def __init__(self, interval = 60, *args, **keywords):
        self._id = self.__class__.__name__
        self._interval = interval
        self.setParams(*keywords)


    def getId(self):
        """get module identification."""
        return self._id


    def getInterval(self):
        """get interval for calling doTask."""
        return self._interval


    def setParams(self, *args, **keywords):
        """set 'debug' log level for this module
        debug:
          0 ... quiet (default)
          1 ... verbose
        """
        self.debug = keywords.get('debug', 0)


    def doTask(self):
        """This method will be called regularly according configuration.
        It has to be redefined in child classes."""
        raise NotImplementedException("Don't call base class directly")


    def doStart(self, *args, **keywords):
        """Called by protocol factory once before starting task loop."""
        pass


    def doStop(self, *args, **keywords):
        """Called by protocol factory before shutdown."""
        pass



class DummyTask(PPolicyServerTaskBase):
    """Dummy Task doing nothing except logging."""

    def __init__(self, interval = 60, *args, **keywords):
        PPolicyServerTaskBase.__init__(self, interval, *keywords)


    #def setParams(self, *args, **keywords):
    #    PPolicyServerTaskBase.setParams(self, *keywords)


    def doTask(self):
        log.msg("[DBG] running task: %s" % self.getId())


class StateRestarterTask(PPolicyServerTaskBase):
    """Task for checking module state. It tries to restart/reload
    module configuration if it is not in 'ready' state."""

    def __init__(self, interval = 60, *args, **keywords):
        self.checks = []
        PPolicyServerTaskBase.__init__(self, interval, *keywords)


    def setParams(self, *args, **keywords):
        PPolicyServerTaskBase.setParams(self, *keywords)
        self.checks = keywords.get('checks', self.checks)


    def doTask(self):
        log.msg("[DBG] running task: %s" % self.getId())
        for check in self.checks:
            if check.getState() != 'ready':
                log.msg("[DBG] Check state: %s not ready - restarting" %
                        check.getId())
                check.doRestartInt()



class DatabaseCleanupTask(PPolicyServerTaskBase):
    """Cleanup expired records from database."""

    def __init__(self, interval = 60, *args, **keywords):
        self.table = None
        self.column = 'expir'
        PPolicyServerTaskBase.__init__(self, interval, *keywords)


    def setParams(self, *args, **keywords):
        PPolicyServerTaskBase.setParams(self, *keywords)
        self.table = keywords.get('table', self.table)
        self.column = keywords.get('column', self.column)


    def doStart(self, *args, **keywords):
        self.factory = keywords.get('factory', self.factory)
        if self.factory != None:
            self.getDbConnection = self.factory.getDbConnection


    def doTask(self):
        log.msg("[DBG] running task: %s" % self.getId())
        #tools.dbMemCacheCleanup()
        try:
            conn = self.getDbConnection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM %s WHERE %s < FROM_UNIXTIME(%i)" %
                         (self.table, self.column, time.time()))
            cursor.close()
        except Exception, err:
            log.msg("[ERR] %s: cleaning cache %s failed: %s" %
                    (self.getId(), self.table, str(err)))



class DatabaseSyncTask(PPolicyServerTaskBase):
    """Synchronize data in two or more databases."""

    def __init__(self, interval = 60, *args, **keywords):
        PPolicyServerTaskBase.__init__(self, interval, *keywords)


    def setParams(self, *args, **keywords):
        PPolicyServerTaskBase.setParams(self, *keywords)
        self.masters = keywords.get('masters', self.masters)
        self.slaves = keywords.get('slaves', self.slaves)
        # dbX (host, port, db, user, port)
        # (table, columns)
        # direction (master-slave, multimaster)


    def doTask(self):
        log.msg("[DBG] running task: %s" % self.getId())
        # FIXME: implement



if __name__ == "__main__":
    print "Module tests:"
    import sys, traceback
    log.startLogging(sys.stdout)
    for taskClass in [ PPolicyServerTaskBase, DummyTask ]:
        task = taskClass()
        print task.getId()
        try:
            task.doTask()
        except Exception, err:
            print "ERROR: %s" % str(err)
            print traceback.print_exc()
