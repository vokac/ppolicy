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
import dns.resolver
import dns.exception


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
                logging.log(logging.DEBUG, "DNS timeout (%s, %s), try #%s, query: %s [%s]" %
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
            logging.log(logging.DEBUG, "DNS timeout (%s, %s), try #%s, query: %s [%s]" %
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


if __name__ == "__main__":
    print "Module tests:"
    import sys
    import twisted.python.log
    twisted.python.log.startLogging(sys.stdout)

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
