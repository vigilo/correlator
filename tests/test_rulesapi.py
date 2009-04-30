# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from __future__ import absolute_import

import random

from vigilo.corr.rulesapi import API

def test_contexts():
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


