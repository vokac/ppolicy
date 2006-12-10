#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# LookupLDAP module for searching records in LDAP
#
# Copyright (c) 2006 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
import ldap
from Base import Base, ParamError


__version__ = "$Revision$"


class LookupLDAP(Base):
    """LookupLDAP module for searching records in LDAP

    Module arguments (see output of getParams method):
    param, uri, base, bind_dn, bind_pass, bind_method, scope, filter, attributes

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... ok, found records for the filter
        0 .... undefined (problem with LDAP query, e.g. failing connection)
        -1 ... failed to find records for the filter

    Examples:
        # recipient ldap lookup in ldap1/2.domain.tld with "mail" filter
        modules['lookup_ldap1'] = ( 'LookupLDAP', { 'param': 'recipient',
                'uri': 'ldap://ldap1.domain.tld ldap://ldap2.domain.tld',
                'base': 'ou=People,dc=domain,dc=tld',
                'filter': '(mail=%m)' } )
        # recipient ldap lookup that returns common name attribute
        modules['lookup_ldap1'] = ( 'LookupLDAP', { 'param': 'recipient',
                'uri': 'ldap://ldap1.domain.tld ldap://ldap2.domain.tld',
                'base': 'ou=People,dc=domain,dc=tld',
                'bind_dn': 'cn=PPolicy User,ou=People,dc=domain,dc=tld',
                'bind_pass': 'secret',
                'scope': ldap.SCOPE_ONELEVEL,
                'filter': '(mail=%m)', 'attributes': 'cn' } )
    """

    PARAMS = { 'param': ('name of parameter in data dictionary', None),
               'uri': ('LDAP server URI', None),
               'base': ('LDAP search base', None),
               'bind_dn': ('LDAP bind DN (None == anonymous bind)', None),
               'bind_pass': ('LDAP bind password', None),
               'bind_method': ('LDAP bind method (only simple is supported)', ldap.AUTH_SIMPLE),
               'scope': ('LDAP search scope', ldap.SCOPE_SUBTREE),
               'filter': ('LDAP filter (%m will be replaced by "param" value', None),
               'attributes': ('attributes returned by LDAP query', None),
               }


    def start(self):
        for attr in [ 'param', 'uri', 'base', 'scope', 'filter' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        uri = self.getParam('uri')
        bind_dn = self.getParam('bind_dn')
        bind_pass = self.getParam('bind_pass')
        bind_method = self.getParam('bind_method')
        logging.getLogger().debug("Trying to connect to the LDAP server: %s" % uri)
        self._ldap = ldap.ldapobject.ReconnectLDAPObject(uri, trace_level=2)
        if bind_dn != None:
            self._ldap.bind_s(bind_dn, bind_pass, bind_method)


    def stop(self):
        self._ldap = None


    def hashArg(self, data, *args, **keywords):
        param = self.getParam('param', None, keywords)
        return hash(data.get(param, ''))


    def check(self, data, *args, **keywords):
        param = self.getParam('param')
        base = self.getParam('base')
        scope = self.getParam('scope')
        fltr = self.getParam('filter')
        attributes = self.getParam('attributes')

        queryFilter = fltr.replace('%m', data.get(param, ''))
        if attributes == None:
            attributes = [ 'dn' ] # fake attribute
        elif type(attributes) == str:
            attributes = [ attributes ]

        retVal = []
        try:
            retVal = self._ldap.search_s(base, scope, queryFilter, attributes)
        except Exception, e:
            return 0, str(e)

        if len(retVal) > 0:
            return 1, retVal
        else:
            return -1, []
