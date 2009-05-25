# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

import runpy
import settings
import sys

# Use io since 2.6
from cStringIO import StringIO

def test_cmdline():
    # Normally called from the command line, this is just for test coverage
    # See the memcached runit service for command-line use.
    oldout, sys.stdout = sys.stdout, StringIO()
    try:
        sys.argv[1:] = ['--get', 'MEMCACHE_CONN_HOST', ]
        runpy.run_module('vigilo.corr.conf',
                run_name='__main__', alter_sys=True)
        assert sys.stdout.getvalue() == settings.MEMCACHE_CONN_HOST + '\n'
    finally:
        sys.stdout = oldout

