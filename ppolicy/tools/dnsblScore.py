#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Return score from RBL according spamassassin settings
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import sys, os, re
import logging
import threading
import dnscache
import dns.exception


class dnsblScore:
    """This class is used to check IP address against various dnsbl.
    It use configuration file from spamassassin 3.1 and can return
    spam score according many popular blacklist.

    required files:
    20_dnsbl_tests.cf  -- spamassassin config file (blacklist definition)
    50_scores.cf       -- spamassassin config file (rule scores)
    """

    __single = None

    def __init__(self, dnsblFileName = None, scoreFileName = None):
        """Constructor for dnsblScore class
        """
        if dnsblScore.__single:
            raise dnsblScore.__single
        dnsblScore.__single = self

        if dnsblFileName == None:
            if os.path.dirname(__file__) == "":
                dnsblFileName = "20_dnsbl_tests.cf"
            else:
                dnsblFileName = "%s/20_dnsbl_tests.cf" % os.path.dirname(__file__)
        logging.getLogger().debug("create dnsbl: %s" % dnsblFileName)

        if scoreFileName == None:
            if os.path.dirname(__file__) == "":
                scoreFileName = "50_scores.cf"
            else:
                scoreFileName = "%s/50_scores.cf" % os.path.dirname(__file__)
        logging.getLogger().debug("create dnsbl: %s" % scoreFileName)

        self.config = {}

        reHeaderRbl2 = re.compile("^header\s+(\S+)\s+eval:check_rbl(|_txt|_envfrom)\('([^']*)',\s*'([^']*)'\)$")
        reHeaderRbl3 = re.compile("^header\s+(\S+)\s+eval:check_rbl(|_txt|_envfrom)\('([^']*)',\s*'([^']*)',\s*'([^']*)'\)$")

        # FIXME: eval:check_rbl_txt
        reHeaderRblSub = re.compile("^header\s+(\S+)\s+eval:check_rbl_sub\('([^']*)',\s*'([^']*)'\)$")
        reDescribe = re.compile("^describe\s+(\S+)\s+(.*)$")
        reScore1 = re.compile("^score\s+(\S+)\s+(\d+|\d+\.\d+)\s*$")
        reScore4 = re.compile("^score\s+(\S+)\s+(\d+|\d+\.\d+)\s+(\d+|\d+\.\d+)\s+(\d+|\d+\.\d+)\s+(\d+|\d+\.\d+)$")

        # read dnsbl definitions
        dnsblFile = open(dnsblFileName)
        for line in dnsblFile.readlines():
            if line[0] == '#': continue
            if line == "\n": continue
            if line.find('#') != -1: line = line[:line.find('#')]
            line = line.strip()
            res = reHeaderRbl2.match(line)
            if res != None:
                cid = res.group(1)
                if res.group(2) == '_envfrom':
                    self.__addConfig(cid, { 'envfrom': True })
                name = res.group(3)
                dnsbl = res.group(4)[:-1]
                self.__addConfig(cid, { 'type': 'main', 'name': name, 'dnsbl': dnsbl })
            res = reHeaderRbl3.match(line)
            if res != None:
                cid = res.group(1)
                if res.group(2) == '_envfrom':
                    self.__addConfig(cid, { 'envfrom': True })
                name = res.group(3)
                dnsbl = res.group(4)[:-1]
