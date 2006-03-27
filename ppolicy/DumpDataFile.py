#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Module whitch dump check data into the file
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import time
import logging
from Base import Base, ParamError


__version__ = "$Revision$"


class DumpDataFile(Base):
    """Dump data from incomming request into the file. These informations
    can be used to improve debugging of other modules or to gather
    statistical data for further analysis. This module should be safe to
    use in sense its check method doesn't raise any exception.

    Module arguments (see output of getParams method):
    fileName

    Check returns:
        this module always return 0 (undefined result)

    Examples:
        # definition for module for saving request info in file
        define('dumpfile1', 'DumpDataFile', fileName="/var/spool/ppolicy/dump.dat")
    """

    PARAMS = { 'fileName': ('file where to dump data from requests', None),
               'cachePositive': (None, 0),
               'cacheNegative': (None, 0),
               }


    def start(self):
        fileName = self.getParam('fileName')
        if fileName == None:
            raise ParamError("undefined fileName")
        self.file = open(fileName, "a")


    def stop(self):
        self.file.close()


    def check(self, data):
        try:
            self.file.write("date=%s\n" % time.time())
            for k,v in data.items():
                self.file.write("%s=%s\n" % (k, v))
            self.file.write("\n")
        except Exception, e:
            fileName = self.getParam('fileName')
            logging.getLogger().warn("error saving request data into \"%s\" (%s), trying to reopen" % (fileName, e))
            try:
                self.file = open(self.getParam('fileName'), "a")
            except Exception, e:
                logging.getLogger().warn("error reopening \"%s\": %s" % (fileName, e))

        return 0, "%s always return undefined" % self.getId()
