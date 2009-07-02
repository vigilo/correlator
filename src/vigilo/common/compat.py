# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

"""
Compatiblity wrappers for pre-2.6 python.

Warning: monkey-patching.
"""

if not hasattr(property, 'setter'):
    class _property(property):
        @property
        def setter(self):
            def decorate(func):
                return property(
                        fget=self.fget,
                        fset=func,
                        fdel=self.fdel,
                        doc=self.__doc__)
            return decorate

    __builtins__['property'] = _property

