# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Tests portant sur les plugins du corrélateur.
"""

from vigilo.correlator.pluginmanager import load_plugin
from vigilo.correlator.registry import get_registry

def test_plugin_loading():
    """Chargement des plugins du corrélateur"""
    load_plugin('vigilo.correlator.rules.test')
    assert get_registry().rules.lookup('TestRule').name == 'TestRule'

