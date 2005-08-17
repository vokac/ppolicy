#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Twisted protocol factory and request
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
from twisted.internet import protocol, interfaces, task
from twisted.python import log
from twisted.enterprise import adbapi
from ppolicy import checks
from ppolicy import tasks
import string



class PPolicyServerFactory:

    """This is a factory which produces protocols."""

    __implements__ = (interfaces.IProtocolFactory,)


    def __init__(self, protocol = None):
        self.protocol = protocol
        self.checks = []
        self.tasks = []
        self.numPorts = 0
        self.numProtocols = 0
        self.databaseAPI = None
        self.database = None
        self.dbConnPool = None
        #self.checkStateTask = task.LoopingCall(self__checkChecksState)


    def addCheck(self, check):
        """Add check to factory."""
	log.msg("[INF] Adding check %s" % check.getId())
	self.checks.append(check)


    def addTask(self, taskInst):
        """Add check to task."""
        log.msg("[INF] Adding task %s" % taskInst.getId())
        twistedTask = task.LoopingCall(taskInst.doTask)
        twistedTask.taskInst = taskInst
        twistedTask.name = taskInst.getId()
        twistedTask.interval = taskInst.getInterval()
	self.tasks.append(twistedTask)


    def getDbConnection(self):
        if self.databaseAPI == None:
           raise Exception("undefined databaseAPI")

        if self.dbConnPool == None:
            self.dbConnPool = adbapi.ConnectionPool(self.databaseAPI,
                                                    self.database)
            #self.dbConnPool.min = 3
            #self.dbConnPool.max = 5
            self.dbConnPool.noisy = 1
            self.dbConnPool.start()

        return self.dbConnPool.connect()


    def __activateTasks(self):
        """Activate factory tasks."""
        for task in self.tasks:
	    log.msg("[INF] Activate Task %s(%s)" % (task.name, task.interval))
            task.taskInst.doStart(self)
	    task.start(task.interval)


    def __deactivateTasks(self):
        """Deactivate factory tasks."""
        for task in self.tasks:
	    log.msg("[INF] Deactivate Task %s" % task.name)
            if task.running:
                task.stop()
            task.taskInst.doStop()


    def __activateChecks(self):
        """Activate factory checks."""
        for check in self.checks:
	    log.msg("[INF] Activate Check %s" % check.getId())
	    check.doStartInt(self)


    def __deactivateChecks(self):
        """Deactivate factory checks."""
        for check in self.checks:
	    log.msg("[INF] Deactivate Check %s" % check.getId())
	    check.doStopInt()


    #def __checkChecksState(self):
    #    """Check state of check modules and reload them if undefined."""
    #    for check in self.checks:
    #        log.msg("[DBG] Check state for %s" % check.getId())
    #        if check.getState() == '???': # FIXME
    #            pass


    def doStart(self):
	"""Make sure startFactory is called."""
	if not self.numPorts:
            log.msg("[INF] Starting factory %s" % self)
	    self.startFactory()
	self.numPorts = self.numPorts + 1
        self.__activateChecks()
	self.__activateTasks()
        #self.checkStateTask.start(60)


    def doStop(self):
        """Make sure stopFactory is called."""
	assert self.numPorts > 0
	self.numPorts = self.numPorts - 1
	if not self.numPorts:
            log.msg("[INF] Stopping factory %s" % self)
	    self.stopFactory()
        #if self.checkStateTask.running == 1:
        #    self.checkStateTask.stop()
	self.__deactivateTasks()
        self.__deactivateChecks()


    def startFactory(self):
        """Called once."""
        pass


    def stopFactory(self):
        """Called once."""
        if self.dbConnPool != None and self.dbConnPool.running == 1:
            self.dbConnPool.close()


    def buildProtocol(self, addr):
	return self.protocol(self, self.checks)



