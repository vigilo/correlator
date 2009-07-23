# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

import runpy
import sys
# Import from io if we target 2.6
from cStringIO import StringIO

from vigilo.common.conf import settings, settings_raw

from nose.tools import assert_raises

def test_layering():
    # Not a good test since settings_raw is private
    for key in settings:
        assert settings_raw[key] == settings[key]

def test_cmdline():
    # Normally called from the command line, this is just for test coverage
    # See the memcached runit service for command-line use.
    oldout, sys.stdout = sys.stdout, StringIO()
    try:
        sys.argv[1:] = ['--get', 'MEMCACHE_CONN_HOST', ]
        runpy.run_module('vigilo.common.conf',
                run_name='__main__', alter_sys=True)
        assert sys.stdout.getvalue() == settings['MEMCACHE_CONN_HOST'] + '\n'
        sys.stdout.seek(0)
        sys.stdout.truncate()

        sys.argv[1:] = []
        runpy.run_module('vigilo.common.conf',
                run_name='__main__', alter_sys=True)
        assert sys.stdout.getvalue() == ''
        sys.stdout.seek(0)
        sys.stdout.truncate()

    finally:
        sys.stdout = oldout

def test_wellformed():
    settings_raw['foo'] = 'bar'
    assert_raises(KeyError, lambda: settings['foo'])

