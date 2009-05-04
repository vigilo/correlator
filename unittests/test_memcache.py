# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

from vigilo.corr.memcache import connect

def test_memcache():
    mc = connect()
    # from python-memcached docs
    mc.set("some_key", "Some value")
    value = mc.get("some_key")

    mc.set("another_key", 3)
    mc.delete("another_key")

    mc.set("key", "1")
    mc.incr("key")
    mc.decr("key")



