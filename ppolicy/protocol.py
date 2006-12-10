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
import sys, time, string, gc, resource
import logging
import threading
import traceback
from twisted.internet import reactor, protocol, interfaces
from twisted.enterprise import adbapi
from twisted.protocols.basic import LineReceiver


class Redirect:
    def __init__(self):
        self.buf = ''
    def write(self, buf):
        self.buf += buf
    def getBuffer(self):
        buf = self.buf
        self.buf = ''
        return buf

class CommandProtocol(LineReceiver):

    COMMANDS = [ "quit" ]

    def __init__(self):
        self.cmd = ''
        self.stdoutOrig = sys.stdout
        self.stdoutRedir = Redirect()

    def __printPrefix(self, prefix):
        delimiter = self.delimiter
        self.delimiter = ''
        self.sendLine(prefix)
        self.delimiter = delimiter

    def connectionMade(self):
        # self.sendLine("Write python expression or call predefined command.")
        # self.sendLine("Commands: %s\n", ", ".join(CommandProtocol.COMMANDS))
        self.__printPrefix('>>> ')

    def connectionLost(self, reason):
        pass

    def lineReceived(self, line):
        logging.getLogger().debug(line)
        ppolicyFactory = self.factory.factory
        if line.lower() == 'quit':
            self.sendLine('bye')
            self.transport.loseConnection()
            return
        try:
            prefix = '>>> '
            buf = ''
            if self.cmd == '':
                if line != '':
                    sys.stdout = self.stdoutRedir
                    eval(compile(line, '<prompt>', 'single'), globals(), locals())
                    sys.stdout = self.stdoutOrig
                    buf = self.stdoutRedir.getBuffer()
            else:
                if line != '':
                    prefix = '... '
                    self.cmd = "%s\n%s" % (self.cmd, line)
                else:
                    sys.stdout = self.stdoutRedir
                    eval(compile(self.cmd, '<prompt>', 'exec'), globals(), locals())
                    sys.stdout = self.stdoutOrig
                    self.cmd = ''
                    buf = self.stdoutRedir.getBuffer()
            if buf != '':
                if buf[len(buf)-1] == "\n": buf = buf[:-1]
                logging.getLogger().debug(buf)
                for line in buf.split("\n"):
                    self.sendLine(line)
            self.__printPrefix(prefix)
        except EOFError:
            self.sendLine('bye')
            self.transport.loseConnection()
        except SyntaxError, e:
            if self.cmd == '':
                self.__printPrefix('... ')
                self.cmd = line
            else:
                for line in str(e).split("\n"):
                    self.sendLine(line)
                self.__printPrefix('>>> ')
                self.cmd = ''
        except Exception, e:
            self.sendLine(str(e))
            self.__printPrefix('>>> ')
        self.stdoutRedir.getBuffer()
        sys.stdout = self.stdoutOrig


class CommandFactory(protocol.Factory):

    protocol = CommandProtocol

    def __init__(self, factory):
        self.factory = factory

    def startFactory(self):
        pass

    def stopFactory(self):
        pass


