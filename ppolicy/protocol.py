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
        self.numProtocols = 0 # FIXME: numProtocols x numPorts ?
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
        if self.dbConnPool != None and self.dbConnPool.running == 1:
            self.dbConnPool.close()


    def startFactory(self):
        """This will be called before I begin listening on a Port or Connector.
	
	It will only be called once, even if the factory is connected
	to multiple ports.
	
	This can be used to perform 'unserialization' tasks that
	are best put off until things are actually running, such
	as connecting to a database, opening files, etcetera.
	"""


    def stopFactory(self):
        """This will be called before I stop listening on all Ports/Connectors.
	
	This can be used to perform 'shutdown' tasks such as disconnecting
	database connections, closing files, etc.
	
	It will be called, for example, before an application shuts down,
	if it was connected to a port.
	"""


    def buildProtocol(self, addr):
        """Create an instance of a subclass of Protocol.
	
	The returned instance will handle input on an incoming server
	connection, and an attribute \"factory\" pointing to the creating
	factory.
	
	Override this method to alter how Protocol instances get created.
	
	@param addr: an object implementing L{twisted.internet.interfaces.IAddress}
	"""
	return self.protocol(self, self.checks)



class PPolicyServerRequest(protocol.Protocol):

    CONN_LIMIT = 100
    DEFAULT_ACTION_CODE = "dunno"
    DEFAULT_ACTION_NR = None
    DEFAULT_ACTION_RESPONSE = None


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
            self.dataResponse(self.DEFAULT_ACTION_CODE, self.DEFAULT_ACTION_NR,
                              self.DEFAULT_ACTION_RESPONSE)
            #self.transport.write("Too many connections, try later") 
            self.transport.loseConnection()


    def connectionLost(self, reason):
        log.msg("[DBG] connection %s lost: %s" %
                (self.factory.numProtocols, reason))
        self.factory.numProtocols = self.factory.numProtocols-1


    def dataReceived(self, data):
        """Receive Data, Parse it, go through the checks"""
        try:
            if self.__parseData(data):
                self.__doChecks()
        except Exception, err:
            import traceback
            log.msg("[ERR] uncatched exception: %s" % str(err))
            log.msg("[ERR] %s" % traceback.format_exc())
            # FIXME: default return action on garbage?


    def dataResponse(self, code=None, nr=None, response=None):
        """Check response"""
        if not code or code == 'dunno':
            log.msg("[DBG] action=dunno")
	    self.transport.write("action=dunno\n\n")
	else:
            log.msg("[DBG] action=%s %s %s" % (code, nr, response))
	    self.transport.write("action=%s %s %s\n\n" % (code, nr, response))


    def __doChecks(self):
        """Loop over all checks"""
        code = self.DEFAULT_ACTION_CODE
        nr = self.DEFAULT_ACTION_NR
        response = self.DEFAULT_ACTION_RESPONSE
        #self.request_state.get_state(self.instance)
        #if not self.request_state.state:
        #    self.request_state.set_state(self.instance, 'started')
        for check in self.checks:
            try:
                code, nr, response = check.doCheckInt(self.data)
            except Exception, err:
                import traceback
                log.msg("[ERR] processing data for %s: %s" %
                        (check.getId(), str(err)))
                log.msg("[ERR] %s" % traceback.format_exc())
                code = self.DEFAULT_ACTION_CODE
                nr = self.DEFAULT_ACTION_NR
                response = self.DEFAULT_ACTION_RESPONSE
            if code != 'dunno' and code >= 400:
                self.dataResponse(code, nr, response)
                #self.request_state.set_state(self.instance, 'ended')
                #self.transport.loseConnection()
                return
            #self.request_state.set_passed(self.instance, check.getId())
            #self.request_state.checks = []
        self.dataResponse(code, nr, response)
        #if self.request_state.state == 'ended':
        #    self.transport.loseConnection()


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

