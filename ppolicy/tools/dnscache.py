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
import struct
import socket
import dns.resolver
import dns.exception


# DNS query parameters
_dnsResolvers = {}
_dnsCache = dns.resolver.Cache()
_dnsMaxRetry = 3
_dnsLifetime = 3.0
_dnsTimeout = 1.0


class DNSCacheError(dns.exception.DNSException):
    """Base exception class for check modules."""
    def __init__(self, args = ""):
        dns.exception.DNSException.__init__(self, args)


def getResolver(lifetime, timeout):
    resolver = _dnsResolvers.get((lifetime, timeout))
    if resolver == None:
        resolver = dns.resolver.Resolver()
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
                answer = getResolver(lifetime, timeout).query(domain, qtype)
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
            answer = getResolver(lifetime, timeout).query(ipaddr, 'PTR')
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
            answer = getResolver(lifetime, timeout).query(domain, 'MX')
            fqdnPref = {}
            for rdata in answer:
                fqdnPref[rdata.preference] = rdata.exchange.to_text(True)
            fqdnPrefKeys = fqdnPref.keys()
            fqdnPrefKeys.sort()
            for key in fqdnPrefKeys:
                for ip in getIpForName(fqdnPref[key], ipv6):
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
        ipsLocal = []
        ip10 = __cidr('10.0.0.0', 8)
        ip172 = __cidr('172.16.0.0', 12)
        ip192 = __cidr('192.168.0.0', 16)
        for ip in ips:
            # localhost
            if ip in [ '127.0.0.1', '0.0.0.0', '::0', '::1' ]: continue
            if ip.find(':') == -1:
                # ipv4 private addresses
                if __cidr(ip, 8) == ip10: continue
                if __cidr(ip, 12) == ip172: continue
                if __cidr(ip, 16) == ip192: continue
            else:
                # NOTE: ipv6 private addresses
                pass
            ipsLocal.append(ip)
        return ipsLocal
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
