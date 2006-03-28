"""Modular Postfix policy server running with Twisted

Modular Python Postfix Policy Server is tool for extending Postfix
checking capabilities. It uses Postfix access policy delegation
(http://www.postfix.org/SMTPD_POLICY_README.html) to check incomming
SMTP request and accept or reject it according provided data. It can
reduce mailserver load with rejecting incorrect mail during SMTP
connection. It was made with stress to hight reliability and performance
by providing multilevel caching of required data and results.
"""

from distutils.core import setup

doclines = __doc__.split("\n")

setup(
    name            = "ppolicy",
    version         = '2.0.1',
    author          = "Petr Vokac",
    author_email    = "vokac@kmlinux.fjfi.cvut.cz",
    url             = "http://kmlinux.fjfi.cvut.cz/~vokac/activities/ppolicy",
    license         = "GPL",
    platforms       = [ "any" ],
    packages        = [ "ppolicy", "ppolicy.tools" ],
    scripts         = [],
    description = doclines[0],
    long_description = "\n".join(doclines[2:]),
    )
