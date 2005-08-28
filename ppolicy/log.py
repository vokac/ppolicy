#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Standard Python logging handler for twisted log.msg()
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging
import twisted.python.log

class TwistedHandler(logging.Handler):
    """ A handler class which sends formatted logging records
    to twisted python logging facitility.
    """

    def __init__(self):
        logging.Handler.__init__(self)

    def emit(self, record):
        msg = self.format(record)
        twisted.python.log.msg(msg)
