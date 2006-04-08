#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Check if client address is in various DNS blacklists and make sum
# of scores defined in spamassassin config files.
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
from Base import Base, ParamError
from tools import dnsblScore


__version__ = "$Revision$"


class DnsblScore(Base):
    """Check if client address and sender domain is in various DNS
    blacklists and make sum of scores that are defined in spamassassin
    config files. Returned result depends on parameter treshold (this
    module can return -1,0,1 or exact score if treshold is None).

    This module use tools.dnsblScore.score to score mail. By default
    it uses all available checks, but you can specify your custom by
    listing their name in dnsbl parameter. You can list all valid
    names by calling `python tools/dnsblScore.py --list`.

    Module arguments (see output of getParams method):
    dnsbl, treshold

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 (positive) .... score > treshold or positive score
        0 ............... unknown error (e.g. DNS problems)
        -1 (negative) ... score < treshold or negative score

    Examples:
        # return blacklist score for client address
        define('dnsbl1', 'DnsblScore')
        # check if blacklist score for client address exceed defined treshold
        define('dnsbl1', 'DnsblScore', treshold=5)
    """

    PARAMS = { 'dnsbl': ('list of DNS blacklist to use', None),
               'treshold': ('treshold that define whitch score mean this module fail', None),
               }


    def start(self):
        # force to create singleton
        dnsblScore.getInstance()


    def hashArg(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        client_address = data.get('client_address')
        sender = data.get('sender', '')
        return hash("client_address=%s\nsender=%s" % (client_address, sender))


    def check(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        client_address = data.get('client_address')
        sender = data.get('sender', '')
        dnsblName = self.getParam('dnsbl')
        treshold = self.getParam('treshold')

        if sender.find("@") != -1:
            user, domain = sender.split("@", 2)
        else:
            domain = None

        if dnsblName != None:
            score = dnsblScore.score(client_address, domain, dnsblName)
        else:
            score = dnsblScore.score(client_address, domain)

        if treshold == None:
            return score, "%s blacklist score" % client_address
        if score > treshold:
            return 1, "%s blacklist score exceeded treshold" % client_address
        else:
            return -1, "%s blacklist score did not exceeded treshold" % client_address
#            return 0, "error checking %s in %s" % (client_address, dnsblName)
