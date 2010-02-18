# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Plugin loading and registration.
"""

import runpy

def load_plugin(mod_name, registry=None):
    """
    Load a plugin from a dot-separated module name.

    This is used at registry initialization to load plugins
    listed in the PLUGINS_ENABLED setting,
    and can be used to explicitly load extra plugins after that.

    Do not load a plugin twice.

    Do not call for a package module,
    because of http://bugs.python.org/issue2751
    Weird messages with python 2.5 and absolute_import,
    clear refusal to execute a package in 2.6 and 3.0.
    In that case, append .__init__ to the package name instead.
    """

    if registry is None:
        from .registry import get_registry
        registry = get_registry()
    runpy.run_module(mod_name)['register'](registry)

