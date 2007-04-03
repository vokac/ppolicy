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
import sys, os, re, time
import logging
# I don't use adns library because of problems with getting response
# for multiple queries (method __adnsCheck doesn't work as I expect)
#try:
useAdns = False
#    import adns
#    useAdns = True
#    logging.getLogger().info("using adns library")
#except:
import dnscache
import dns.exception
logging.getLogger().info("using dnspython library")


__version__ = "$Revision$"

class dnsbl:

    """This class is used to check IP address against various dnsbl.
    It use configuration file generated from spamassassin 3.1 and also
    from http://moensted.dk/spam database of various dnsbl (you can
    recreate configuration files by running this script - see help).

    required file:
    dnsbl.dat -- this file contains DNSBL configuration and scores
    """

    __single = None

    def __init__(self, dnsblFileName = None, **keywords):
        """Constructor for dnsbl class

        Parameters:
        dnsblFileName -- file with blacklist and score configuration
        keywords -- optional parameters (e.g. for adns configuration)
            adns -- adns object (default: None, created for each query)
            resolver -- string similar to libresolv /etc/resolv.conf
                        (default: use /etc/resolv.conf resp. /etc/resolv-adns.conf)
            ipv6 -- boolean value for IPv6 support (default: False)
            timeout -- query timeout in seconds (default: 7)
        """
        if dnsbl.__single:
            raise dnsbl.__single
        dnsbl.__single = self

        if useAdns:
            self.adns = keywords.get('adns')
            self.resolver = keywords.get('resolver', '')
            if self.resolver == '' and os.access('/etc/resolv.conf', os.R_OK) and not os.path.exists('/etc/resolv-adns.conf'):
                # read default configuration and "remove" search domains
                f = open('/etc/resolv.conf')
                for line in f.readlines():
                    if line[:len('nameserver')] == 'nameserver':
                        self.resolver += line
                f.close()
            self.ipv6 = keywords.get('ipv6', False)
            self.timeout = keywords.get('timeout', 7)

        if dnsblFileName == None:
            if os.path.dirname(__file__) == "":
                dnsblFileName = "dnsbl.dat"
            else:
                dnsblFileName = "%s/dnsbl.dat" % os.path.dirname(__file__)
        logging.getLogger().debug("create dnsbl: %s" % dnsblFileName)

        reIgnoreLine = re.compile("^(\s*#.*|\s*)$")
        reConfigLine = re.compile("^\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*(\S*)\s*$")

        self.config = {}
        dnsblFile = open(dnsblFileName)
        for line in dnsblFile.readlines():
            if reIgnoreLine.match(line): continue
            if line.find('#') != -1: line = line[:line.find('#')]
            line = line.strip()
            res = reConfigLine.match(line)
            if res != None:
                name = res.group(1)
                bl = res.group(2)
                score = float(res.group(3))
                envfrom = res.group(4).lower() == 'true'
                value = res.group(5)
                if self.config.has_key(name):
                    logging.getLogger().warn("overriding configuration for %s" % name)
                self.config[name] = { 'dnsbl': bl, 'score': score,
                                      'envfrom': envfrom, 'value': value }

        self.reIPv4 = re.compile("^([012]?\d{1,2}\.){3}[012]?\d{1,2}$")
        self.reIPv6 = re.compile('^([0-9a-fA-F]{0,4}:){0,7}([0-9a-fA-F]{0,4}|([012]?\d{1,2}\.){3}[012]?\d{1,2})$')


    def get_config(self):
        return self.config


    def has_config(self, name):
        return self.config.has_key(name)


    def score(self, ip = None, domain = None, checkList = []):
        """See dnsbl.check info."""
        return self.check(ip, domain, checkList, True)


    def check(self, ip = None, domain = None, checkList = [], scoreOnly = False):
        """Return blacklist hits and score for defined client ip
        address and sender domain according spamassassin rules.

        Parameters:
        ip -- client ip address
        domain -- sender domain from mail envelope
        checkList -- list of rules that should be used
        scoreOnly -- return only valid score (skip blacklist with score 0)
        """
        logging.getLogger().debug("score(%s, %s, %s)" % (ip, domain, len(checkList)))

        if ip != None:
            # XXX: IPv6
            if self.reIPv4.match(ip) == None:
                logging.getLogger().info("%s doesn't looks like valid IPv4 address" % ip)
                ipr = None
            else:
                ipr = ip.split('.')
                ipr.reverse()
                ipr = '.'.join(ipr)
        else:
            ipr = None

        check_items = []
        check_items_bl = []
        for check in checkList:
            if not self.config.has_key(check):
                logging.getLogger().warn("check %s is not defined" % check)
                continue
            if scoreOnly and self.config[check]['score'] == 0:
                logging.getLogger().warn("score 0 for %s, skipping this check" % check)
                continue
            bl = self.config[check]['dnsbl']
            envfrom = self.config[check]['envfrom']
            score = self.config[check]['score']
            value = self.config[check]['value']

            check_name = None
            if not envfrom:
                if ipr != None:
                    check_name = "%s.%s" % (ipr, bl)
            else:
                if domain != None:
                    check_name = "%s.%s" % (domain, bl)
            if check_name != None:
                check_items.append((bl, check_name, value, score))
                if check_name not in check_items_bl:
                    check_items_bl.append(check_name)

        if len(check_items) == 0:
            return (0, 0)

        if useAdns:
            check_items_bl_res = self.__adnsCheck(check_items_bl)
        else:
            check_items_bl_res = self.__dnspythonCheck(check_items_bl)

        retHit = 0
        retScore = 0

        for bl, name, value, score in check_items:
            if not check_items_bl_res.has_key(name): continue
            ips = check_items_bl_res[name]

            if value != '':
                for ip in ips:
                    if re.compile(value).match(ip):
                        logging.getLogger().debug("%s[%s:%s]: %s" % (bl, name, value, score))
                        retHit += 1
                        retScore += score
                        break
            else:
                logging.getLogger().debug("%s[%s]: %s" % (bl, name, score))
                retHit += 1
                retScore += score

        if retHit == 0:
            return (-1, 0)
        else:
            return (retHit, retScore)


    def __adnsCheck(self, check_items_bl):
        retVal = {}

        queries = {}
        if self.resolver == None or self.resolver == '':
            _adns = adns.init(adns.iflags.noautosys, sys.stderr)
        else:
            _adns = adns.init(adns.iflags.noautosys, sys.stderr, self.resolver)
        for bl in check_items_bl:
            queries[_adns.submit(bl, adns.rr.A)] = bl

        timeout = time.time() + self.timeout
        while len(queries) > 0 and time.time() < timeout:
            for query in _adns.completed(self.timeout):
                answer = query.check()
                bl = queries[query]
                del(queries[query])
                if answer[0] != 0: continue # query error
                retVal[bl] = list(answer[3])
        logging.getLogger().debug("timeout: %s" % ",".join(queries.values()))
        
        return retVal


    def __dnspythonCheck(self, check_items_bl):
        retVal = {}

        for bl in check_items_bl:

            # don't process DNS query for servers that timeouts
            if dnscache.dnsTimeoutBlacklistHas((bl.lower(), 'A')):
                continue

            ips = []
            try:
                resolver = dnscache.getResolver(3.0, 1.0)
                answer = resolver.query(bl, 'A')
                for rdata in answer:
                    ips.append(rdata.address)
            except dns.exception.Timeout:
                logging.getLogger().debug("DNS timeout, query: %s" % bl)
                dnscache.dnsTimeoutBlacklistAdd((bl.lower(), 'A'), 24*60*60)
            except dns.exception.DNSException:
                # no results or DNS problem
                pass

            if len(ips) > 0:
                retVal[bl] = ips

        return retVal




