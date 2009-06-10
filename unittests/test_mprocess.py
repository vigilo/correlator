# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

"""

Spy on multiprocessing.pool:worker
This may be the reason for the pool issues.
IOError: [Errno 9] Bad file descriptor


        except (EOFError, IOError):
            import traceback
            debug(traceback.format_exc())
            debug(''.join(traceback.format_stack()))
            debug('worker got EOFError or IOError -- exiting')
            break

When the pool is created, it creates and starts workers, passing them
a few queues. One of them, inqueue, is read by the poolworkers on startup,
in a blocking fashion. The read throws an IOError 9, bad file descriptor,
in a call to socket.recv (via mp.connection.Pipe(duplex=False)).
Changing to duplex=True fixes it.
The queue is an mp.queues.SimpleQueue created by the pool.
The pool isn't a Process on its own, the worker processes are children
of the caller of the pool constructor.

We should fix either the Pipe impl or the Connection impl.


Fixes:
http://bugs.python.org/issue5331
http://bugs.python.org/issue5155
http://bugs.python.org/issue5313

    def _bootstrap(self):
        from multiprocessing import util
        global _current_process

        try:
            self._children = set()
            self._counter = itertools.count(1)
            try:
                #os.close(sys.stdin.fileno())
                sys.stdin.close()
            except (OSError, ValueError):
                pass

"""

import logging
import signal

# Use those for missing libraries or runtime support
from nose.exc import SkipTest
from nose.plugins.attrib import attr

from vigilo.corr.libs import mp

from vigilo.common.logging import get_logger

LOGGER = get_logger(__name__)
# Someone else's problem
# Those are bugs in multiprocessing
SEP = attr('SEP')

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

sync_mgr = None
def setup():
    mp.get_logger().propagate = True
    logging.basicConfig(
            level=logging.DEBUG,
            format='%(levelname)s::%(processName)s::%(name)s::%(message)s')
    global sync_mgr
    sync_mgr = mp.Manager()

def teardown():
    sync_mgr.shutdown()

def check_loaded_modules():
    import sys
    # Evidence that multiprocessing takes advantage of os.fork()
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

@SEP
def test_pool_from_process():
    # FAILS with multiprocessing, but not pyprocessing. Flaky.
    # Pools created in a process block when map is used,
    # from the same process.
    # Pools apparently must be created in the topmost process.
    # We see the workers stopping in the log, just after creation.
    # http://bugs.python.org/issue5331

    p = mp.Process(target=test_pool)
    run_once(p)

global_pool = None
def use_global_pool():
    global global_pool
    pool = global_pool
    pool.map(square, [0, 1, 2])

@SEP
def test_global_pool():
    # FAILS. Pools aren't fork-safe.
    # We don't see the workers stopping in the log.

    global global_pool
    pool = mp.Pool(processes=4)
    global_pool = pool
    p = mp.Process(target=use_global_pool)
    run_once(p)

def use_passed_pool(pool):
    pool.map(square, [0, 1, 2])

@SEP
def test_pool_passing():
    # FAILS. Pools aren't pickle-safe.
    # Blocks, with pyprocessing and multiprocessing both.
    # We don't see the workers stopping in the log.

    pool = mp.Pool(processes=4)
    p = mp.Process(target=use_passed_pool, args=(pool,))
    run_once(p)

def display_signals(prefix):
    LOGGER.info('%s %s %s', prefix, 'SIGINT', signal.getsignal(signal.SIGINT))
    LOGGER.info('%s %s %s', prefix, 'SIGTERM', signal.getsignal(signal.SIGTERM))
    LOGGER.info('%s %s %s', prefix, 'SIGCHLD', signal.getsignal(signal.SIGCHLD))
    LOGGER.info('%s %s %s', prefix, 'SIGPIPE', signal.getsignal(signal.SIGPIPE))

def test_signals():
    display_signals('parent')
    p = mp.Process(target=display_signals, args=('child', ))
    run_once(p)

def use_shared_queue(queue):
    queue.put('alpha')

def test_shared_queue():
    queue = mp.Queue()
    p = mp.Process(target=use_shared_queue, args=(queue, ))
    run_once(p)

global_queue = None
def use_global_queue(arg):
    global_queue.put('alpha')

def test_pool_shared_queue():
    # Use a global (fork-shared), we can't pass a mp.Queue to mp.Pool.map.
    # mp.Queue isn't pickle-safe, and has the decency to throw an exception.
    global global_queue
    global_queue = mp.Queue()
    pool = mp.Pool(2)
    try:
        deferred = pool.map_async(use_global_queue, range(3))
        deferred.wait(timeout=1)
        deferred.get(timeout=1)
        assert deferred.ready() and deferred.successful()
    finally:
        pool.terminate()
        global_queue = None

def test_pool_managed_queue():
    # This is not an mp.Queue, simply a proxied, out of process Queue.Queue
    # Proxies seem pickle-safe.
    queue = sync_mgr.Queue()
    pool = mp.Pool(2)
    deferred = pool.map_async(use_shared_queue, [queue, queue, queue])
    deferred.get(timeout=1)

def use_queue(queue):
    # IOError
    queue.get(timeout=1.)

def create_queue(success_queue):
    queue = mp.Queue()
    sub = mp.Process(target=use_queue, args=(queue,))
    sub.start()
    queue.put('plonk')
    sub.join()
    success = queue.empty()
    success_queue.put(success)

@SEP
def test_deep_queue():
    # http://bugs.python.org/issue5155
    success_queue = sync_mgr.Queue()
    proc = mp.Process(target=create_queue, args=(success_queue,))
    run_once(proc)
    assert success_queue.get_nowait() is True


