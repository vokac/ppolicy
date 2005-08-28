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
import string
import logging
import checks
import tasks
from twisted.internet import protocol, interfaces, task
from twisted.enterprise import adbapi



class PPolicyServerFactory:

    """This is a factory which produces protocols."""

    __implements__ = (interfaces.IProtocolFactory,)


    def __init__(self, protocol = None, config = {}):
        self.protocol = protocol
        self.checks = []
        self.tasks = []
        self.numPorts = 0
        self.numProtocols = 0
        self.dbConnPool = None
        self.config = config
        self.databaseAPI = self.config.get('databaseAPI')
        self.database = self.config.get('database')
        for chk in self.config.get('checks'):
            self.addCheck(chk)
        for tsk in self.config.get('tasks'):
            self.addTask(tsk)


    def addCheck(self, check):
        """Add check to factory."""
	logging.log(logging.INFO, "Adding check %s" % check.getId())
	self.checks.append(check)


    def addTask(self, taskInst):
        """Add check to task."""
        logging.log(logging.INFO, "Adding task %s" % taskInst.getId())
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
                                                    **self.database)
            #self.dbConnPool.min = 3
            #self.dbConnPool.max = 5
            self.dbConnPool.noisy = 1
            self.dbConnPool.start()

        return self.dbConnPool.connect()


    def __activateTasks(self):
        """Activate factory tasks."""
        for task in self.tasks:
	    logging.log(logging.INFO, "Activate Task %s(%s)" %
                        (task.name, task.interval))
            task.taskInst.doStart(self)
	    task.start(task.interval)


    def __deactivateTasks(self):
        """Deactivate factory tasks."""
        for task in self.tasks:
	    logging.log(logging.INFO, "Deactivate Task %s" % task.name)
            if task.running:
                task.stop()
            task.taskInst.doStop()


    def __activateChecks(self):
        """Activate factory checks."""
        for check in self.checks:
	    logging.log(logging.INFO, "Activate Check %s" % check.getId())
	    check.doStartInt(self, factory=self)


    def __deactivateChecks(self):
        """Deactivate factory checks."""
        for check in self.checks:
	    logging.log(logging.INFO, "Deactivate Check %s" % check.getId())
	    check.doStopInt()


    def doStart(self):
	"""Make sure startFactory is called."""
	if not self.numPorts:
            logging.log(logging.INFO, "Starting factory %s" % self)
	    self.startFactory()
	self.numPorts = self.numPorts + 1
        self.__activateChecks()
	self.__activateTasks()


    def doStop(self):
        """Make sure stopFactory is called."""
	assert self.numPorts > 0
	self.numPorts = self.numPorts - 1
	if not self.numPorts:
            logging.log(logging.INFO, "Stopping factory %s" % self)
	    self.stopFactory()
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
        logging.log(logging.DEBUG, "connection #%s made" %
                    self.factory.numProtocols)
        if self.factory.numProtocols > self.CONN_LIMIT:
            logging.log(logging.ERROR, "connection limit (%s) reached, returning dunno" % self.CONN_LIMIT)
            self.dataResponse(self.DEFAULT_ACTION, self.DEFAULT_ACTION_EX)
            #self.transport.write("Too many connections, try later") 
            self.transport.loseConnection()


    def connectionLost(self, reason):
        logging.log(logging.DEBUG, "connection %s lost: %s" %
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
            logging.log(logging.ERROR, "uncatched exception: %s" % str(err))
            logging.log(logging.ERROR, "%s" % traceback.format_exc())
            # FIXME: default return action on garbage?


    def dataResponse(self, action=None, actionEx=None):
        """Check response"""
        if action == None:
            logging.log(logging.DEBUG, "action=dunno")
	    self.transport.write("action=dunno\n\n")
        elif actionEx == None:
            logging.log(logging.DEBUG, "action=%s" % action)
	    self.transport.write("action=%s\n\n" % action)
	else:
            logging.log(logging.DEBUG, "action=%s %s" % (action, actionEx))
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
                logging.log(logging.ERROR, "processing data for %s: %s" %
                            (check.getId(), str(err)))
                logging.log(logging.ERROR, "%s" % traceback.format_exc())
                action = self.DEFAULT_ACTION
                actionEx = self.DEFAULT_ACTION_EX
            if action == None:
                logging.log(logging.WARN, "module %s return None for action" %
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
                    logging.log(logging.ERROR, "policy protocol error: request wasn't specified before empty line")
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
                    logging.log(logging.DEBUG, "input: %s=%s" % (k, v))
                else:
                    logging.log(logging.WARN, "unknown key %s (%s)" % (k, v))
            except ValueError:
                logging.log(logging.WARN, "garbage in input: %s" % line)
        logging.log(logging.WARN, "input was not ended by empty line")
        return False



if __name__ == "__main__":
    print "Module tests:"
    import sys, time
    import twisted.python.log
    twisted.python.log.startLogging(sys.stdout)

    # default config
    config = {
        'logLevel'     : logging.DEBUG,
        'configFile'   : '/home/vokac/workspace/ppolicy/ppolicy.conf',
        'databaseAPI'  : 'MySQLdb',
        'database'     : { 'host'   : 'localhost',
                           'port'   : 3306,
                           'db'     : 'ppolicy',
                           'user'   : 'ppolicy',
                           'passwd' : 'ppolicy',
                           },
        'listenPort'   : 1030,
        'checks'       : ( checks.DummyCheck(debug=True), ),
        'tasks'        : ( tasks.DummyTask(1, debug=True), ),
        }

    print ">>> Create Factory"
    factory	= PPolicyServerFactory(PPolicyServerRequest)
    for chk in config['checks']:
        factory.addCheck(chk)
    for tsk in config['tasks']:
        factory.addTask(tsk)
    factory.databaseAPI = config['databaseAPI']
    factory.database = config['database']

    print ">>> Test Db Connection"
    factory.getDbConnection().cursor().execute("SHOW DATABASES")

    print ">>> Start Factory"
    factory.doStart()
    time.sleep(5)
    print ">>> Stop Factory"
    factory.doStop()

