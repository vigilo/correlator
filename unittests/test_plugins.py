# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

from vigilo.corr.registry import get_registry

def test_plugin_loading():
    # Loading of plugins listed in settings['PLUGINS_ENABLED']
    # is done at registry initialisation.
    assert get_registry().rules.lookup('TestRule').name == 'TestRule'


