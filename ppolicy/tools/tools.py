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
import time, threading
import dns.resolver
import dns.exception
from twisted.python import log


# DNS query parameters
_dnsResolvers = {}
_dnsCache = dns.resolver.Cache()
_dnsMaxRetry = 3
_dnsLifetime = 3.0
_dnsTimeout = 1.0


def getResolver(lifetime, timeout):
    resolver = _dnsResolvers.get((lifetime, timeout))
    if resolver == None:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = lifetime
        resolver.timeout = timeout
        resolver.cache = _dnsCache
        _dnsResolvers[(lifetime, timeout)] = resolver
    return resolver


def getFqdnIPs(domain, ipv6 = True):
    """Return IP addresses for FQDN. Optional parametr @ipv6 specify
    if IPv6 addresses should be added too (default: True)"""

    ips = []
    dnsretry = _dnsMaxRetry
    lifetime = _dnsLifetime
    timeout = _dnsTimeout

    if ipv6:
        types = [ 'A', 'AAAA' ]
    else:
        types = [ 'A' ]

    for qtype in types:
        dnsretry = _dnsMaxRetry
        while dnsretry > 0:
            dnsretry -= 1
            try:
                answer = getResolver(lifetime, timeout).query(domain, qtype)
                for rdata in answer:
                    ips.append(rdata.address)
                break
            except dns.exception.Timeout:
                log.msg("[DBG] DNS timeout (%s, %s), try #%s, query: %s [%s]" %
                        (lifetime, timeout, _dnsMaxRetry - dnsretry,
                         domain, qtype))
                lifetime *= 2
                timeout *= 2
            except dns.exception.DNSException:
                # no results or DNS problem
                break
    return ips


def getDomainMailhosts(domain, ipv6 = True):
    """Return IP addresses of mail exchangers for the domain
    sorted by priority."""

    ips = []
    dnsretry = _dnsMaxRetry
    lifetime = _dnsLifetime
    timeout = _dnsTimeout

    while dnsretry > 0:
        dnsretry -= 1
        try:
            # try to find MX records
            answer = getResolver(lifetime, timeout).query(domain, 'MX')
            fqdnPref = {}
            for rdata in answer:
                fqdnPref[rdata.preference] = rdata.exchange.to_text(True)
            fqdnPrefKeys = fqdnPref.keys()
            fqdnPrefKeys.sort()
            for key in fqdnPrefKeys:
                for ip in getFqdnIPs(fqdnPref[key], ipv6):
                    ips.append(ip)
            break
        except dns.exception.Timeout:
            log.msg("[DBG] DNS timeout (%s, %s), try #%s, query: %s [%s]" %
                    (lifetime, timeout, _dnsMaxRetry - dnsretry, domain, 'MX'))
            lifetime *= 2
            timeout *= 2
        except dns.resolver.NoAnswer:
            # search for MX failed, try A (AAAA) record
            for ip in getFqdnIPs(domain, ipv6):
                ips.append(ip)
            break
        except dns.exception.DNSException:
            # no results or DNS problem
            break
    return [ ip for ip in ips if ip not in [ '127.0.0.1', '0.0.0.0',
                                             '::0', '::1' ] ]


def funcMailToPostfixLookup(mail, split = True, user = True, userAt = True):
    if mail == None or mail == '':
        return []
    try:
        username, domain = mail.split("@")
        domainParts = domain.split(".")
    except ValueError:
        return []
    if not split:
        if user:
            return [ "%s@%s" % (username, ".".join(domainParts)) ]
        else:
            return [ "%s" % ".".join(domainParts) ]
    retVal = []
    if user:
        retVal.append("%s@%s" % (username, ".".join(domainParts)))
    while len(domainParts) > 0:
        retVal.append("%s" % ".".join(domainParts))
        domainParts.pop(0)
    if userAt:
        retVal.append("%s@" % username)
    return retVal
