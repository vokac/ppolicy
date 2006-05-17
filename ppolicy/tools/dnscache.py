#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# DNS related functions
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
import time
import random
import struct
import socket
import threading
import dns.resolver
import dns.exception


class Cache(object):
    """Simple threadsafe DNS answer cache.

    @ivar data: A dictionary of cached data
    @type data: dict
    @ivar cleaning_interval: The number of seconds between cleanings.  The
    default is 300 (5 minutes).
    @type cleaning_interval: float
    @ivar next_cleaning: The time the cache should next be cleaned (in seconds
    since the epoch.)
    @type next_cleaning: float
    @ivar max_size: The maximum records in the cache.
    @type max_size: int
    @ivar lock: Lock for threadsafe handling this cache.
    @type lock: threading.Lock
    """

    def __init__(self, cleaning_interval=300.0, max_size=10000):
        """Initialize a DNS cache. It has to be called with acquired lock!

        @param cleaning_interval: the number of seconds between periodic
        cleanings.  The default is 300.0
        @type cleaning_interval: float.
        @param max_size: The maximum records in the cache.
        @type max_size: int
        """

        self.data = {}
        self.cleaning_interval = cleaning_interval
        self.next_cleaning = time.time() + self.cleaning_interval
        self.max_size = max_size
        self.lock = threading.Lock()

    def maybe_clean(self):
        """Clean the cache if it's time to do so."""

        now = time.time()
        if self.next_cleaning <= now or len(self.data) > self.max_size:
            keys_to_delete = []
            for (k, v) in self.data.iteritems():
                if v.expiration <= now:
                    keys_to_delete.append(k)
            for k in keys_to_delete:
                del self.data[k]
            if len(self.data) > self.max_size:
                # remove randomly 1/10 of keys
                keys_in_cache = self.data.keys()
                keys_to_delete = []
                for i in range(0, self.max_size / 10 - 1):
                    keys_to_delete.append(keys_in_cache[i*10+random.randint(0,9)])
                for k in keys_to_delete:
                    del self.data[k]
            now = time.time()
            self.next_cleaning = now + self.cleaning_interval

    def get(self, key):
        """Get the answer associated with I{key}.  Returns None if
        no answer is cached for the key.
        @param key: the key
        @type key: (dns.name.Name, int, int) tuple whose values are the
        query name, rdtype, and rdclass.
        @rtype: dns.resolver.Answer object or None
        """

        v = None
        self.lock.acquire()
        try:
            # self.maybe_clean()
            v = self.data.get(key)
        finally:
            self.lock.release()
        if v is None or v.expiration <= time.time():
            return None
        return v

    def put(self, key, value):
        """Associate key and value in the cache.
        @param key: the key
        @type key: (dns.name.Name, int, int) tuple whose values are the
        query name, rdtype, and rdclass.
        @param value: The answer being cached
        @type value: dns.resolver.Answer object
        """

        self.lock.acquire()
        try:
            self.maybe_clean()
            self.data[key] = value
        finally:
            self.lock.release()

    def flush(self, key=None):
        """Flush the cache.

        If I{key} is specified, only that item is flushed.  Otherwise
        the entire cache is flushed.

        @param key: the key to flush
        @type key: (dns.name.Name, int, int) tuple or None
        """

        self.lock.acquire()
        try:
            if not key is None:
                if self.data.has_key(key):
                    del self.data[key]
            else:
                self.data = {}
                self.next_cleaning = time.time() + self.cleaning_interval
        finally:
            self.lock.release()


# DNS query parameters
_dnsResolvers = {}
_dnsCache = Cache(30*60, 10000)
_dnsMaxRetry = 3
_dnsLifetime = 2
_dnsTimeout = 0.75


class DNSCacheError(dns.exception.DNSException):
    """Base exception class for check modules."""
    def __init__(self, args = ""):
        dns.exception.DNSException.__init__(self, args)


def getResolver(lifetime, timeout):
    resolver = _dnsResolvers.get((lifetime, timeout))
    if resolver == None:
        resolver = dns.resolver.Resolver()
        resolver.search = []
        resolver.lifetime = lifetime
        resolver.timeout = timeout
        resolver.cache = _dnsCache
        _dnsResolvers[(lifetime, timeout)] = resolver
    return resolver


