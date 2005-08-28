#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Param functions
# def paramFunction(string):
#     return [ "str1", "str2", ... ]
#
# Copyright (c) 2005 JAS
#
# Author: Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
#
# $Id$
#
import logging


def funcMailToPostfixLookup(mail, split = True, user = True, userAt = True):
    if mail == None or mail == '':
        return []
    try:
        username, domain = mail.split("@")
        domainParts = domain.split(".")
    except ValueError:
        return []
    if not split:
        if user:
            return [ "%s@%s" % (username, ".".join(domainParts)) ]
        else:
            return [ "%s" % ".".join(domainParts) ]
    retVal = []
    if user:
        retVal.append("%s@%s" % (username, ".".join(domainParts)))
    while len(domainParts) > 0:
        retVal.append("%s" % ".".join(domainParts))
        domainParts.pop(0)
    if userAt:
        retVal.append("%s@" % username)
    return retVal
def funcMailToUserDomain(mail, split = False):
    return funcMailToPostfixLookup(mail, split, True, False)
def funcMailToUserDomainSplit(mail):
    return funcMailToUserDomain(mail, True)
def funcMailToDomain(mail, split = False):
    return funcMailToPostfixLookup(mail, split, False, False)
def funcMailToDomainSplit(mail):
    return funcMailToDomain(mail, True)


def safeSubstitute(text, dict, unknown = 'UNKNOWN'):
    """Replace keywords in text with data from dictionary. If there is
    not matching key in dictionary, use unknown."""
    import re
    retVal = text
    keywords = re.findall("%(\(.*?\))", text)
    replace = []
    for keyword in keywords:
        if not dict.has_key(keyword[1:-1]):
            replace.append(".\(%s\)." % keyword[1:-1])
    for repl in replace:
        retVal = re.sub(repl, unknown, retVal)
    return retVal % dict




if __name__ == "__main__":
    print "Module tests:"
    import sys
    import twisted.python.log
    twisted.python.log.startLogging(sys.stdout)

    print "##### Param functions #####"
