# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

import logging
import signal

from vigilo.corr.libs import mp

def run_once(p):
    try:
        p.start()
        p.join(1)
        # pyprocessing / multiprocessing compat
        if hasattr(p, 'is_alive'):
            assert not p.is_alive()
        else:
            assert not p.isAlive()
    finally:
        p.terminate()
        p.join()

def setup():
    # 5 is the 'SUBDEBUG' level.
    mp.log_to_stderr(logging.INFO)

def check_loaded_modules():
    import sys
    assert 'tabnanny' in sys.modules

def test_loaded_modules():
    import tabnanny
    p = mp.Process(target=check_loaded_modules)
    run_once(p)

def square(x):
    return x*x

def test_pool():
    pool = mp.Pool(processes=4)
    pool.map(square, [0, 1, 2])

def test_pool_from_process():
    # FAILS with multiprocessing, but not pyprocessing. Flaky.
    # Pools created in a process block when map is used,
    # from the same process.
    # http://bugs.python.org/issue5331
    p = mp.Process(target=test_pool)
    run_once(p)

global_pool = None
def use_global_pool():
    global global_pool
    pool = global_pool
    pool.map(square, [0, 1, 2])

def test_global_pool():
    # FAILS
    global global_pool
    pool = mp.Pool(processes=4)
    global_pool = pool
    p = mp.Process(target=use_global_pool)
    run_once(p)

def use_passed_pool(pool):
    pool.map(square, [0, 1, 2])

def test_pool_passing():
    # FAILS
    # Blocks, with pyprocessing and multiprocessing both.
    pool = mp.Pool(processes=4)
    p = mp.Process(target=use_passed_pool, args=(pool,))
    run_once(p)

def display_signals(prefix):
    print '%s %s %s' % (prefix, 'SIGINT', signal.getsignal(signal.SIGINT))
    print '%s %s %s' % (prefix, 'SIGTERM', signal.getsignal(signal.SIGTERM))
    print '%s %s %s' % (prefix, 'SIGCHLD', signal.getsignal(signal.SIGCHLD))
    print '%s %s %s' % (prefix, 'SIGPIPE', signal.getsignal(signal.SIGPIPE))

def test_signals():
    display_signals('parent')
    p = mp.Process(target=display_signals, args=('child', ))
    run_once(p)