def getIpForName(domain, ipv6 = True):
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
            try:
                resolver = getResolver(lifetime, timeout)
                answer = resolver.query(domain, qtype)
                for rdata in answer:
                    ips.append(rdata.address)
                break
            except dns.exception.Timeout:
                logging.getLogger().debug("DNS timeout (%s, %s), try #%s, query: %s [%s]" %
                        (lifetime, timeout, _dnsMaxRetry - dnsretry,
                         domain, qtype))
                lifetime *= 2
                timeout *= 2
            except dns.exception.DNSException:
                # no results or DNS problem
                break
            dnsretry -= 1

        if dnsretry == 0 and len(ips) == 0:
            raise DNSCacheError("DNS error getting IP for domain name: %s" % domain)

    return ips


def getNameForIp(ip):
    """Return domain name for the IP using reverse record resolution."""

    ips = []
    dnsretry = _dnsMaxRetry
    lifetime = _dnsLifetime
    timeout = _dnsTimeout

    ipaddr = ip.split('.')
    ipaddr.reverse()
    ipaddr = '.'.join(ipaddr) + '.in-addr.arpa'

    dnsretry = _dnsMaxRetry
    while dnsretry > 0:
        dnsretry -= 1
        try:
            resolver = getResolver(lifetime, timeout)
            answer = resolver.query(ipaddr, 'PTR')
            for rdata in answer:
                ips.append(rdata.target.to_text(True))
            break
        except dns.exception.Timeout:
            logging.getLogger().debug("DNS timeout (%s, %s), try #%s, query: %s [PTR]" %
                        (lifetime, timeout, _dnsMaxRetry - dnsretry, ipaddr))
            lifetime *= 2
            timeout *= 2
        except dns.exception.DNSException:
            # no results or DNS problem
            break

    if dnsretry == 0 and len(ips) == 0:
        raise DNSCacheError("DNS error getting domain name for IP: %s" % ip)

    return ips


def __cidr(ip, n):
    return ~(0xFFFFFFFFL >> n) & 0xFFFFFFFFL & struct.unpack("!L", socket.inet_aton(ip))[0]


def removeLocal(ips):
    ipsLocal = []
    ip0 = __cidr('0.0.0.0', 8)
    ip10 = __cidr('10.0.0.0', 8)
    ip127 = __cidr('127.0.0.0', 8)
    ip169 = __cidr('169.254.0.0', 16)
    ip172 = __cidr('172.16.0.0', 12)
    ip192 = __cidr('192.168.0.0', 16)
    ip1922 = __cidr('192.0.2.0', 24)
    ip19218 = __cidr('192.18.0.0', 15)
    ip224 = __cidr('224.0.0.0', 4)
    ip240 = __cidr('240.0.0.0', 5)
    ip248 = __cidr('248.0.0.0', 5)
    for ip in ips:
        # localhost
        if ip in [ '255.255.255.255', '127.0.0.1', '0.0.0.0', '::0', '::1' ]: continue
        if ip.find(':') == -1:
            # ipv4 private addresses
            if __cidr(ip, 8) == ip0: continue
            if __cidr(ip, 8) == ip10: continue
            if __cidr(ip, 8) == ip127: continue
            if __cidr(ip, 16) == ip169: continue
            if __cidr(ip, 12) == ip172: continue
            if __cidr(ip, 16) == ip192: continue
            if __cidr(ip, 24) == ip1922: continue
            if __cidr(ip, 15) == ip19218: continue
            if __cidr(ip, 4) == ip224: continue
            if __cidr(ip, 5) == ip240: continue
            if __cidr(ip, 5) == ip248: continue
        else:
            # NOTE: ipv6 private addresses
            pass
        ipsLocal.append(ip)
    return ipsLocal


