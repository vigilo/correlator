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

def square(x):
    return x*x

def test_pool():
    pool = mp.Pool(processes=4)
    pool.map(square, [0, 1])

def test_pool_from_process():
    # Pools created in a process block when map is used,
    # from the same process.
    # Flaky. pyprocessing isn't subject to this.
    # http://bugs.python.org/issue5331
    p = mp.Process(target=test_pool)
    p.start()
    p.join()

