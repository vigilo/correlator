# vim: set fileencoding=utf-8 sw=4 ts=4 et :
import atexit
import subprocess
import time

proc = None

def setup():
    global proc
    assert proc is None
    # Note: don't try to spawn runsvdir that way.
    # Runsvdir is useful for delegation, but doesn't do its own locking.
    proc = subprocess.Popen(
            'PYTHONPATH=lib /sbin/runsv ./service/memcached',
            shell=True)
    atexit.register(lambda: proc.wait())
    # wait for runsv. I know I know.
    time.sleep(1)
    # check if memcached is running, runsv can wait up to 7 seconds.
    subprocess.check_call(['/sbin/sv', 'start', './service/memcached', ])

def teardown():
    global proc
    proc.terminate()

