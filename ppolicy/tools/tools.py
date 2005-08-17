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


#
# DNS
#

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


#
# Param functions
# def paramFunction(string):
#     return [ "str1", "str2", ... ]
#

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


def safeSubstitute(text, dict, unknown = 'UNKNOWN'):
    """Replace keywords in text with data from dictionary. If there is
    not matching key in dictionary, use unknown."""
    import re
    retVal = text
    keywords = re.findall("%(\(.*?\))", text)
    replace = []
    for keyword in keywords:
        if not dict.has_key(keyword[1:-1]):
            replace.append(".\(%s\)." % keyword[1:-1])
    for repl in replace:
        retVal = re.sub(repl, unknown, retVal)
    return retVal % dict



#
# Classes for data caching
#
class MemCache:
    """Base class for cache. It implements memory caching and provide
    interface for subclasses that can add e.g. database caching.

    parameters:
      memExpire - handle different expiration for different records if you
        set this variable > 0. Otherwise per record expiration is not used.
      memMaxSize - maximum cached record in memory
    """

    # How many record should stay in cache if its size reach memMaxSize limit.
    CLEAR_FACTOR = 2./3

    def __init__(self, memExpire = 0, memMaxSize = 0):
        self.memExpire = getattr(self, 'memExpire', memExpire)
        self.memMaxSize = getattr(self, 'memMaxSize', memMaxSize)
        self.cacheVal = {}
        self.cacheUse = {}
        self.cacheExp = {}
        self.lock = threading.Lock()


    def __cleanCache(self, all = False):
        """If cache is full clear CLEAR_FACTOR. It is not thread safe
        and has to be called with acquired lock."""
        if all:
            self.cacheVal.clear()
            self.cacheUse.clear()
            self.cacheExp.clear()
        else:
            toDel = []
            sval = sorted(self.cacheUse.values())
            trh = sval[int(self.memMaxSize*self.CLEAR_FACTOR)]
            for keyToDel in self.cacheUse.keys():
                if self.cacheUse[keyToDel] <= trh or (self.memExpire > 0 and self.cacheExp[keyToDel] < time.time()):
                    toDel.append(keyToDel)
            for keyToDel in toDel:
                del self.cacheVal[keyToDel]
                del self.cacheUse[keyToDel]
                if self.memExpire != 0:
                    del self.cacheExp[keyToDel]


    def clean(self):
        """Clean all records in memory cache."""
        self.lock.acquire()
        try:
            self.__cleanCache(True)
        finally:
            self.lock.release()


    def reload(self, data = None):
        """Clean/Reload data cache."""
        self.lock.acquire()
        try:
            self.clean()
            if data != None:
                for d in data:
                    if len(d) > 1:
                        self.cacheVal[d[0]] = d[1]
                    else:
                        self.cacheVal[d[0]] = True
                    if self.memExpire > 0:
                        self.cacheExp[d[0]] = time.time() + self.memExpire
                        if len(d) > 2 and time.time() + self.memExpire > d[2]:
                            self.cacheExp[d[0]] = d[2]
                    if self.memMaxSize > 0:
                        self.cacheUse[d[0]] = time.time()
        finally:
            self.lock.release()


    def get(self, key, default = None):
        val = default
        self.lock.acquire()
        try:
            if self.cacheVal.has_key(key):
                if self.memMaxSize > 0:
                    self.cacheUse[key] = time.time()
                if self.memExpire == 0:
                    val = self.cacheVal[key]
                elif self.cacheExp[key] >= time.time():
                    val = self.cacheVal[key]
                else:
                    # remove memExpired record
                    del self.cacheVal[key]
                    del self.cacheExp[key]
                    if self.memMaxSize > 0:
                        del self.cacheUse[key]
        finally:
            self.lock.release()
        return val


    def set(self, key, val, exp = 0):
        self.lock.acquire()
        try:
            if self.memMaxSize > 0 and len(self.cacheUse) >= self.memMaxSize:
                self.__cleanCache()
            self.cacheVal[key] = val
            if self.memExpire > 0:
                if exp == 0:
                    exp = self.memExpire
                self.cacheExp[key] = time.time() + exp
            if self.memMaxSize > 0:
                self.cacheUse[key] = time.time()
        finally:
            self.lock.release()



