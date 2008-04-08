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
    """P0f module detect sender OS using p0f and its unix socket interface.
    You can use patched version of p0f that requires only sender IP to detect
    OS - it is less reliable but easier to use, because you don't have to
    specify "ip" and "port" parameters). It can be downloaded from
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
        modules['p0f2'] = ( 'P0f', { 'socket': '/tmp/p0f.socket'
                                     'ip': '192.168.0.1', 'port': 1234 } )
    """

    PARAMS = { 'socket': ('p0f socket for sending requests', '/var/run/p0f.socket'),
               'version': ('p0f version', '2.0.8'),
               'ip': ('IP address of destionation server', None),
               'port': ('port address of destionation server', 25),
               'cachePositive': (None, 60*60),
               'cacheUnknown': (None, 60*15),
               'cacheNegative': (None, 60*60),
               }


    def start(self):
        """Called when changing state to 'started'."""
        for attr in [ 'socket', 'version' ]:
            if self.getParam(attr) == None:
                raise ParamError("parameter \"%s\" has to be specified for this module" % attr)

        self.p0f_socket = self.getParam('socket')
        self.p0f_version = self.getParam('version')

        self.reIPv4 = re.compile('^(25[0-5]|2[0-4]\d|[01]?\d?\d)(\.(25[0-5]|2[0-4]\d|[01]?\d?\d)){3}$')


    def hashArg(self, data, *args, **keywords):
        return hash(data.get('client_address'))


    def check(self, data, *args, **keywords):
        client_address = data.get('client_address')

        if self.reIPv4.match(client_address) == None:
            logging.getLogger().info("client address %s doesn't looks like valid IPv4 address" % client_address)
            return -1, None

        if not os.path.exists(self.p0f_socket):
            logging.getLogger().error("p0f socket %s doesn't exist" % self.p0f_socket)
            return -1, None

        try:
            destination_address = self.getParam('ip')
            if self.getParam('ip') == None or self.reIPv4.match(destination_address) == None:
                destination_address = '0.0.0.0'
            destination_port_int = self.getParam('port', 0)
            if self.p0f_version < '2.0.8':
                query = struct.pack("II4s4sHH", 0x0defaced, 0x12345678, socket.inet_aton(client_address), socket.inet_aton(destination_address), 0, destination_port_int)
            else:
                query = struct.pack("IBI4s4sHH", 0x0defaced, 1, 0x12345678, socket.inet_aton(client_address), socket.inet_aton(destination_address), 0, destination_port_int)
        except struct.error, e:
            logging.getLogger().error("error packing query (%s): address %s" % (e, client_address))
            return -1, None

        # FIXME: synchronized
        response = None
        retry = 3
        while retry > 0:
            try:
                logging.getLogger().debug("opening socket: %s" % self.p0f_socket)
                p0f_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                p0f_socket.connect(self.p0f_socket)
                p0f_socket.send(query)
                response = p0f_socket.recv(1024)
                break
            except Exception, e:
                logging.getLogger().warn("query error: %s" % e)
                retry -= 1

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




if __name__ == "__main__":
    import sys
    import socket

    streamHandler = logging.StreamHandler(sys.stderr)
    streamHandler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s](%(module)s:%(lineno)d) %(message)s", "%d %b %H:%M:%S"))
    logging.getLogger().addHandler(streamHandler)
    logging.getLogger().setLevel(logging.DEBUG)

    if len(sys.argv) <= 1:
        print "usage: %s srcIP [dstIP] [dstPort] [socket] [version]" % sys.argv[0]
        print "example:"
        print "  p0f -0 -Q /tmp/p0f"
        print "  python P0f.py 192.168.0.1 192.168.0.2 25 /tmp/p0f 2.0.8"
        sys.exit(1)

    obj = P0f('P0f')

    client_address = sys.argv[1]
    if len(sys.argv) > 2:
        obj.setParam('ip', sys.argv[2])
    if len(sys.argv) > 3:
        obj.setParam('port', int(sys.argv[3]))
    if len(sys.argv) > 4:
        obj.setParam('socket', sys.argv[4])
    if len(sys.argv) > 5:
        obj.setParam('version', sys.argv[5])

    obj.start()
    print obj.check({ 'client_address': client_address })
    print obj.check({ 'client_address': client_address })
    obj.stop()
