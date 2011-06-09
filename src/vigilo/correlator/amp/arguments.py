# -*- coding: utf-8 -*-
from twisted.protocols import amp
import pkg_resources

class Function(amp.Argument):
    def fromString(self, inString):
        ep = pkg_resources.EntryPoint.parse("foo = %s" % inString)
        return ep.load(False)

    def toString(self, inObject):
        return "%s:%s" % (inObject.__module__, inObject.__name__)