def funcMailToUserDomain(mail, split = False):
    return funcMailToPostfixLookup(mail, split, True, False)
def funcMailToUserDomainSplit(mail):
    return funcMailToUserDomain(mail, True)
def funcMailToDomain(mail, split = False):
    return funcMailToPostfixLookup(mail, split, False, False)
def funcMailToDomainSplit(mail):
    return funcMailToDomain(mail, True)


def code2nr(code):
    if code == None:
        return '0.0.0'
    else:
        return ".".join([ x for x in str(code) ])


def safeSubstitute(text, dict):
    import re
    retVal = text
    keywords = re.findall("%(\(.*?\))", text)
    replace = []
    for keyword in keywords:
        if not dict.has_key(keyword[1:-1]):
            replace.append(".\(%s\)." % keyword[1:-1])
    for repl in replace:
        retVal = re.sub(repl, "UNKNOWN", retVal)
    return retVal % dict


class DbMemListCache:
    """Cache for list check. Method 'get' return action and text if name
    is in table. Otherwise and in case of error it returns dunno.
    If possible don't use limited cache size because it dramatically reduce
    performance."""

    # stop to use db after limit reached
    ERROR_LIMIT = 10
    # time after which errorLimit will be increased
    ERROR_SLEEP = 120

    def __init__(self, parent, table = None, cols = None, maxSize = 0):
        self.getId = parent.getId
        self.getDbConnection = parent.getDbConnection
        self.useDb = True
        self.table = table
        self.cols = cols
        self.maxSize = 0
        if maxSize > 0:
            self.maxSize = maxSize
        self.cacheRes = {}
        self.cacheUse = {}
        self.errorLimit = self.ERROR_LIMIT
        self.errorSleep = 0
        self.lock = threading.Lock()
        if self.useDb:
            self.__checkDb()
        if self.useDb and self.maxSize == 0:
            self.__readAll()


    def __checkDb(self):
        """Check if we can use db connection, check existence or required
        table and create new if doesn't exist."""
        try:
            conn = self.getDbConnection()
            cursor = conn.cursor()
            if self.table != None:
                cursor.execute("CREATE TABLE IF NOT EXISTS %s ( %s VARCHAR(50) NOT NULL PRIMARY KEY, %s VARCHAR(20), %s VARCHAR(200) ) ENGINE=MyISAM DEFAULT CHARSET=latin1" % (self.table, self.cols['name'], self.cols['action'], self.cols['explanation'] ))
                cursor.execute("SELECT * FROM %s WHERE 0 = 1" % self.table)
        except Exception, err:
            log.msg("[ERR] %s: checking db %s: %s" % (self.getId(), self.table,
                                                      err))

    def __readAll(self):
        try:
            conn = self.getDbConnection()
            cursor = conn.cursor()
            if self.table != None:
                cursor.execute("SELECT %s, %s, %s FROM %s" %
                               (self.cols['name'], self.cols['action'],
                                self.cols['explanation'], self.table))
                while (True):
                    row = cursor.fetchone()
                    if row == None: break
                    self.cacheRes[row[0]] = ( row[1], row[2] )
                    self.cacheUse[row[0]] = time.time()
                log.msg("[INF] %s: loaded %s rows from %s" %
                        (self.getId(), cursor.rowcount, self.table))
            cursor.close()
            self.maxSize = -1
        except Exception, err:
            # use only memory cache in case of DB problems
            log.msg("[ERR] %s: error loading %s: %s" %
                    (self.getId(), self.table, str(err)))
            self.errorLimit -= 1


    def __cacheCheckCleanFull(self):
        """If cache is full clear 1/2. Call only inside block
        with acquired cache lock."""
        if self.maxSize > 0 and len(self.cacheUse) >= self.maxSize:
            trh = sorted(self.cacheUse.values())[self.maxSize/2]
            toDel = []
            for keyToDel in self.cacheUse.keys():
                if self.cacheUse[keyToDel] <= trh:
                    toDel.append(keyToDel)
            for keyToDel in toDel:
                del(self.cacheRes[keyToDel])
                del(self.cacheUse[keyToDel])


    def get(self, key):
        """Get data from cache."""
        retVal = (None, None, None)
        self.lock.acquire()
        try:
            if self.errorLimit <= 0:
                if self.useDb:
                    self.errorSleep = time.time() + self.ERROR_SLEEP
                    self.useDb = False
                elif self.errorSleep < time.time():
                    self.useDb = True
                    self.errorLimit = self.ERROR_LIMIT
            # load cache data firstime if we can load everything
            if self.useDb and self.maxSize == 0:
                self.__readAll()
            # memory cache
            if self.cacheRes.has_key(key):
                self.cacheUse[key] = time.time()
                retVal = self.cacheRes[key]
            # database cache
            elif self.useDb and self.maxSize > 0:
                conn = self.getDbConnection()
                cursor = conn.cursor()
                if self.table:
                    cursor.execute("SELECT %s, %s, %s FROM %s WHERE %s == '%s'" %
                                   (self.cols['name'], self.cols['action'],
                                    self.cols['explanation'], self.table,
                                    self.cols['name'], key))
                    if cursor.rowcount > 0:
                        if cursor.rowcount > 1:
                            log.msg("[WRN] %s: more records in %s for %s (using first)" % (self.getId(), self.table, key))
                        row = cursor.fetchone()
                        if row != None:
                            self.__cacheCheckCleanFull()
                            self.cacheRes[key] = ( row[1], row[2] )
                            self.cacheUse[key] = time.time()
                            retVal = ( row[1], row[2] )
                cursor.close()
        except Exception, err:
            log.msg("[ERR] %s: cache error (table: %s, key: %s, limit: %s): %s" %
                    (self.getId(), self.table, key, self.errorLimit, str(err)))
            self.errorLimit -= 1
            retVal = (None, None, None)
        self.lock.release()
        return retVal



