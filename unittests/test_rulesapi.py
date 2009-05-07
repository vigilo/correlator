# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

import random
from nose import with_setup

from . import setup_mc, teardown_mc

@with_setup(setup_mc, teardown_mc)
def test_contexts():
    # import it now because we override MEMCACHE_CONN_PORT in setup_mc
    from vigilo.corr.rulesapi import API
    name = str(random.random())
    ctx, created = API.get_or_create_context(name, 3)
    assert created
    ctx.decr_treshold()
    ai, created = ctx.get_or_create_aggr_id()
    assert created
    ctx, created = API.get_or_create_context(name, 3)
    assert not created
    tresh = ctx.decr_treshold()
    assert tresh == 1
    ai1, created = ctx.get_or_create_aggr_id()
    assert not created
    assert ai == ai1


