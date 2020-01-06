# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2020 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Corrélateur de Vigilo.
"""

from zope.interface import implements
from twisted.plugin import IPlugin
from twisted.application import service

from vigilo.connector import options as base_options

class CorrelatorServiceMaker(object):
    """
    Creates a service that wraps everything the correlator needs.
    """
    implements(service.IServiceMaker, IPlugin)
    tapname = "vigilo-correlator"
    description = "Vigilo correlator"
    options = base_options.make_options('vigilo.correlator')

    def makeService(self, options):
        from vigilo.correlator import makeService
        return makeService(options)

correlator = CorrelatorServiceMaker()