def getInstance(x = dnsbl):
    try:
        inst = x()
    except dnsbl, i:
        inst = i
    return inst
        #print type(e) == __main__.dnsbl



def score(ip = None, domain = None, checkList = []):
    """See documentation for dnsbl.score method."""
    return getInstance().score(ip, domain, checkList)


def check(ip = None, domain = None, checkList = [], score = False):
    """See documentation for dnsbl.check method."""
    return getInstance().check(ip, domain, checkList, score)




def parseSpamassassinCf(dnsblFile, scoreFile):
    """Parse spamassassin config files, find DNSBL definitions and scores."""
    config = {}

    reHeaderRbl2 = re.compile("^header\s+(\S+)\s+eval:check_rbl(|_txt|_envfrom)\('([^']*)',\s*'([^']*)'\)$")
    reHeaderRbl3 = re.compile("^header\s+(\S+)\s+eval:check_rbl(|_txt|_envfrom)\('([^']*)',\s*'([^']*)',\s*'([^']*)'\)$")

    # FIXME: eval:check_rbl_txt
    reHeaderRblSub = re.compile("^header\s+(\S+)\s+eval:check_rbl_sub\('([^']*)',\s*'([^']*)'\)$")
    reDescribe = re.compile("^describe\s+(\S+)\s+(.*)$")
    reScore1 = re.compile("^score\s+(\S+)\s+(\d+|\d+\.\d+)\s*$")
    reScore4 = re.compile("^score\s+(\S+)\s+(\d+|\d+\.\d+)\s+(\d+|\d+\.\d+)\s+(\d+|\d+\.\d+)\s+(\d+|\d+\.\d+)$")

    # read dnsbl definitions
    for line in dnsblFile.readlines():
        if line[0] == '#': continue
        if line == "\n": continue
        if line.find('#') != -1: line = line[:line.find('#')]
        line = line.strip()
        res = reHeaderRbl2.match(line)
        if res != None:
            cid = res.group(1)
            envfrom = res.group(2) == '_envfrom'
            name = res.group(3)
            bl = res.group(4)[:-1]
            config[cid] = { 'type': 'main', 'name': name, 'dnsbl': bl, 'score': (0, 0, 0, 0), 'envfrom': envfrom }
        res = reHeaderRbl3.match(line)
        if res != None:
            cid = res.group(1)
            envfrom = res.group(2) == '_envfrom'
            name = res.group(3)
            bl = res.group(4)[:-1]
