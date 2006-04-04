#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# This module store information about requests that use
# trap email address and restrict receiving following messages
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
import time
from Base import Base, ParamError


__version__ = "$Revision$"


class Trap(Base):
    """Trap module catches mail probing random recipient addresses. If in
    defined time fall more than defined amount of mail from one client to
    the trap, all mail from that client will be temporarly blocked.

    Module arguments (see output of getParams method):
    traps, treshold, expire, limit

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... request from client that send many mail touched our mail traps
        0 .... some problem
        -1 ... client is not touched mail traps

    Examples:
        # define trap to block client_address for one hour if we receive
        # one mail with recipient spamtrap1 or spamtrap2
        define('trap1', 'Trap', traps="spamtrap1@domain.com,spamtrap2@domain.com")
    """

    PARAMS = { 'traps': ('comma separated list of trap email addresses', None),
               'treshold': ('how many traps has to be touched before blacklisting (negative value mean fraction 1/x)', -2),
               'expire': ('expiration time for client that send trapped email', 60*60),
               'cachePositive': (None, 0),
               'cacheUnknown': (None, 0),
               'cacheNegative': (None, 0),
               }


    def start(self):
        traps = self.getParam('traps')
        if traps == None:
            raise ParamError('traps has to be specified for this module')
        self.traps = traps.lower().split(",")
        
        treshold = self.getParam('treshold')
        if treshold < 0: treshold = -len(self.traps) / treshold
        if treshold == 0: treshold = 1
        self.treshold = treshold

        self.trap = {}


    def stop(self):
        del(self.trap)


    def hashArg(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        return hash("client_address=%s" % data.get('client_address'))


    def check(self, *args, **keywords):
        data = self.dataArg(0, 'data', {}, *args, **keywords)
        expire = self.getParam('expire')
        sender = data.get('sender')
        recipient = data.get('recipient')
        client_address = data.get('client_address')

        # RFC 2821, section 4.1.1.2
        # empty MAIL FROM: reverse address may be null
        if sender == '':
            return 0, "%s accept empty From address" % self.getId()
        if reclc == 'postmaster' or reclc[:11] == 'postmaster@':
            return 0, "%s accept mail from postmaster" % self.getId()
        
        if recipient in self.traps:
            # add to trap cache
            newTrap = []
            for expire in self.trap.get(client_address, []):
                if expire > time.time():
                    newTrap.append(expire)
            if len(newTrap) > self.treshold:
                newTrap.pop()
            newTrap.insert(0, time.time() + expire)
            self.trap[client_address] = newTrap
            return 0, "%s: do nothing with trapped message" % self.getId()
        else:
            # RFC 2821, section 4.1.1.3
            # see RCTP TO: grammar
            reclc = recipient.lower()
            if reclc == 'postmaster' or reclc[:11] == 'postmaster@':
                return 0, "%s always accept postmaster as recipient" % self.getId()
            
            thisTrap = self.trap.get(client_address, [])
            if len(thisTrap) > 0 and thisTrap[len(thisTrap)-1] < time.time():
                # remove expired
                for i in range(0, len(thisTrap)):
                    if thisTrap[i] < time.time():
                        thisTrap = thisTrap[:i]
                        break
                self.trap[client_address] = thisTrap

            if len(self.trap[client_address]) > self.treshold:
                return 1, "%s blacklisted your client address" % self.getId()

            return -1, "%s did not blacklisted your client address" % self.getId()
