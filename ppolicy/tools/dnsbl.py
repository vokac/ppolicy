#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Check if hostname exist in some RBL
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import sys, os.path
import logging
import dnscache
import dns.exception


class dnsbl:
    """This class is used to check IP address against various dnsbl.
    It use configuration file from http://moensted.dk/spam to specify
    many blacklists thats name can be used in check method."""

    __single = None

    def __init__(self, configFileName = None):
        """Constructor for dnsbl class
        
        Parameter
        configFileName -- config file from http://moensted.dk/spam/drbsites.txt
        """
        if dnsbl.__single:
            raise dnsbl.__single
        dnsbl.__single = self

        if configFileName == None:
            if os.path.dirname(__file__) == "":
                configFileName = "dnsbl.dat"
            else:
                configFileName = "%s/dnsbl.dat" % os.path.dirname(__file__)
        logging.getLogger().debug("create dnsbl: %s" % configFileName)

        self.config = {}
        configFile = open(configFileName)
        for line in configFile.readlines():
            if line[0] != "'": continue
            xxx = line[line.find("'")+1:line.rfind("'")]
            while len(xxx.split(";")) < 13:
                xxx += ";"
            rblcode, rbls, rblw, rbln, rblp, rblabout, rblstatus, rblremoval, longname, check, txt, rbltype, rbldns = xxx.split(";")
            self.config[rblcode] = ( rbls, rblw, rbln, rblp, rblabout, rblstatus, rblremoval, longname, check, txt, rbltype, rbldns )
        configFile.close()

        self.resolver, self.resolverLock = dnscache.getResolver(3.0, 1.0)


    def has_config(self, name):
        return self.config.has_key(name)


    def get_config(self):
        return self.config


    def check(self, name, ip, ipList = []):
        if not self.config.has_key(name):
            logging.getLogger().warn("there is not %s dnsbl list in config file" % name)
            return False

        rbls, rblw, rbln, rblp, rblabout, rblstatus, rblremoval, longname, check, txt, rbltype, rbldns = self.config[name]

        ipr = ip.split(".")
        ipr.reverse()
        ipr = ".".join(ipr) + "." + rbls

        logging.getLogger().debug("%s" % ipr)

        listed = False
        try:
            answer = []
            self.resolverLock.acquire()
            try:
                answer = self.resolver.query(ipr, 'A')
            except Exception, e:
                self.resolverLock.release()
                raise e
            self.resolverLock.release()
            logging.getLogger().debug("result: %s" % [ x for x in answer ])
            for rdata in answer:
                if ipList == []:
                    listed = True
                    break
                elif rdata.address in ipList:
                    listed = True
                    break
        except dns.exception.Timeout:
            logging.getLogger().debug("DNS timeout, query: %s" % ipr)
        except dns.exception.DNSException:
            # no results or DNS problem
            pass

        return listed


def getInstance(x = dnsbl):
    try:
        inst = x()
    except dnsbl, i:
        inst = i
    return inst
        #print type(e) == __main__.dnsbl


def has_config(name):
    return getInstance().has_config(name)


def listDnsbl():
    config = getInstance().get_config()
    for name, value in config.items():
        rbls, rblw, rbln, rblp, rblabout, rblstatus, rblremoval, longname, check, txt, rbltype, rbldns = value
        print "%s (%s)" % (name, longname)
        print "\tDNS: %s" % rbls
        print "\tHome: %s" % rblp
        print "\tLookup: %s" % rblw
        print "\tSubmit: %s" % rbln
        print "\tRemove: %s" % rblremoval
        print "\tStatus: %s" % rblstatus
        print "\tInfo: %s" % rblabout
        print "\tcheck: %s" % check
        print "\ttxt: %s" % txt
        print "\trbltype: %s" % rbltype
        print "\trbldns: %s" % rbldns
        print


def check(name, ip, ipList = []):
    return getInstance().check(name, ip, ipList)



if __name__ == "__main__":
    streamHandler = logging.StreamHandler(sys.stdout)
    streamHandler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s](%(module)s:%(lineno)d) %(message)s", "%d %b %H:%M:%S"))
    logging.getLogger().addHandler(streamHandler)
    logging.getLogger().setLevel(logging.DEBUG)

    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        listDnsbl()
        sys.exit()

    for name, ip in [ ('ORDB', '147.32.8.5'), ('SBL', '147.32.8.5'),
                      ('SBL', '147.32.8.9'),
                      ('SBL', '62.193.240.107'), ('SBL', '71.99.151.7') ]:
        print "%s[%s]: %s" % (name, ip, check(name, ip))
