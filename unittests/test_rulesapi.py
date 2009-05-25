# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

import Queue
import random

from . import with_mc

@with_mc
def test_contexts():
    # import it now because we override MEMCACHE_CONN_PORT in setup_mc
    from vigilo.corr.rulesapi import Api
    api = Api(queue=None)
    name = str(random.random())
    ctx, created = api.get_or_create_context(name, treshold=6)
    assert created
    ctx.decr_treshold()
    ai, created = ctx.get_or_create_aggr_id()
    assert created
    ctx, created = api.get_or_create_context(name, treshold=6)
    assert not created
    tresh = ctx.decr_treshold()
    assert tresh == 4
    ai1, created = ctx.get_or_create_aggr_id()
    assert not created
    assert ai == ai1

@with_mc
def test_aggr_buffer():
    from vigilo.corr.rulesapi import Api
    qu = Queue.Queue(0)
    api = Api(queue=qu)
    name = str(random.random())
    ctx, created = api.get_or_create_context(name, treshold=6)
    assert created
    ctx.aggr_buffer_append(423)
    ctx.aggr_buffer_append(523)
    vals = ctx.aggr_buffer_clear()
    assert vals == [ '423', '523', ]
    try:
        vals = ctx.aggr_buffer_clear()
        assert vals == []
    except RuntimeError: # No such buffer. Maybe we shouldn't throw at all.
        pass
    else:
        assert False
    ctx.aggr_buffer_append(423)
    ctx.aggr_buffer_append(523)
    aid = ctx.aggr_buffer_send()
    val = qu.get()
    assert val == "<item xmlns='http://jabber.org/protocol/pubsub'><aggr xmlns='vigilo' id='1'><alert-ref refid='423'/><alert-ref refid='523'/></aggr></item>"
    assert qu.empty()
    ctx.aggr_append(aid, '643')
    val = qu.get()
    assert val == "<item xmlns='http://jabber.org/protocol/pubsub'><aggr xmlns='vigilo' id='1'><alert-ref refid='643'/></aggr></item>"
    assert qu.empty()


