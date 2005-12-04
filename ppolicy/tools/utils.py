#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Other functions
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging


def safeSubstitute(text, dict, unknown = 'UNKNOWN'):
    """Replace keywords in text with data from dictionary. If there is
    not matching key in dictionary, use unknown."""
    import re
    retVal = text
    keywords = re.findall("(%\(.*?\))", text)
    for keyword in keywords:
        if dict.has_key(keyword[2:-1]):
            retVal = retVal.replace(keyword, dict[keyword[2:-1]])
        else:
            retVal = retVal.replace(keyword, 'UNKNOWN')
    return retVal




if __name__ == "__main__":
    print "Module tests:"
    import sys
    import twisted.python.log
    twisted.python.log.startLogging(sys.stdout)

    print "##### Other functions #####"
