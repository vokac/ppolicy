"""Modular Postfix policy server running with Twisted

Modular Postfix policy server is tool for extending postfix checking
capabilities and can reduce mailserver load rejecting icorrect mail
during SMTP connection. It was made with stress to hight reliability
and performance by providing multilevel caching of required data and
results. Because it has modular design it can be easily extended by
custom modules (only one method has to be implemented and everything
else is handled automatically). By default it provide SPF checking,
domain mailhost checking, sender/recipient verification, ... It also
provide configuration mechanism to make logical AND, OR, NOT and
IFwith results of each module.
"""

from distutils.core import setup

doclines = __doc__.split("\n")

setup(
    name            = "ppolicy",
    version         = "1.0",
    author          = "Petr Vokac",
    author_email    = "vokac@kmlinux.fjfi.cvut.cz",
    url             = "http://kmlinux.fjfi.cvut.cz/~vokac/ppolicy",
    license         = "GPL",
    platforms       = [ "any" ],
    packages        = ["ppolicy"],
    scripts         = [],
    description = doclines[0],
    long_description = "\n".join(doclines[2:]),
    )