#                val = res.group(5)
                self.__addConfig(cid, { 'type': 'main', 'name': name, 'dnsbl': dnsbl })
            res = reHeaderRblSub.match(line)
            if res != None:
                cid = res.group(1)
                name = res.group(2)
                val = res.group(3)
                self.__addConfig(cid, { 'type': 'sub', 'name': name, 'value': val })
            res = reDescribe.match(line)
            if res != None:
                cid = res.group(1)
                desc = res.group(2)
                self.__addConfig(cid, { 'desc': desc })

        # add blacklist score
        scoreFile = open(scoreFileName)
        for line in scoreFile.readlines():
            if line[0] == '#': continue
            if line == "\n": continue
            if line.find('#') != -1: line = line[:line.find('#')]
            line = line.strip()
            res = reScore1.match(line)
            if res != None:
                cid = res.group(1)
                sc1 = float(res.group(2))
                if self.config.has_key(cid):
                    self.__addConfig(cid, { 'score': (sc1, sc1, sc1, sc1) })
            res = reScore4.match(line)
            if res != None:
                cid = res.group(1)
                sc1 = float(res.group(2))
                sc2 = float(res.group(3))
                sc3 = float(res.group(4))
                sc4 = float(res.group(5))
                if self.config.has_key(cid):
                    self.__addConfig(cid, { 'score': (sc1, sc2, sc3, sc4) })

        # remove items without required fields
        toDel = []
        for k,v in self.config.items():
            if not v.has_key('type'):
                toDel.append(k)
        for k in toDel:
            del(self.config[k])

        # add dns to all items
        self.configMain = {}
        for k,v in self.config.items():
            if v['type'] == 'main':
                logging.getLogger().debug("main module: %s (%s)" % (v['name'], k))
                self.configMain[v['name']] = v
            else:
                logging.getLogger().debug("sub module: %s[%s]" % (k, v['name']))
        # envelope subcheck
        for k,v in self.config.items():
            if v['type'] == 'sub':
                if self.configMain.has_key(v['name']):
                    if self.configMain[v['name']].get('envfrom', False):
                        v['envfrom'] = True


    def __addConfig(self, cid, params = {}):
        if not self.config.has_key(cid):
            self.config[cid] = {}
        self.config[cid].update(params)


    def get_config(self):
        return self.config


    def score(self, ip, sender_domain = None, checkList = []):
        """Return score for defined client ip address and sender domain
        according spamassassin rules.

        Parameters:
        ip -- client ip address
        sender_domain -- sender domain from mail envelope
        checkList -- list of rules that should be used
        """
        score = 0
        result = {}
        ipr = ip.split('.')
        ipr.reverse()
        ipr = '.'.join(ipr)
        for check in checkList:
            logging.getLogger().debug("check: %s" % check)
            if not self.config.has_key(check):
                logging.getLogger().warn("check %s is not defined" % check)
                continue
            if self.config[check]['type'] == 'sub':
                if not self.configMain.has_key(self.config[check]['name']):
                    logging.getLogger().warn("main check for %s is not defined" % check)
                    continue
                else:
                    dnsbl = self.configMain[self.config[check]['name']]['dnsbl']
                    envfrom = self.configMain[self.config[check]['name']].get('envfrom', False)
            else:
                dnsbl = self.config[check]['dnsbl']
                envfrom = self.config[check].get('envfrom', False)
    
            if not result.has_key(dnsbl):
                # test DNS
                check_name = None
                if not envfrom:
                    check_name = "%s.%s" % (ipr, dnsbl)
                elif sender_domain != None:
                    check_name = "%s.%s" % (sender_domain, dnsbl)
                ips = []
                if check_name != None:
                    try:
                        logging.getLogger().debug("resolve: %s" % check_name)
                        answer = []
                        resolver, resolverLock = dnscache.getResolver(3.0, 1.0)
                        resolverLock.acquire()
                        try:
                            answer = resolver.query(check_name, 'A')
                        except Exception, e:
                            resolverLock.release()
                            raise e
                        resolverLock.release()
                        logging.getLogger().debug("result: %s" % [ x for x in answer ])
                        for rdata in answer:
                            ips.append(rdata.address)
                    except dns.exception.Timeout:
                        logging.getLogger().debug("DNS timeout, query: %s" % check_name)
                    except dns.exception.DNSException:
                        # no results or DNS problem
                        pass
                result[dnsbl] = ips
            if len(result[dnsbl]) > 0:
                if self.config[check].has_key('value'):
                    # test if result match
                    for ip in result[dnsbl]:
                        if re.compile(self.config[check]['value']).match(ip):
                            if self.config[check].has_key('score'):
                                addScore = self.config[check]['score'][1]
                                logging.getLogger().debug("%s[%s]: %s" % (check, ip, addScore))
                                score += addScore
                            break
                else:
                    if self.config[check].has_key('score'):
                        addScore = self.config[check]['score'][1]
                        logging.getLogger().debug("%s[%s]: %s" % (check, ip, addScore))
                        score += addScore

        return score
        


def getInstance(x = dnsblScore):
    try:
        inst = x()
    except dnsblScore, i:
        inst = i
    return inst
        #print type(e) == __main__.dnsbl


def score(ip, sender_domain = None, checkList = [ 'RCVD_IN_XBL', 'RCVD_IN_NJABL_DUL', 'RCVD_IN_BL_SPAMCOP_NET', 'DNS_FROM_RFC_WHOIS', 'DNS_FROM_AHBL_RHSBL', 'RCVD_IN_WHOIS_HIJACKED', 'RCVD_IN_SORBS_WEB', 'DNS_FROM_RFC_POST', 'RCVD_IN_NJABL_SPAM', 'RCVD_IN_DSBL', 'DNS_FROM_RFC_DSN', 'RCVD_IN_SORBS_SOCKS', 'RCVD_IN_SBL', 'RCVD_IN_WHOIS_BOGONS', 'DNS_FROM_RFC_BOGUSMX', 'RCVD_IN_WHOIS_INVALID', 'DNS_FROM_RFC_ABUSE', 'RCVD_IN_SORBS_SMTP', 'RCVD_IN_SORBS_DUL', 'RCVD_IN_NJABL_PROXY', 'RCVD_IN_SORBS_ZOMBIE', 'DNS_FROM_SECURITYSAGE' ]):
    """See documentation for dnsblScore.score method."""
    return getInstance().score(ip, sender_domain, checkList)



def listDnsbl():
    config = getInstance().get_config()
    for k,v in config.items():
        if v['type'] == 'main':
            print "%s ++++ %s ++++" % (k, v.get('name'))
        else:
            print "%s ---- %s ----" % (k, v.get('name'))
        print "\tdesc: %s" % v.get('desc')
        print "\tvalue: %s" % v.get('value')
        print "\tscore: %s" % str(v.get('score'))
        if v.get('envfrom', False):
            print "\tenvfrom: %s" % str(v.get('envfrom'))



if __name__ == "__main__":
    streamHandler = logging.StreamHandler(sys.stdout)
    streamHandler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s](%(module)s:%(lineno)d) %(message)s", "%d %b %H:%M:%S"))
    logging.getLogger().addHandler(streamHandler)
    logging.getLogger().setLevel(logging.DEBUG)

    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        listDnsbl()
        sys.exit()

    for ip in [ '71.99.151.7', '62.193.240.107', '84.108.164.149' ]:
        print "%s: %s" % (ip, score(ip, 'pradella.biz'))
