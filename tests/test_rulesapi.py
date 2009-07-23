# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

import Queue
import random
import threading

from nose.tools import assert_raises

from vigilo.corr.libs import mp

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
    vals = ctx.aggr_buffer_clear()
    assert vals == []
    ctx.aggr_buffer_append(423)
    ctx.aggr_buffer_append(523)
    aid = ctx.aggr_buffer_send()
    val = qu.get()
    assert val == u"<item xmlns='http://jabber.org/protocol/pubsub'><aggr xmlns='http://www.projet-vigilo.org/xmlns/aggr1' id='1'><alert-ref refid='423'/><alert-ref refid='523'/></aggr></item>"
    assert qu.empty()
    ctx.aggr_append(aid, '643')
    val = qu.get()
    assert val == u"<item xmlns='http://jabber.org/protocol/pubsub'><aggr xmlns='http://www.projet-vigilo.org/xmlns/aggr1' id='1'><alert-ref refid='643'/></aggr></item>"
    assert qu.empty()

@with_mc
def test_strictness():
    from vigilo.corr.rulesapi import Api
    api = Api(queue=None)
    assert_raises(TypeError, lambda: api.get_or_create_context(u'unicode'))

def run_concurrently(parallelism, func, *args, **kwargs):
    if False:
        # The GIL means this doesn't work
        tasks = [
                threading.Thread(target=func, args=args, kwargs=kwargs)
                for j in xrange(parallelism)]
    else:
        # coverage/tracing doesn't work in subprocesses
        tasks = [
                mp.Process(target=func, args=args, kwargs=kwargs)
                for j in xrange(parallelism)]
    for t in tasks:
        t.start()
    for t in tasks:
        t.join(.1)

@with_mc
def test_concurrency():
    # Check the logs to see if we really exercised concurrency.
    # Apparently we didn't manage.
    from vigilo.corr.rulesapi import Api

    def gocai(name):
        # Don't share libmemcached connections across threads or processes
        api = Api(queue=None)
        ctx, created = api.get_or_create_context(name, treshold=6)
        ctx.get_or_create_aggr_id()
    def aba(name):
        api = Api(queue=None)
        ctx, created = api.get_or_create_context(name, treshold=6)
        ctx.aggr_buffer_append(4)

    for i in xrange(16):
        name = str(random.random())
        run_concurrently(8, gocai, name)
        run_concurrently(8, aba, name)