class DbCache:
    """Pernament database cache. It can use MemCache for speedup access
    regularly requested records.

    Parameters:
      parent - reference to Check object (needed for db connection)
      table - database table to read/save cached items
      cols - database column to store data (dictionary of name, value, expire)
      memCache - use memory cache (default: True)
      memExpire - expiration time of item in MemCache (default: 600s)
      memMaxSize - maximum item in MemCache (default: 0 - infinite)
    """

    # stop to use db after limit reached
    ERROR_LIMIT = 10
    # time after which errorLimit will be increased
    ERROR_SLEEP = 120
    # table type
    TABLE_TYPE = 'ENGINE=MyISAM DEFAULT CHARSET=latin1'

    class DbCacheError(Exception):
        """Base exception class."""
        def __init__(self, args = ""):
            Exception.__init__(self, args)

    def __init__(self, parent, table, cols,
                 memCache = True, memExpire = 600, memMaxSize = 0):
        if parent == None or table == None or cols == None:
            raise DbCache.DbCacheError("Undefined required param: %s, %s, %s" %
                                       (parent, table, cols))
        self.getId = parent.getId
        self.getDbConnection = parent.getDbConnection
        self.table = getattr(self, 'table', table)
        self.cols = getattr(self, 'cols', cols)
        self.memCache = getattr(self, 'memCache', memCache)
        self.memExpire = getattr(self, 'memExpire', memExpire)
        self.memMaxSize = getattr(self, 'memMaxSize', memMaxSize)
        if memCache:
            self.cacheVal = MemCache(memExpire, memMaxSize)
        else:
            self.cacheVal = None
        self.errorLimit = self.ERROR_LIMIT
        self.errorSleep = 0
        self.useDb = True
        self.__createDb()
        self.lastReload = 0
        self.reload()
        self.lock = threading.Lock()


    def __createDb(self):
        """Check if we can use db connection, check existence or required
        table and create new if doesn't exist."""
        try:
            colsDef = []
            if 'name' not in self.cols.keys():
                raise DbCache.DbCacheError("Name field is required %s" % self.table)
            if self.cols.has_key('name'):
                colsDef.append("%s VARCHAR(50) NOT NULL PRIMARY KEY" % self.cols['name'])
            if self.cols.has_key('value'):
                for val in self.cols['value']:
                    colsDef.append("%s VARCHAR(200)" % val)
            if self.cols.has_key('expire'):
                colsDef.append("%s TIMESTAMP NOT NULL" % self.cols['expire'])
            for k, v in self.cols.items():
                if k not in [ 'name', 'value', 'expire' ]:
                    raise DbCache.DbCacheError("Unknown column name %s in table %s" %
                                               (k, self.table))
            sql = "CREATE TABLE IF NOT EXISTS %s ( %s ) %s" % (self.table, ",".join(colsDef), DbCache.TABLE_TYPE)
            conn = self.getDbConnection()
            cursor = conn.cursor()
            cursor.execute(sql)
            sql = "SELECT %s FROM %s" % (self.__getCols(), self.table)
            cursor.execute(sql)
            cursor.close()
        except DbCache.DbCacheError, err:
            raise err
        except Exception, err:
            log.msg("[ERR] %s: query '%s': %s" % (self.getId(), sql, err))


    def __getCols(self):
        retval = []
        if self.cols.has_key('name'):
            retval.append(self.cols['name'])
        if self.cols.has_key('value'):
            for val in self.cols['value']:
                retval.append(val)
        if self.cols.has_key('expire'):
            retval.append(self.cols['expire'])
        return ",".join(retval)


    def __useDb(self):
        """Not thread safe - has to be called with acquired lock."""
        if self.errorLimit <= 0:
            if self.useDb:
                self.useDb = False
                self.errorSleep = time.time() + self.ERROR_SLEEP
            elif self.errorSleep < time.time():
                self.useDb = True
                self.errorLimit = self.ERROR_LIMIT
        return self.useDb


    def clean(self, db = False):
        if db:
            try:
                sql = "DELETE FROM %s" % self.table
                conn = self.getDbConnection()
                cursor = conn.cursor()
                cursor.execute(sql)
                cursor.close()
            except Exception, err:
                log.msg("[ERR] %s: error cleaning %s: %s" %
                        (self.getId(), self.table, err))
        self.cacheVal.clean()


    def reload(self):
        if not self.memCache:
            return
        try:
            sql = ""
            conn = self.getDbConnection()
            cursor = conn.cursor()
            if self.memMaxSize > 0:
                sql = "SELECT COUNT(*) FROM %s" % self.table
                cursor.execute(sql)
                row = cursor.fetchone()
                if self.memMaxSize > row[0]:
                    self.cacheVal.clean()
                    return
            sql = "SELECT %s FROM %s" % (self.__getCols(), self.table)
            cursor.execute(sql)
            self.cacheVal.reload(cursor.fetchall(), self.cols)
            log.msg("[INF] %s: loaded %s rows from %s" %
                    (self.getId(), cursor.rowcount, self.table))
            cursor.close()
            self.lastReload = time.time()
        except Exception, err:
            # use only memory cache in case of DB problems
            log.msg("[ERR] %s: error loading %s: %s" %
                    (self.getId(), self.table, err))
            self.cacheVal.clean()


    def get(self, key, default = None):
        """Get data from cache."""
        retVal = default
        self.lock.acquire()
        try:
            if self.memExpire > 0 and self.memMaxSize == 0:
                if self.lastReload < time.time() - self.memExpire:
                    self.reload()
            retVal = self.cacheVal.get(key, default)
            if retVal == default and self.__useDb() and self.memMaxSize > 0:
                sql = "SELECT %s FROM %s WHERE %s == '%s'" % (self.__getCols(), self.table, self.cols['name'], key)
                conn = self.getDbConnection()
                cursor = conn.cursor()
                cursor.execute(sql)
                if cursor.rowcount > 0:
                    if cursor.rowcount > 1:
                        log.msg("[WRN] %s: more records in %s for %s" %
                                (self.getId(), self.table, key))
                    row = cursor.fetchone()
                    if row != None:
                        value = True
                        if self.cols.has_key('value'):
                            if len(self.cols['value']) == 1:
                                value = row[1]
                            else:
                                value = tuple()
                                for i in range(0, len(self.cols['value'])):
                                    value += (row[1+i])
                        expire = self.memExpire
                        if self.cols.has_key('expire') and time.time() + self.memExpire > row[2]:
                            expire = row[len(row)-1]
                        self.cacheVal.set(key, value, expire)
                        if expire >= time.time():
                            retVal = value
                cursor.close()
        except Exception, err:
            log.msg("[ERR] %s: cache error (table: %s, key: %s, err: %s): %s" %
                    (self.getId(), self.table, key, self.errorLimit, err))
            self.errorLimit -= 1
        self.lock.release()
        return retVal


    def set(self, key, val = True, exp = 0):
        """Set data in cache."""
        self.lock.acquire()
        try:
            self.cacheVal.set(key, val, self.memExpire)
            if self.__useDb():
                sql = "SELECT COUNT(*) FROM %s WHERE %s = '%s'" % (self.table, self.cols['name'], key)
                conn = self.getDbConnection()
                cursor = conn.cursor()
                cursor.execute(sql)
                row = cursor.fetchone ()
                if row != None:
                    if row[0] == 0:
                        sql = "INSERT INTO %s (%s) VALUES ('%s'" % (self.table, self.__getCols(), key)
                        if self.cols.has_key('value'):
                            if len(self.cols['value']) == 1:
                                sql += ", '%s'" % val
                            else:
                                for i in range(0, len(self.cols['value'])):
                                    sql += ", '%s'" % val[i]
                        if self.cols.has_key('expire'):
                            sql += "FROM_UNIXTIME(%i)" % long(exp)
                        cursor.execute(sql)
                    else:
                        sql = "UPDATE %s SET " % self.table
                        if self.cols.has_key('value'):
                            if len(self.cols['value']) == 1:
                                sql += "%s = '%s'" % (self.cols['value'], val)
                            else:
                                for i in range(0, len(self.cols['value'])):
                                    sql += "%s = '%s'" % (self.cols['value'][i], val[i])
                        if self.cols.has_key('expire'):
                            sql += ", %s = FROM_UNIXTIME(%i) " % (self.cols['expire'], long(exp))
                        sql += "WHERE %s = '%s'" % (self.cols['name'], key)
                        if self.cols > 1:
                            cursor.execute(sql)
                cursor.close()
        except IndexError, err:
            log.msg("[ERR] %s: wrong number of parameters: %s" %
                    (self.getId(), err))
        except Exception, err:
            log.msg("[ERR] %s: cache error (table: %s, key: %s, err: %s): %s" %
                    (self.getId(), self.table, key, self.errorLimit, err))
            self.errorLimit -= 1
        self.lock.release()




class FakeCheck:
    def getId(self):
        return "FakeCheck"
    def getDbConnection(self):
        return None

if __name__ == "__main__":
    print "Module tests:"
    import sys
    log.startLogging(sys.stdout)

    print "##### DNS #####"
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

    print "##### MemCache #####"
    memCache = MemCache(30, 10)
    for i in range(0, 20):
        memCache.set(i, i)
    for i in range(0, 20):
        print memCache.get(i)

    print "##### DbCache #####"
    dbCache = DbCache(FakeCheck(), 'test', { 'name': 'name', 'value': 'value',
                                            'expire': 'expire' }, True, 900, 0)
