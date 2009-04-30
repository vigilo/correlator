# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

from vigilo.corr.libs import mp

def run_child():
    import sys
    assert 'tabnanny' in sys.modules

def test_modules():
    import tabnanny
    p = mp.Process(target=run_child)
    p.start()
    p.join()

