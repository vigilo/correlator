# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Tests portant sur les plugins du corrélateur.
"""

from vigilo.corr.pluginmanager import load_plugin
from vigilo.corr.registry import get_registry

def test_plugin_loading():
    """Chargement des plugins du corrélateur"""
    load_plugin('vigilo.corr.rules.test')
    assert get_registry().rules.lookup('TestRule').name == 'TestRule'

