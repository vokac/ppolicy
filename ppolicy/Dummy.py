#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Dummy module skeleton for creating new modules
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
from Base import Base


__version__ = "$Revision$"


class Dummy(Base):
    """Dummy module skeleton for creating new modules

    Module arguments (see output of getParams method):
    test1, test2

    Check arguments:
        data ... all input data in dict

    Check returns:
        1 .... ok 
        0 .... undefined (default for this module)
        -1 ... failed

    Examples:
        # make instance of dummy module
        modules['dummy1'] = ( 'Dummy', {} )
        # make instance of dummy module with parameters
        modules['dummy2'] = ( 'Dummy', { 'test1': 1, 'test2': "def" } )
    """

    PARAMS = { 'test1': ('test parameter 1', None),
               'test2': ('test parameter 2', 'abc'),
               'cachePositive': (None, 60*15), # define new default value
               'cacheUnknown': (None, 60*15),  # define new default value
               'cacheNegative': (None, 60*15), # define new default value
               }


    def start(self):
        """Called when changing state to 'started'. Right now it is called
        only when you start ppolicy daemon (but in future it can be called
        e.g. during reloading configuration files).
        
        You can check here e.g. module parameters (test1, test2, ...)
        if values defined in ppolicy.conf doesn't contain wrong values."""
        pass


    def stop(self):
        """Called when changing state to 'stopped'. As for start this is
        called only during exit of ppolicy daemon.
        
        You can cleanly release resources used by this module (e.g. close
        opened file hanles, network connections, ...)."""
        pass


    def hashArg(self, data, *args, **keywords):
        """Compute hash from data which is then used as index
        to the result cache. Changing this function in subclasses
        and using only required fields for computing hash can
        improve cache usage and performance.
        arguments:
            data -- input data
            args -- array of arguments defined in ppolicy.conf
            keywords -- dict of arguments defined in ppolicy.conf
        example:
            If your check method use only sender address than the result
            is only dependend on this one parameter (and not on recipient,
            client_address, ...). So for best cache performance you should
            return value that depends only on sender address:

            return hash(data.get('sender', ''))

            If you return 0 it means that check method result will not
            be cached.
        """
        return 0


    def check(self, data, *args, **keywords):
        """check request data againts policy and returns tuple of status
        code and optional info. The meaning of status codes is folloving:
            < 0 check failed
            = 0 check uknown (e.g. required resource not available)
            > 0 check succeded
        parameters:
            data -- input data
            args -- array of arguments defined in ppolicy.conf
            keywords -- dict of arguments defined in ppolicy.conf
        """
        ## example of communication with DB
        # dbPool = self.factory.getdbPool()
        ##
        # d = dbPool.runOperation("SQL QUERY ? ?", (sqlData1, sqlData2))
        # d.addErrback(lambda x: logging.getLogger().error("db query error: " % str(x)))
        ##
        # d = dbPool.runQuery("SELECT * FROM `something`)
        # d.addCallback(lambda x: for r in x: logging.getLogger().info("row: %s" % str(r)))
        # d.addErrback(lambda x: logging.getLogger().error("db query error: " % str(x)))
        ##
        # conn = dbPool.connect()
        # cursor = conn.cursor()
        # cursor.execute()
        # cursor.close()
        # dbPool.disconnect(conn)

        return 0, 'dummy'