class DbMemListWBCache:
    """Cache for white/black lists. Method 'get' return True if key is in
    whitelist, False if key is in blacklist and None if it is not in either.
    If possible don't use limited cache size because it dramatically reduce
    performance."""

    # stop to use db after limit reached
    ERROR_LIMIT = 10
    # time after which errorLimit will be increased
    ERROR_SLEEP = 120

    def __init__(self, parent, wtable = None, wcol = 'name',
                 btable = None, bcol = 'name', maxSize = 0):
        self.getId = parent.getId
        self.getDbConnection = parent.getDbConnection
        self.useDb = True
        self.wtable = wtable
        self.wcol = wcol
        self.btable = btable
        self.bcol = bcol
        self.maxSize = 0
        if maxSize > 0:
            self.maxSize = maxSize
        self.cacheRes = {}
        self.cacheUse = {}
        self.errorLimit = self.ERROR_LIMIT
        self.errorSleep = 0
        self.lock = threading.Lock()
        if self.useDb:
            self.__checkDb()
        if self.useDb and self.maxSize == 0:
            self.__readAll()


    def __checkDb(self):
        """Check if we can use db connection, check existence or required
        table and create new if doesn't exist."""
        try:
            conn = self.getDbConnection()
            cursor = conn.cursor()
            if self.wtable != None:
                cursor.execute("CREATE TABLE IF NOT EXISTS %s ( %s VARCHAR(50) NOT NULL PRIMARY KEY ) ENGINE=MyISAM DEFAULT CHARSET=latin1" % (self.wtable, self.wcol))
                cursor.execute("SELECT %s FROM %s WHERE 0 = 1" %
                               (self.wcol, self.wtable))
            if self.btable != None:
                cursor.execute("CREATE TABLE IF NOT EXISTS %s ( %s VARCHAR(50) NOT NULL PRIMARY KEY ) ENGINE=MyISAM DEFAULT CHARSET=latin1" % (self.btable, self.bcol))
                cursor.execute("SELECT %s FROM %s WHERE 0 = 1" %
                               (self.bcol, self.btable))
        except Exception, err:
            log.msg("[ERR] %s: checking db %s/%s: %s" %
                    (self.getId(), self.wtable, self.btable, str(err)))

    def __readAll(self):
        try:
            conn = self.getDbConnection()
            cursor = conn.cursor()
            if self.wtable != None:
                cursor.execute("SELECT %s FROM %s" % (self.wcol, self.wtable))
                while (True):
                    row = cursor.fetchone()
                    if row == None: break
                    self.cacheRes[row[0]] = True
                    self.cacheUse[row[0]] = time.time()
                log.msg("[INF] %s: loaded %s rows from %s" %
                        (self.getId(), cursor.rowcount, self.wtable))
            if self.btable != None:
                cursor.execute("SELECT %s FROM %s" % (self.bcol, self.btable))
                while (True):
                    row = cursor.fetchone()
                    if row == None: break
                    if self.cacheRes.has_key(row[0]): continue # WL preference
                    self.cacheRes[row[0]] = False
                    self.cacheUse[row[0]] = time.time()
                log.msg("[INF] %s: loaded %s rows from %s" %
                        (self.getId(), cursor.rowcount, self.btable))
            cursor.close()
            self.maxSize = -1
        except Exception, err:
            # use only memory cache in case of DB problems
            log.msg("[ERR] %s: error loading %s/%s: %s" %
                    (self.getId(), self.wtable, self.btable, str(err)))
            self.errorLimit -= 1


    def __cacheCheckCleanFull(self):
        """If cache is full clear 1/2. Call only inside block
        with acquired cache lock."""
        if self.maxSize > 0 and len(self.cacheUse) >= self.maxSize:
            trh = sorted(self.cacheUse.values())[self.maxSize/2]
            toDel = []
            for keyToDel in self.cacheUse.keys():
                if self.cacheUse[keyToDel] <= trh:
                    toDel.append(keyToDel)
            for keyToDel in toDel:
                del(self.cacheRes[keyToDel])
                del(self.cacheUse[keyToDel])


    def get(self, key):
        """Get data from cache."""
        retVal = None
        self.lock.acquire()
        try:
            if self.errorLimit <= 0:
                if self.useDb:
                    self.errorSleep = time.time() + self.ERROR_SLEEP
                    self.useDb = False
                elif self.errorSleep < time.time():
                    self.useDb = True
                    self.errorLimit = self.ERROR_LIMIT
            # load cache data firstime if we can load everything
            if self.useDb and self.maxSize == 0:
                self.__readAll()
            # memory cache
            if self.cacheRes.has_key(key):
                self.cacheUse[key] = time.time()
                retVal = self.cacheRes[key]
            # database cache
            elif self.useDb and self.maxSize > 0:
                conn = self.getDbConnection()
                cursor = conn.cursor()
                if self.wtable:
                    cursor.execute("SELECT %s FROM %s WHERE %s == '%s'" %
                                   (self.wcol, self.wtable, self.wcol, key))
                    if cursor.rowcount > 0:
                        self.__cacheCheckCleanFull()
                        self.cacheRes[key] = True
                        self.cacheUse[key] = time.time()
                if self.btable and not self.cacheRes.has_key(key): # WL pref
                    cursor.execute("SELECT %s FROM %s WHERE %s == '%s'" %
                                   (self.bcol, self.btable, self.bcol, key))
                    if cursor.rowcount > 0:
                        self.__cacheCheckCleanFull()
                        self.cacheRes[key] = False
                        self.cacheUse[key] = time.time()
                cursor.close()
                retVal = self.cacheRes.get(key)
        except Exception, err:
            log.msg("[ERR] %s: cache error (table: %s/%s, key: %s, limit: %s): %s" %
                    (self.getId(), self.wtable, self.btable,
                     key, self.errorLimit, str(err)))
            self.errorLimit -= 1
            retVal = None
        self.lock.release()
        return retVal



