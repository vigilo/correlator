# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Aliases for dependencies.
"""

__all__ = ( 'mc', 'mp', 'etree', 'event', )


# Tried to find a binding to libmemcached or the memcache protocol
# that supports the cas (check and set) operation.
# Didn't find it, will have to extend.
# Didn't find a cython libmemcached binding either,
# but python-libmemcached is pyrex based.

# pylibmc mimics the python-memcached api, all three are mostly swappable.
if True:
    # mdv: python-memcached
    # pypi: python-memcached
    import memcache as mc
elif False:
    # gcode: python-libmemcached
    import cmemcached as mc
else:
    # pypi: pylibmc
    import pylibmc as mc

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