class PPolicyFactory:

    """This is a factory which produces protocols."""

    __implements__ = (interfaces.IProtocolFactory,)


    def __init__(self, config = {}):
        self.protocol = PPolicyRequest
        self.cacheLock = threading.Lock()
        self.__initConfig(config)


    def __initConfig(self, config):
        self.numPorts = 0
        self.numProtocols = 0
        self.dbConnPool = None
        self.config = config
        self.modules = {}
        self.__addChecks(self.getConfig('modules'))
        self.cacheSize = self.getConfig('cacheSize', 10000)
        self.cacheValue = {}
        self.cacheExpire = {}        


    def reload(self, config = {}):
        # FIXME: Implement factrory reloading
        self.doStop() # FIXME: stop all "check" before doing "__stopCheck"
        self.__initConfig(config)
        self.doStart()


    def getDbConnection(self):
        if self.config.get('databaseAPI') == None:
           raise Exception("undefined databaseAPI")

        if self.dbConnPool == None:
            self.dbConnPool = adbapi.ConnectionPool(self.config.get('databaseAPI'),
                                                    **self.config.get('database'))
            self.dbConnPool.start()

        return self.dbConnPool.connect()


    def getConfig(self, key, default = None):
        return self.config.get(key, default)


    def __addChecks(self, modules):
        for modName,v in modules.items():
            modType = v[0]
            modParams = v[1]
            if modType == None or modType == '':
                logging.getLogger().error("Type was not defined for module %s" % modName)
                raise Exception("Type was not defined for module %s" % modName)
            if not self.modules.has_key(modName):
                logging.getLogger().info("Adding module %s[%s(%s)]" % (modType, modName, modParams))
            else:
                logging.getLogger().warn("Redeclaration of module %s[%s(%s)]" % (modType, modName, modParams))
            globals()[modType] = eval("__import__('%s', globals(),  locals(), [])" % modType)
            obj = eval("%s.%s('%s', self, **%s)" % (modType, modType, modName, modParams))
            self.modules[modName] = [ obj, False ]


    def __startChecks(self):
        """Start factory modules."""
        for modName, modVal in self.modules.items():
	    logging.getLogger().info("Start module %s" % modVal[0].getId())
            try:
                modVal[0].start()
                modVal[1] = True
            except Exception, e:
                logging.getLogger().error("Start module %s failed: %s" % (modVal[0].getId(), e))


    def __stopChecks(self):
        """Stop factory modules."""
        for modName, modVal in self.modules.items():
	    logging.getLogger().info("Stop module %s" % modVal[0].getId())
            try:
                modVal[0].stop()
                modVal[1] = False
            except Exception, e:
                logging.getLogger().error("Stop module %s failed: %s" % (modVal[0].getId(), e))


    def check(self, name, data, *args, **keywords):
        """Called from config file. We should cache results here."""
        startTime = time.time()
        allStartTime = data.get('resource_start_time', startTime)
        reqid = data.get('instance', "unknown%i" % allStartTime)

        if not self.modules.has_key(name):
            raise Exception("module named \"%s\" was not defined" % name)

        prefix = "result_%s" % name
        saveResult = False
        try:
            obj, running = self.modules.get(name)

            saveResult = obj.getParam('saveResult', False)
            if saveResult:
                prefix = "%s%s" % (obj.getParam('saveResultPrefix', ''), name)
                if data.has_key("%s_code" % prefix):
                    reqnum = 1
                    while data.has_key("%s#%i_code" % (prefix, reqnum)):
                        reqnum += 1
                    prefix = "%s#%i" % (prefix, reqnum)

            if not running:
                obj.start()
            
            logging.getLogger().info("%s running %s[%i]" % (reqid, name, int((startTime - allStartTime) * 1000)))
            hashArg = obj.hashArg(data, *args, **keywords)
            if hashArg != 0:
                hashArg = "%s%s" % (name, hashArg)

            code, codeEx = self.__cacheGet(hashArg)
            if code == None:
                hitCache = ''
                #logging.getLogger().debug("%s: running %s.check(%s, %s, %s)" % (reqid, name, data, args, keywords))
                code, codeEx = obj.check(data, *args, **keywords)
                self.__cacheSet(hashArg, code, codeEx, obj.getParam('cachePositive'), obj.getParam('cacheUnknown'), obj.getParam('cacheNegative'))
            else:
                hitCache = ' cached'

            endTime = time.time()
            if obj.getParam('saveResult', False):
                data["%s_code" % prefix] = code
                data["%s_info" % prefix] = codeEx
                data["%s_cache" % prefix] = not (hitCache == '')
                data["%s_time" % prefix] = int((endTime - startTime) * 1000)
                if logging.getLogger().getEffectiveLevel() < logging.DEBUG:
                    rusage = resource.getrusage(resource.RUSAGE_SELF)
                    rusageStr = "[ %.3f, %.3f, %s ]" % (rusage[0], rusage[1], str(rusage[2:])[1:-1])
                    data["%s_resource" % prefix] = "cache(%i), gc(%s, %s), rs%s" % (len(self.cacheValue), len(gc.get_objects()), len(gc.garbage), rusageStr)
            logging.getLogger().info("%s result%s %s[%i,%i]: %s (%s)" % (reqid, hitCache, name, int((endTime - allStartTime) * 1000), int((endTime - startTime) * 1000), code, codeEx))

            return code, codeEx
        except Exception, e:
            code = 0
            codeEx = "%s failed with exception" % name
            endTime = time.time()
            try:
                if saveResult:
                    data["%s_code" % prefix] = code
                    data["%s_info" % prefix] = codeEx
                    data["%s_time" % prefix] = int((endTime - startTime) * 1000)
            except:
                pass

            logging.getLogger().error("%s failed %s[%i,%i]: %s" % (reqid, name, int((endTime - allStartTime) * 1000), int((endTime - startTime) * 1000), e))
            exc_info_type, exc_info_value, exc_info_traceback = sys.exc_info()
            logging.getLogger().error("%s: %s" % (reqid, traceback.format_exception(exc_info_type, exc_info_value, exc_info_traceback)))
            # raise e
            return code, codeEx


    def __cacheGet(self, key):
        if key == 0: return None, None
        retVal = None, None
        self.cacheLock.acquire()
        #logging.getLogger().debug("__cacheGet for %s" % key)
        try:
            if self.cacheExpire.has_key(key) and self.cacheExpire[key] >= time.time():
                retVal = self.cacheValue[key]
        except Exception, e:
            self.cacheLock.release()
            raise e
        self.cacheLock.release()
        return retVal


    def __cacheSet(self, key, code, codeEx, cachePositive, cacheUnknown, cacheNegative):
        if key == 0: return

        cacheTime = 0
        if code > 0: cacheTime = cachePositive
        elif code < 0: cacheTime = cacheNegative
        else: cacheTime = cacheUnknown

        if cacheTime <= 0: return

        self.cacheLock.acquire()
        #logging.getLogger().debug("__cacheSet for %s (%s, %s)" % (key, code, codeEx))
        try:
            # full cache 3/4 cleanup?
            if len(self.cacheExpire) > self.cacheSize:
                logging.getLogger().debug("memory cache cleanup")
                exp = self.cacheExpire.values()
                exp.sort()
                expTr = exp[3*len(exp)/4]
                if expTr < time.time():
                    expTr = time.time()
                toDelArr = [ name for name, exp in self.cacheExpire.items() if exp < expTr ]
                for toDel in toDelArr:
                    del(self.cacheValue[toDel])
                    del(self.cacheExpire[toDel])
            self.cacheValue[key] = (code, codeEx)
            self.cacheExpire[key] = time.time() + cacheTime
        except Exception, e:
            self.cacheLock.release()
            raise e
        self.cacheLock.release()


    def doStart(self):
	"""Make sure startFactory is called."""
	if not self.numPorts:
            logging.getLogger().info("Starting factory %s" % self)
	    self.startFactory()
	self.numPorts = self.numPorts + 1
        self.__startChecks()


    def doStop(self):
        """Make sure stopFactory is called."""
	assert self.numPorts > 0
	self.numPorts = self.numPorts - 1
        self.__stopChecks()
	if not self.numPorts:
            logging.getLogger().info("Stopping factory %s" % self)
	    self.stopFactory()
        if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
            gc.collect()
            logging.getLogger().debug("gc: %s" % len(gc.get_objects()))
            logging.getLogger().debug("gc: %s" % gc.get_objects())


    def startFactory(self):
        """Called once."""
        pass


    def stopFactory(self):
        """Called once."""
        if self.dbConnPool != None and self.dbConnPool.running == 1:
            self.dbConnPool.close()


    def buildProtocol(self, addr):
	return self.protocol(self)