#            val = res.group(5)
            config[cid] = { 'type': 'main', 'name': name, 'dnsbl': bl, 'score': (0, 0, 0, 0), 'envfrom': envfrom }
        res = reHeaderRblSub.match(line)
        if res != None:
            cid = res.group(1)
            name = res.group(2)
            val = res.group(3)
            config[cid] = { 'type': 'sub', 'name': name, 'value': val, 'score': (0, 0, 0, 0) }
        res = reDescribe.match(line)
        if res != None:
            cid = res.group(1)
            desc = res.group(2)
            if config.has_key(cid):
                config[cid].update({ 'desc': desc })

    # add blacklist score
    for line in scoreFile.readlines():
        if line[0] == '#': continue
        if line == "\n": continue
        if line.find('#') != -1: line = line[:line.find('#')]
        line = line.strip()
        res = reScore1.match(line)
        if res != None:
            cid = res.group(1)
            sc1 = float(res.group(2))
            if config.has_key(cid):
                config[cid].update({ 'score': (sc1, sc1, sc1, sc1) })
        res = reScore4.match(line)
        if res != None:
            cid = res.group(1)
            sc1 = float(res.group(2))
            sc2 = float(res.group(3))
            sc3 = float(res.group(4))
            sc4 = float(res.group(5))
            if config.has_key(cid):
                config[cid].update({ 'score': (sc1, sc2, sc3, sc4) })

    # remove items without required fields
    toDel = []
    for k,v in config.items():
        logging.getLogger().debug("%s: %s" % (k,v))
        if not v.has_key('type'):
            toDel.append(k)
    for k in toDel:
        del(config[k])

    # add dns to all items
    configMain = {}
    for k,v in config.items():
        if v['type'] == 'main':