def getDomainMailhosts(domain, ipv6=True, local=True):
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
            resolver = getResolver(lifetime, timeout)
            answer = resolver.query(domain, 'MX')
            fqdnPref = {}
            for rdata in answer:
                if not fqdnPref.has_key(rdata.preference):
                    fqdnPref[rdata.preference] = []
                fqdnPref[rdata.preference].append(rdata.exchange.to_text(True))
            fqdnPrefKeys = fqdnPref.keys()
            fqdnPrefKeys.sort()
            for key in fqdnPrefKeys:
                for mailhost in fqdnPref[key]:
                    for ip in getIpForName(mailhost, ipv6):
                        ips.append(ip)
            break
        except dns.exception.Timeout:
            logging.getLogger().debug("DNS timeout (%s, %s), try #%s, query: %s [%s]" %
                        (lifetime, timeout, _dnsMaxRetry - dnsretry, domain, 'MX'))
            lifetime *= 2
            timeout *= 2
        except dns.resolver.NoAnswer:
            # search for MX failed, try A (AAAA) record
            for ip in getIpForName(domain, ipv6):
                ips.append(ip)
            break
        except dns.exception.DNSException:
            # no results or DNS problem
            break

    if dnsretry == 0 and len(ips) == 0:
        raise DNSCacheError("DNS error getting mailhost for domain name: %s" % domain)

    # remove invalid IP from the list of mailhost
    if not local:
        return removeLocal(ips)
    return ips



if __name__ == "__main__":
    print "Module tests:"
    import sys
    import twisted.python.log
    twisted.python.log.startLogging(sys.stdout)

    print "##### DNS #####"
    print ">>>>> %s" % getIpForName.__name__
    for domain in [ "fjfi.cvut.cz", "ns.fjfi.cvut.cz",
                    "bimbod.fjfi.cvut.cz", "nmsd.fjfi.cvut.cz",
                    "unknown.fjfi.cvut.cz", "sh.cvut.cz",
                    "nightmare.sh.cvut.cz" ]:
        print ">>> %s" % domain
        print getIpForName(domain)
    print
    print ">>>>> %s" % getNameForIp.__name__
    for ip in [ "147.32.8.9", "147.32.9.20" ]:
        print ">>> %s" % ip
        print getNameForIp(ip)
    print
    print ">>>>> %s" % getDomainMailhosts.__name__
    for domain in [ "fjfi.cvut.cz", "ns.fjfi.cvut.cz",
                    "bimbod.fjfi.cvut.cz", "nmsd.fjfi.cvut.cz",
                    "unknown.fjfi.cvut.cz", "sh.cvut.cz",
                    "nightmare.sh.cvut.cz" ]:
        print ">>> %s" % domain
        print getDomainMailhosts(domain)

    print ">>>>> %s" % __cidr.__name__
    ip10 = __cidr('10.0.0.0', 8)
    ip172 = __cidr('172.16.0.0', 12)
    ip192 = __cidr('192.168.0.0', 16)
    if __cidr('9.255.255.255', 8) == ip10: print "__cidr('9.255.255.255', 8) == ip10"
    if __cidr('10.0.0.0', 8) == ip10: print "__cidr('10.0.0.0', 8) == ip10"
    if __cidr('10.255.255.255', 8) == ip10: print "__cidr('10.255.255.255', 8) == ip10"
    if __cidr('11.0.0.0', 8) == ip10: print "__cidr('11.0.0.0', 8) == ip10"
    if __cidr('147.32.8.9', 8) == ip10: print "__cidr('147.32.8.9', 8) == ip10"
    if __cidr('172.15.255.255', 12) == ip172: print "__cidr('172.15.255.255', 12) == ip172"
    if __cidr('172.16.0.0', 12) == ip172: print "__cidr('172.16.0.0', 12) == ip172"
    if __cidr('172.31.255.255', 12) == ip172: print "__cidr('172.31.255.255', 12) == ip172"
    if __cidr('172.32.0.0', 12) == ip172: print "__cidr('172.32.0.0', 12) == ip172"
    if __cidr('147.32.8.9', 12) == ip172: print "__cidr('147.32.8.9', 12) == ip172"
    if __cidr('192.167.255.255', 16) == ip192: print "__cidr('192.167.255.255', 16) == ip192"
    if __cidr('192.168.0.0', 16) == ip192: print "__cidr('192.168.0.0', 16) == ip192"
    if __cidr('192.168.255.255', 16) == ip192: print "__cidr('192.168.255.255', 16) == ip192"
    if __cidr('192.169.0.0', 16) == ip192: print "__cidr('192.169.0.0', 16) == ip192"
    if __cidr('147.32.8.9', 16) == ip192: print "__cidr('147.32.8.9', 16) == ip192"
