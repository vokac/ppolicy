#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# P0f module detect sender OS
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
import socket
import struct
import os, os.path
import re
from Base import Base, ParamError


__version__ = "$Revision$"


class P0f(Base):
    """P0f module detect sender OS using patched version p0f (that require
    only sender IP address to detect OS) and its unix socket interface
    to get data. It can be downloaded from
    http://kmlinux.fjfi.cvut.cz/~vokac/activities/ppolicy/download/p0f

    This module returns tuple with information described in p0f-query.h
    p0f_response structure. Most important for our purposes are
    retEx[3] ... detected OS
    retEx[4] ... details about detected OS (e.g. version)
    retEx[5] ... distance of sender
    retEx[12] .. uptime (not reliable)

    Module arguments (see output of getParams method):
    socket

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... success (p0f response structure in second parameter)
        0 .... undefined (no data)
        -1 ... failed (error getting data from p0f)

    Examples:
        # make instance of p0f module
        modules['p0f1'] = ( 'P0f', {} )
        # make instance of p0f module with different socket path
        modules['p0f2'] = ( 'P0f', { 'socket': '/tmp/p0f.socket' } )
    """

    PARAMS = { 'socket': ('p0f socket for sending requests', '/var/run/p0f.socket'),
               'version': ('p0f version', '2.0.8'),
               'dst_ad': ('destination ip', ''),
               'dst_port': ('destination port', 0),
               'cachePositive': (None, 60*60),
               'cacheUnknown': (None, 60*15),
               'cacheNegative': (None, 60*60),
               }


    def start(self):
        """Called when changing state to 'started'."""
        for attr in [ 'socket', 'version' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        self.p0f_socket = None

        self.reIPv4 = re.compile('^(25[0-5]|2[0-4]\d|[01]?\d?\d)(\.(25[0-5]|2[0-4]\d|[01]?\d?\d)){3}$')
        self.reIPv6 = re.compile('^((?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|((?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4})*)?)::((?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4})*)?)|((?:[0-9A-Fa-f]{1,4}:){6,6})(25[0-5]|2[0-4]\d|[0-1]?\d?\d)(\.(25[0-5]|2[0-4]\d|[0-1]?\d?\d)){3}|((?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4})*)?)::((?:[0-9A-Fa-f]{1,4}:)*)(25[0-5]|2[0-4]\d|[0-1]?\d?\d)(\.(25[0-5]|2[0-4]\d|[0-1]?\d?\d)){3})$')


    def stop(self):
        """Called when changing state to 'stopped'."""
        if self.p0f_socket != None:
            self.p0f_socket.close()
            self.p0f_socket = None


    def hashArg(self, data, *args, **keywords):
        return hash(data.get('client_address'))


    def check(self, data, *args, **keywords):
        client_address = data.get('client_address')

        if self.reIPv4.match(client_address) == None:
            logging.getLogger().info("client address %s doesn't looks like valid IPv4 address" % client_address)
            return -1, None

        p0f_socket_path = self.getParam('socket')
        if not os.path.exists(p0f_socket_path):
            logging.getLogger().error("p0f socket %s doesn't exist" % p0f_socket_path)
            return -1, None
        
        try:
            client_address_int = struct.unpack('!L',socket.inet_aton(client_address))[0]
            if self.getParam('dst_ad') != None:
                destination_addresss = self.getParam('dst_ad')
                if self.reIPv4.match(destination_addresss) != None:
                    destination_addresss_int = struct.unpack('!L',socket.inet_aton(destination_addresss))[0]
                else:
                    destination_addresss_int = 0
            else:
                destination_addresss_int = 0
            if self.getParam('dst_port') != None:
                destination_port_int = self.getParam('dst_port')
            else:
                destination_port_int = 0
            if self.getParam('version') < '2.0.8':
                query = struct.pack("I I", 0x0defaced, 0x12345678)
            else:
                query = struct.pack("I B I", 0x0defaced, 1, 0x12345678)
            query += struct.pack(">I I", client_address_int, destination_addresss_int)
            query += struct.pack("H H", 0, destination_port_int)
        except struct.error, e:
            logging.getLogger().error("error packing query (%s): address %s" % (e, client_address))
            return -1, None

        # FIXME: synchronized
        response = None
        retry = 3
        while retry > 0:
            try:
##                if self.p0f_socket == None:
##                    logging.getLogger().debug("opening socket: %s" % p0f_socket_path)
##                    self.p0f_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
##                    self.p0f_socket.connect(p0f_socket_path)
##                self.p0f_socket.send(query)
##                response = self.p0f_socket.recv(1024)
                logging.getLogger().debug("opening socket: %s" % p0f_socket_path)
                p0f_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                p0f_socket.connect(p0f_socket_path)
                p0f_socket.send(query)
                response = p0f_socket.recv(1024)
                break
            except Exception, e:
                logging.getLogger().warn("query error: %s" % e)
##                if self.p0f_socket != None:
##                    self.p0f_socket.close()
##                self.p0f_socket = None
                retry -= 1
##         try:
##             logging.getLogger().debug("opening socket: %s" % p0f_socket_path)
##             p0f_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
##             p0f_socket.connect(p0f_socket_path)
##             p0f_socket.send(query)
##             p0f_socket.close()
##             response = p0f_socket.recv(1024)
##         except Exception, e:
##             logging.getLogger().warn("query error: %s" % e)

        if response == None:
            logging.getLogger().debug("no response for: %s" % client_address)
            return -1, None

        # (magic, id, type, genre, detail, dist, link, tos, fw, nat, real, score, mflags, uptime)
        try:
            retEx = []
            for i in struct.unpack("I I B 20s 40s b 30s 30s B B B h H i", response):
                if type(i) == str and i.find('\x00') != -1:
                    retEx.append(i[:i.find('\x00')])
                else:
                    retEx.append(i)
        except struct.error, e:
            logging.getLogger().error("error unpacking response (%s): %s" % (e, str(response)))
            return -1, None

        if (retEx[0] != 0x0defaced):
            logging.getLogger().info("magic is not correct: %s" % retEx[0])
            return -1, None

        if (retEx[2] != 0):
            if retEx[2] == 1:
                logging.getLogger().info("error type returned: Query malformed")
                return -1, None
            elif retEx[2] == 2:
                logging.getLogger().debug("error type returned: No match for src-dst data")
                return 0, None
            else:
                logging.getLogger().debug("error type returned: %s" % retEx[2])
                return -1, None

        return 1, retEx