#            logging.getLogger().debug("main module: %s (%s)" % (v['name'], k))
            configMain[v['name']] = v
#        else:
#            logging.getLogger().debug("sub module: %s[%s]" % (k, v['name']))
    # envelope subcheck
    for k,v in config.items():
        if v['type'] == 'sub':
            if configMain.has_key(v['name']):
                if configMain[v['name']].get('envfrom', False):
                    v['envfrom'] = True
                if not v.has_key('dnsbl'):
                    v['dnsbl'] = configMain[v['name']]['dnsbl']
            else:
                logging.getLogger().warn("main check for %s is not defined" % k)

    # print config
    for k,v in config.items():
        logging.getLogger().debug("%s: %s" % (k, v))
        print "# %s[%s] - %s" % (k, v['name'], v.get('desc', ''))
        print "%s %s %s %s %s" % (k, v['dnsbl'], v['score'][1], v.get('envfrom', 'False'), v.get('value', ''))


def parseDrbsites(configFile):
    """Parse http://moensted.dk/spam/drbsites.txt DNSBL file."""

    #config = {}
    for line in configFile.readlines():
        if line[0] != "'": continue
        xxx = line[line.find("'")+1:line.rfind("'")]
        while len(xxx.split(";")) < 13:
            xxx += ";"
        rblcode, rbls, rblw, rbln, rblp, rblabout, rblstatus, rblremoval, longname, check, txt, rbltype, rbldns = xxx.split(";")
        print "# %s - %s (%s)" % (rblcode, longname, rblp)
        print "%s %s %s %s %s" % (rblcode, rbls, 0, False, '')
        #self.config[rblcode] = ( rbls, rblw, rbln, rblp, rblabout, rblstatus, rblremoval, longname, check, txt, rbltype, rbldns )


def listDnsbl():
    config = getInstance().get_config()
    for k,v in config.items():
        print "%s" % k
        print "\tdnsbl: %s" % v.get('dnsbl')
        print "\tvalue: %s" % v.get('value')
        print "\tscore: %s" % str(v.get('score'))
        print "\tenvfrom: %s" % str(v.get('envfrom'))


def debugCheck(ip, sender = ''):
    print ">>> Checking %s %s <<<" % (ip, sender)
    if sender.find('@') != -1:
        user, domain = sender.split('@', 1)
    else:
        domain = sender
    dnsblList = [ 'DNS_FROM_AHBL_RHSBL', 'DNS_FROM_RFC_BOGUSMX', 'DNS_FROM_RFC_DSN', 'DNS_FROM_SECURITYSAGE', 'DNS_FROM_SECURITYSAGE', 'RCVD_IN_BL_SPAMCOP_NET', 'RCVD_IN_DSBL', 'RCVD_IN_NJABL_DUL', 'RCVD_IN_NJABL_PROXY', 'RCVD_IN_NJABL_SPAM', 'RCVD_IN_SBL', 'RCVD_IN_SORBS_DUL', 'RCVD_IN_SORBS_SOCKS', 'RCVD_IN_SORBS_WEB', 'RCVD_IN_SORBS_ZOMBIE', 'RCVD_IN_WHOIS_BOGONS', 'RCVD_IN_WHOIS_HIJACKED', 'RCVD_IN_WHOIS_INVALID', 'RCVD_IN_XBL' ]
    startTime = time.time()
    sc = check(ip, domain, dnsblList)
    print "%15s[%6.2f]: %s" % (ip, time.time()-startTime, sc)
    startTime = time.time()
    sc = check(ip, domain, dnsblList)
    print "%15s[%6.2f]: %s" % (ip, time.time()-startTime, sc)