class PPolicyServerRequest(protocol.Protocol):

    CONN_LIMIT = 100
    DEFAULT_ACTION = 'DUNNO'
    DEFAULT_ACTION_EX = None


    def __init__(self, factory, checks=[]):
        self.data = {}
        self.factory = factory
	self.checks = checks
	self.finished = False


    def connectionMade(self):
        self.factory.numProtocols += 1
        log.msg("[DBG] connection #%s made" % self.factory.numProtocols)
        if self.factory.numProtocols > self.CONN_LIMIT:
            log.msg("[ERR] connection limit (%s) reached, returning dunno" %
                    self.CONN_LIMIT)
            self.dataResponse(self.DEFAULT_ACTION, self.DEFAULT_ACTION_EX)
            #self.transport.write("Too many connections, try later") 
            self.transport.loseConnection()


    def connectionLost(self, reason):
        log.msg("[DBG] connection %s lost: %s" %
                (self.factory.numProtocols, reason))
        self.factory.numProtocols = self.factory.numProtocols-1


    def dataReceived(self, data):
        """Receive Data, Parse it, go through the checks"""
        try:
            self.data = {}
            if self.__parseData(data):
                self.__doChecks()
        except Exception, err:
            import traceback
            log.msg("[ERR] uncatched exception: %s" % str(err))
            log.msg("[ERR] %s" % traceback.format_exc())
            # FIXME: default return action on garbage?


    def dataResponse(self, action=None, actionEx=None):
        """Check response"""
        if action == None:
            log.msg("[DBG] action=dunno")
	    self.transport.write("action=dunno\n\n")
        elif actionEx == None:
            log.msg("[DBG] action=%s" % action)
	    self.transport.write("action=%s\n\n" % action)
	else:
            log.msg("[DBG] action=%s %s" % (action, actionEx))
	    self.transport.write("action=%s %s\n\n" % (action, actionEx))


    def __doChecks(self):
        """Loop over all checks"""
        action = self.DEFAULT_ACTION
        actionEx = self.DEFAULT_ACTION_EX
        defer_if_permit = False
        defer_if_reject = False

        for check in self.checks:
            try:
                action, actionEx = check.doCheckInt(self.data)
            except Exception, err:
                import traceback
                log.msg("[ERR] processing data for %s: %s" %
                        (check.getId(), str(err)))
                log.msg("[ERR] %s" % traceback.format_exc())
                action = self.DEFAULT_ACTION
                actionEx = self.DEFAULT_ACTION_EX
            if action == None:
                log.msg("[WRN] module %s return None for action" %
                        check.getId())
                action = self.DEFAULT_ACTION
                actionEx = self.DEFAULT_ACTION_EX
            if action.upper() in [ 'DUNNO', 'WARN' ]:
                pass
            elif action.upper() == 'DEFER_IF_PERMIT':
                defer_if_permit = True
            elif action.upper() == 'DEFER_IF_REJECT':
                defer_if_reject = True
            else:
                # FIXME: handle DEFER_IF_
                self.dataResponse(action, actionEx)
                return
        # FIXME: handle DEFER_IF_
        self.dataResponse(action, actionEx)


    def __parseData(self, data):
        """Parse incomming data."""
        for line in string.split(data, '\n'):
            line = line.strip()
            if line == '':
                if self.data.has_key("request"):
                    return True
                else:
                    log.msg("[ERR] policy protocol error: request wasn't specified before empty line")
                    return False
            try:
                k, v = line.split('=')
                if k in [ "request", "protocol_state", "protocol_name",
                          "helo_name", "queue_id", "sender", "recipient",
                          "client_address", "client_name",
                          "reverse_client_name", "instance",
                          "sasl_method", "sasl_username", "sasl_sender",
                          "ccert_subject", "ccert_issuer", "ccert_fingerprint",
                          "size" ]:
                    if k == 'sender' or k == 'recipient':
                        if len(v) != 0 and v[0] == '<': v = v[1:]
                        if len(v) != 0 and v[-1] == '<': v = v[:-1]
                    #if k == 'instance' and self.cluster == True:
                    #    self.clusterip = self.transport.getPeer().host
                    #    v = '%s_%s' % (self.clusterip, v)
                    self.data[k] = v
                    log.msg("[DBG] input: %s=%s" % (k, v))
                else:
                    log.msg("[WRN] unknown key %s (%s)" % (k, v))
            except ValueError:
                log.msg("[WRN] garbage in input: %s" % line)
        log.msg("[WRN] input was not ended by empty line")
        return False



if __name__ == "__main__":
    print "Module tests:"
    import sys, time
    log.startLogging(sys.stdout)
    factory = PPolicyServerFactory(PPolicyServerRequest,
                                   [ checks.DummyCheck(debug=True) ],
                                   [ tasks.DummyTask(1, debug=True) ])
    factory.doStart()
    time.sleep(5)
    factory.doStop()

