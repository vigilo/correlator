# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Aliases for dependencies.
"""

__all__ = ( 'mp', 'etree', 'event', )

if False: # Not swappable at this point
    # Drawbacks: no logging helpers, exceptions are easily missed.
    # Incompatibilities: not pep-8 compliant (isAlive instead of is_alive)
    # pypi: processing
    import processing as mp
else:
    # the original pyprocessing (pypi: processing), incorporated into
    # the python standard libary since 2.6, then backported
    # Extra features: logging helpers (have to be used explicitly)
    # Regressions from pyprocessing: http://bugs.python.org/issue5331
    # pypi: multiprocessing
    import multiprocessing as mp
# If multiprocessing doesn't work out, we could try something more
# barebones: launching interpreter processes from twisted, and bringing
# http://code.google.com/p/twisted-parallels/ up to scratch.
# We would still get pools.
# We would lose forking (a shame, but twisted lacks api support and
# some reactors weren't fork-safe as of recently), and
# queues (which are fickle but can be made to work).

if True: # Schema validation
    import lxml.etree as etree
else:
    import xml.etree.ElementTree as etree

# pypi: rel
import rel
rel.override()

import event