def usage():
    print "usage: %s [--help] [--test] [--list] [--convert [ ... ]]" % sys.argv[0]
    print "Params:"
    print "  -h, --help\tthis help"
    print "  -q, -v, -l=x\tlog level"
    print "  -t --test\ttest pair of \"IP sender@mail.address\""
    print "  -i --list\tlist all known DNSBL and corresponding score"
    print "  -c, --convert\tconvert spamassassin configuration files"
    print "  --dnsbl-cf\tspamassassin dnsbl.cf file"
    print "  --score-cf\tspamassassin score.cf file"


if __name__ == "__main__":
    streamHandler = logging.StreamHandler(sys.stdout)
    streamHandler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s](%(module)s:%(lineno)d) %(message)s", "%d %b %H:%M:%S"))
    logging.getLogger().addHandler(streamHandler)
    logging.getLogger().setLevel(logging.INFO)

    import getopt
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hvql:tic",
                                   ["help", "verbose", "quiet", "log-level",
                                    "test", "list", "convert", "dnsbl-cf",
                                    "score-cf", "drbsites" ])
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    action = None
    dnsblFileName = None
    scoreFileName = None
    drbsitesFileName = None

    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        if o in ("-v", "--verbose"):
            logging.getLogger().setLevel(logging.DEBUG)
        if o in ("-q", "--quiet"):
            logging.getLogger().setLevel(logging.ERROR)
        if o in ("-l", "--log-level"):
            logging.getLogger().setLevel(int(a))
        if o in ("-t", "--test"):
            action = 'test'
        if o in ("-i", "--list"):
            action = 'list'
        if o in ("-c", "--convert"):
            action = 'convert'
        if o in ("--dnsbl-cf", ):
            dnsblFileName = a
        if o in ("--score-cf", ):
            scoreFileName = a
        if o in ("--drbsites", ):
            drbsitesFileName = a

    logging.getLogger().debug("command: %s" % " ".join(sys.argv))
    logging.getLogger().debug("version: %s" % __version__)

    if action == None:
        usage()
        sys.exit(1)
    if action == 'test':
        # test
        testIpSender = [ ("213.29.7.193", "petr.jambor@centrum.cz"),
                         ("12.154.9.125", "stephen@quasarman.biz"),
                         ("12.202.58.19", "philip@pistonheads.biz"),
                         ("12.205.105.185", "geoffrey@psychologen.biz"),
                         ("12.214.67.125", "aqruopft35C@yahoo.com"),
                         ("12.215.156.205", "acr2oof5u65@yahoo.com"),
                         ("12.218.133.172", "ucmcuuotyvili@earthlink.net"),
                         ("12.221.22.94", "nicholas@paramed.biz") ]
        if len(args) > 0:
            sender = ''
            ip = args[0]
            if len(args) > 1:
                sender = args[1]
            testIpSender = [ (ip, sender) ]
        for ip, sender in testIpSender:
            debugCheck(ip, sender)
    elif action == 'list':
        # list
        listDnsbl()
    elif action == 'convert':
        print "# "
        print "# configuration file for %s" % sys.argv[0]
        print "# file structure:"
        print "# name    url    score    env    [regex for returned IP address matching]"
        print "# "
        import urllib2
        urlbase = "http://svn.apache.org/repos/asf/spamassassin/trunk/rules"
        if dnsblFileName == None:
            dnsblFile = urllib2.urlopen("%s/20_dnsbl_tests.cf" % urlbase)
        else:
            dnsblFile = open(dnsblFileName)
        if scoreFileName == None:
            scoreFile = urllib2.urlopen("%s/50_scores.cf" % urlbase)
        else:
            scoreFile = open(scoreFileName)
        print "# "
        print "# "
        print "# spamassassin config file"
        print "# "
        parseSpamassassinCf(dnsblFile, scoreFile)
        dnsblFile.close()
        scoreFile.close()
        if drbsitesFileName == None:
            drbsitesFile = urllib2.urlopen("http://moensted.dk/spam/drbsites.txt")
        else:
            drbsitesFile = open(drbsitesFileName)
        print "# "
        print "# "
        print "# drbsites config file"
        print "# "
        parseDrbsites(drbsitesFile)
        drbsitesFile.close()

