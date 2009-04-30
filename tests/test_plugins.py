# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

from vigilo.corr.pluginmanager import load_plugin

def test_plugin_loading():
    load_plugin('vigilo.corr.rules.test')