class PPolicyRequest(protocol.Protocol):

    CONN_LIMIT = 100


    def __init__(self, factory):
        self.factory = factory
        self.check = factory.getConfig('check')
        self.returnOnFatalError = factory.getConfig('returnOnFatalError', ('dunno', None))
        self.returnOnConnLimit = factory.getConfig('returnOnConnLimit', ('dunno', None))
	self.finished = False


    def connectionMade(self):
        self.factory.numProtocols += 1
        logging.getLogger().debug("connection #%s made" % self.factory.numProtocols)
        if self.factory.numProtocols > self.CONN_LIMIT:
            logging.getLogger().error("connection limit (%s) reached, returning dunno" % self.CONN_LIMIT)
            dataResponse(self.transport, self.returnOnConnLimit[0], self.returnOnConnLimit[1])
            #self.transport.writeSomeData("Too many connections, try later") 
            self.transport.loseConnection()


    def connectionLost(self, reason):
        logging.getLogger().debug("connection %s lost: %s" % (self.factory.numProtocols, reason))
        self.factory.numProtocols = self.factory.numProtocols-1


    def dataReceived(self, data):
        """Receive data and process them in new thread"""
        # XXXXX: callInThread doesn't release resources?!
        #        or it is resouce leak when creating/releasing connection?
        #reactor.callInThread(self.dataProcess, data)
        # replaced with following Thread class - it is not so effective,
        # because it doesn't use thread pool, but it doesn't leak resources
        PPolicyRequestThread(self.factory, data, self.transport).start()