class DbMemCache:

    # stop to use db after limit reached
    ERROR_LIMIT = 10
    # time after which errorLimit will be increased
    ERROR_SLEEP = 120

    def __init__(self, parent, table = None,
                 cols = { 'key': 'name', 'res': 'result', 'exp': 'expir' },
                 maxSize = 0):
        self.getId = parent.getId
        self.getDbConnection = parent.getDbConnection
        self.table = table
        self.colKey = cols.get('key')
        self.colRes = cols.get('res')
        self.colExp = cols.get('exp')
        self.useDb = self.table != None and self.colKey != None and self.colRes != None and self.colExp != None
        self.maxSize = 0
        if maxSize > 0:
            self.maxSize = maxSize
        self.cacheRes = {}
        self.cacheExp = {}
        self.cacheUse = {}
        self.errorLimit = self.ERROR_LIMIT
        self.errorSleep = 0
        self.lock = threading.Lock()
        if self.useDb:
            self.__checkDb()
        if self.useDb and self.maxSize == 0:
            self.__readAll()


    def __checkDb(self):
        """Check if we can use db connection, check existence or required
        table and create new if doesn't exist."""
        try:
            conn = self.getDbConnection()
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS %s ( %s VARCHAR(50) NOT NULL PRIMARY KEY, %s VARCHAR(100), %s TIMESTAMP NOT NULL ) ENGINE=MyISAM DEFAULT CHARSET=latin1" % (self.table, self.colKey, self.colRes, self.colExp))
            cursor.execute("SELECT %s, %s, UNIX_TIMESTAMP(%s) FROM %s WHERE 0 = 1" %
                           (self.colKey, self.colRes, self.colExp, self.table))
        except Exception, err:
            log.msg("[ERR] %s: checking db %s: %s" %
                    (self.getId(), self.table, str(err)))

    def __readAll(self):
        try:
            conn = self.getDbConnection()
            cursor = conn.cursor()
            cursor.execute("SELECT %s, %s, UNIX_TIMESTAMP(%s) FROM %s" %
                         (self.colKey, self.colRes, self.colExp, self.table))
            while (True):
                row = cursor.fetchone()
                if row == None: break
                self.cacheRes[row[0]] = row[1]
                self.cacheExp[row[0]] = row[2]
                self.cacheUse[row[0]] = time.time()
            log.msg("[INF] %s: loaded %s rows from %s" %
                    (self.getId(), cursor.rowcount, self.table))
            cursor.close()
            self.maxSize = -1
        except Exception, err:
            # use only memory cache in case of DB problems
            log.msg("[ERR] %s: error loading %s: %s" %
                    (self.getId(), self.table, str(err)))
            self.errorLimit -= 1


    def __cacheCheckCleanFull(self):
        """If cache is full clear 1/2. Call only inside block
        with acquired cache lock."""
        if self.maxSize > 0 and len(self.cacheExp) >= self.maxSize:
            trh = sorted(self.cacheUse.values())[self.maxSize/2]
            toDel = []
            for keyToDel in self.cacheUse.keys():
                if self.cacheUse[keyToDel] <= trh:
                    toDel.append(keyToDel)
            for keyToDel in toDel:
                del(self.cacheRes[keyToDel])
                del(self.cacheExp[keyToDel])
                del(self.cacheUse[keyToDel])


    def get(self, key):
        """Get data from cache."""
        retVal = None
        self.lock.acquire()
        try:
            if self.errorLimit <= 0:
                if self.useDb:
                    self.errorSleep = time.time() + self.ERROR_SLEEP
                    self.useDb = False
                elif self.errorSleep < time.time():
                    self.useDb = True
                    self.errorLimit = self.ERROR_LIMIT

            # load cache data firstime if we can load everything
            if self.useDb and self.maxSize == 0:
                self.__readAll()

            # memory cache
            if self.cacheExp.has_key(key) and self.cacheExp[key] >= time.time():
                self.cacheUse[key] = time.time()
                retVal = self.cacheRes[key]
            # database cache
            elif self.useDb and self.maxSize > 0:
                conn = self.getDbConnection()
                cursor = conn.cursor()
                cursor.execute("SELECT %s, UNIX_TIMESTAMP(%s) FROM %s WHERE %s == '%s'" %
                               (self.colRes, self.colExp, self.table,
                                self.colKey, key))
                if cursor.rowcount > 0:
                    if cursor.rowcount > 1:
                        log.msg("[WRN] %s: more rows for key %s" %
                                (self.getId(), key))
                    row = cursor.fetchone ()
                    if row != None:
                        self.__cacheCheckCleanFull()
                        self.cacheRes[key] = row[0]
                        self.cacheExp[key] = row[1]
                        self.cacheUse[key] = time.time()
                cursor.close()
                retVal = self.cacheRes.get(key)

        except Exception, err:
            log.msg("[ERR] %s: cache error (table: %s, key: %s, limit: %s): %s" %
                    (self.getId(), self.table, key, self.errorLimit, str(err)))
            self.errorLimit -= 1
            retVal = None

        self.lock.release()
        return retVal


    def set(self, key, value, expir):
        """Set data in the cache."""
        self.lock.acquire()
        try:
            if self.errorLimit <= 0:
                if self.useDb:
                    self.errorSleep = time.time() + self.ERROR_SLEEP
                    self.useDb = False
                elif self.errorSleep < time.time():
                    self.useDb = True
                    self.errorLimit = self.ERROR_LIMIT

            # memory cache
            self.__cacheCheckCleanFull()
            self.cacheRes[key] = value
            self.cacheExp[key] = expir
            self.cacheUse[key] = time.time()

            # database cache
            if self.useDb:
                conn = self.getDbConnection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM %s WHERE %s = '%s'" %
                             (self.table, self.colKey, key))
                row = cursor.fetchone ()
                if row != None:
                    if row[0] == 0:
                        cursor.execute("INSERT INTO %s (%s, %s, %s) VALUES ('%s', '%s', FROM_UNIXTIME(%i))" %
                                       (self.table, self.colKey, self.colRes,
                                        self.colExp, key, value, long(expir)))
                    else:
                        cursor.execute("UPDATE %s SET %s = '%s', %s = FROM_UNIXTIME(%i) WHERE %s = '%s'" %
                                       (self.table, self.colRes, value,
                                        self.colExp, expir, self.colKey, key))
                cursor.close()

        except Exception, err:
            log.msg("[ERR] %s: cache error (table: %s, key: %s, limit: %s): %s" %
                    (self.getId(), self.table, key, self.errorLimit, str(err)))
            self.errorLimit -= 1

        self.lock.release()



if __name__ == "__main__":
    print "Module tests:"
    import sys
    log.startLogging(sys.stdout)
    print
    print ">>>>> %s" % getFqdnIPs.__name__
    for domain in [ "fjfi.cvut.cz", "ns.fjfi.cvut.cz",
                    "bimbod.fjfi.cvut.cz", "nmsd.fjfi.cvut.cz",
                    "unknown.fjfi.cvut.cz", "sh.cvut.cz",
                    "nightmare.sh.cvut.cz" ]:
        print ">>> %s" % domain
        print getFqdnIPs(domain)
    print
    print ">>>>> %s" % getDomainMailhosts.__name__
    for domain in [ "fjfi.cvut.cz", "ns.fjfi.cvut.cz",
                    "bimbod.fjfi.cvut.cz", "nmsd.fjfi.cvut.cz",
                    "unknown.fjfi.cvut.cz", "sh.cvut.cz",
                    "nightmare.sh.cvut.cz" ]:
        print ">>> %s" % domain
        print getDomainMailhosts(domain)
