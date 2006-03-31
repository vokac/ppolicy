#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Check module tests
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import sys, re
import logging
import twisted.python.log

class FakeFactory:
    def __init__(self):
        self.config = {}

    def getDbConnection(self):
        import MySQLdb

        conn = None
        try:
            conn = MySQLdb.connect(host = "localhost",
                                   db = "ppolicy",
                                   user = "ppolicy",
                                   passwd = "secret")
        except MySQLdb.Error, e:
            print "Error %d: %s" % (e.args[0], e.args[1])

        return conn


def run(name, param = None, count = 1, **keywords):
    print "Testing module: %s(%s)" % (name, str(keywords))
    print ">> import"
    globals()[name] = eval("__import__('%s', globals(),  locals(), [])" % name)
    if param == None:
        obj = eval("%s.%s('%s', FakeFactory(), **keywords)" % (name, name, name))
    else:
        obj = eval("%s.%s('%s', FakeFactory(), %s)" % (name, name, name, param))
    print ">> start"
    obj.start()
    print ">> check"
    for i in range(0, count):
        print obj.check(data)
    print ">> stop"
    obj.stop()


def doc(name, **keywords):
    print "Module %s" % name
    print "-------%s" % ('-' * len(name))
    print
    globals()[name] = eval("__import__('%s', globals(),  locals(), [])" % name)
    obj = eval("%s.%s('%s', FakeFactory(), **keywords)" % (name, name, name))
    paramsPrinted = False
    skipLines = False
    for line in obj.__doc__.split("\n"):
        if line[:4] == '    ': line = line[4:]
        if line[:len('Module arguments')] == 'Module arguments':
            paramsPrinted = True
            skipLines = True
            print "Parameters:"
            for k,v in obj.getParams().items():
                print "    %s (%s)\n        %s" % (k, v[1], v[0])
            print
        else:
            if skipLines:
                if re.match("^\s*$", line) != None:
                    skipLines = False
            else:
                print line
    if not paramsPrinted:
        print "Module arguments:"
        for k,v in obj.getParams().items():
            print "    %s (%s)\n        %s" % (k, v[1], v[0])
    print
    print
    print



if __name__ == "__main__":
    streamHandler = logging.StreamHandler(sys.stdout)
    streamHandler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s](%(module)s:%(lineno)d) %(message)s", "%d %b %H:%M:%S"))
    logging.getLogger().addHandler(streamHandler)
    logging.getLogger().setLevel(logging.DEBUG)

    data = { 'request': 'smtpd_access_policy',
             'protocol_state': 'RCPT',
             'protocol_name': 'SMTP',
             'helo_name': 'mailgw1.fjfi.cvut.cz',
             'queue_id': '8045F2AB23',
             'sender': 'vokac@kmlinux.fjfi.cvut.cz',
             'recipient': 'vokac@linux.fjfi.cvut.cz',
             'client_address': '147.32.9.3',
             'client_name': 'mailgw1.fjfi.cvut.cz',
             'reverse_client_name': 'mailgw1.fjfi.cvut.cz',
             'instance': '123.456.7',
             'sasl_method': 'plain',
             'sasl_username': 'you',
             'sasl_sender': '',
             'ccert_subject': '???',
             'ccert_issuer': '???',
             'ccert_fingerprint': '???',
             'size': '12345' }
    if len(sys.argv) > 1:
        if sys.argv[1] == '--doc':
            for module in [ 'Dnsbl', 'DOS', 'Dummy', 'DumpDataDB', 'DumpDataFile', 'Greylist', 'List', 'ListDyn', 'Resolve', 'SPF', 'Trap', 'Verification' ]:
                doc(module)
            sys.exit()
        moduleName = sys.argv[1]
        moduleParams = {}
        for arg in sys.argv[2:]:
            arg1, arg2 = arg.split("=", 2)
            moduleParams[arg1] = arg2
        run(moduleName, **moduleParams)
        sys.exit()

    run('DumpDataFile', fileName='test.dat')
#    run('DumpDataDB', tableName='dump')
#    run('List', paramName='sender')
#    run('DOS', 'params="sender"')
#    run('DOS', 'params=["sender","client_address"], limitCount=100, limitTime=10')
#    run('ListDyn', "mapping=[('sender',None,None)], softExpire=10, hardExpire=10")
#    run('ListDyn', "mapping=[('sender',None,None)], operation='add', softExpire=10, hardExpire=10")
#    run('ListDyn', "mapping=[('sender',None,None)], operation='add', softExpire=10, hardExpire=10")
#    run('ListDyn', "mapping=[('sender',None,None)], softExpire=10, hardExpire=10")
#    run('ListDyn', "mapping=[('sender',None,None)], operation='remove'")
#    run('ListDyn', "mapping=[('sender',None,None)], softExpire=10, hardExpire=10")