class PPolicyRequestThread(threading.Thread):

    def __init__ (self, factory, data, transport):
        threading.Thread.__init__(self)
        self.factory = factory
        self.check = factory.getConfig('check')
        self.returnOnFatalError = factory.getConfig('returnOnFatalError', ('dunno', None))
        self.returnOnConnLimit = factory.getConfig('returnOnConnLimit', ('dunno', None))
        self.data = data
        self.transport = transport


    #def dataProcess(self, data): # XXXXX: old usage in PPolicyRequest
    def run(self):
        """Parse data, call check method from config file and return results."""
        startTime = time.time()
        reqid = "unknown%i" % startTime
        try:
            #parsedData = self.__parseData(data) # XXXXX: old usage in PPolicyRequest
            parsedData = self.__parseData(self.data)
            if parsedData != None:
                if not parsedData.has_key('resource_start_time'):
                    parsedData['resource_start_time'] = startTime
                reqid = parsedData.get('instance', "unknown%i" % startTime)
                logging.getLogger().info("%s start[%i]" % (reqid, startTime))
                if logging.getLogger().getEffectiveLevel() < logging.DEBUG:
                    rusage = list(resource.getrusage(resource.RUSAGE_SELF))
                    rusageStr = "[ %.3f, %.3f, %s ]" % (rusage[0], rusage[1], str(rusage[2:])[1:-1])
                    logging.getLogger().debug("%s gc(%s, %s), rs%s" % (reqid, len(gc.get_objects()), len(gc.garbage), rusageStr))

                iaddress = self.transport.getPeer()
                action, actionEx = self.check(self.factory, parsedData, iaddress.port)

                runTime = int((time.time() - startTime) * 1000)
                logging.getLogger().info("%s finish[%i]: %s (%s)" % (reqid, runTime, action, actionEx))
                if logging.getLogger().getEffectiveLevel() < logging.DEBUG:
                    rusage = list(resource.getrusage(resource.RUSAGE_SELF))
                    rusageStr = "[ %.3f, %.3f, %s ]" % (rusage[0], rusage[1], str(rusage[2:])[1:-1])
                    logging.getLogger().debug("%s gc(%s, %s), rs%s" % (reqid, len(gc.get_objects()), len(gc.garbage), rusageStr))

                dataResponse(self.transport, action, actionEx)
            else:
                # default return action for garbage?
                dataResponse(self.transport)
        except Exception, err:
            logging.getLogger().error("%s uncatched exception: %s" % (reqid, str(err)))
            exc_info_type, exc_info_value, exc_info_traceback = sys.exc_info()
            logging.getLogger().error("%s" % traceback.format_exception(exc_info_type, exc_info_value, exc_info_traceback))
            dataResponse(self.transport, self.returnOnFatalError[0], self.returnOnFatalError[1])


    def __parseData(self, data):
        """Parse incomming data."""
        retData = {}
        for line in string.split(data, '\n'):
            line = line.strip()
            if line == '':
                if retData.has_key("request"):
                    return retData
                else:
                    logging.getLogger().error("policy protocol error: request wasn't specified before empty line")
                    return None
            try:
                k, v = line.split('=', 1)
                #if k == 'instance' and self.cluster == True:
                #    self.clusterip = self.transport.getPeer().host
                #    v = '%s_%s' % (self.clusterip, v)
                if k == 'client_name' and v == 'unknown':
                    v = ''
                retData[k] = v
                logging.getLogger().debug("input: %s=%s" % (k, v))
            except ValueError:
                logging.getLogger().warn("garbage in input: %s" % line)
        logging.getLogger().warn("input was not ended by empty line")
        if retData.has_key("request"):
            return retData
        else:
            return None


def dataResponse(transport, action=None, actionEx=None):
    """Check response"""
    if action == None:
        logging.getLogger().debug("output: action=dunno")
        transport.writeSomeData("action=dunno\n\n")
    elif actionEx == None:
        logging.getLogger().debug("output: action=%s" % action)
        transport.writeSomeData("action=%s\n\n" % action)
    else:
        logging.getLogger().debug("output: action=%s %s" % (action, actionEx))
        transport.writeSomeData("action=%s %s\n\n" % (action, actionEx))



if __name__ == "__main__":
    print "Module tests:"
    import socket
    import twisted.python.log
    twisted.python.log.startLogging(sys.stdout)

    # default config
    config = {
        'configFile'   : '../ppolicy.conf',
        'logLevel'     : logging.DEBUG,
        'admin'        : 'postmaster',
        'domain'       : socket.gethostname(),
        'databaseAPI'  : 'MySQLdb',
        'database'     : { 'host'   : 'localhost',
                           'port'   : 3306,
                           'db'     : 'ppolicy',
                           'user'   : 'ppolicy',
                           'passwd' : 'secret',
                           },
        'listenPort'   : 10030,
        'returnOnConnLimit': ('450', 'reached connection limit to ppolicy, retry later'),
        'returnOnFatalError': ('450', 'fatal error when checking SMTP data, retry later'),
        'check'        : lambda x: ('dunno', ''),
        'modules'      : {},
        }

    print ">>> Create Factory"
    factory = PPolicyFactory(config)

    print ">>> Test Db Connection"
    factory.getDbConnection().cursor().execute("SHOW DATABASES")

    print ">>> Start Factory"
    factory.doStart()
    time.sleep(5)
    print ">>> Stop Factory"
    factory.doStop()

