# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Suite de tests pour la classe 'Api"""

import unittest

import random
import threading

from vigilo.models.configure import DBSession

from utils import setup_mc, teardown_mc
from utils import setup_db, teardown_db
from vigilo.corr.libs import mp

class TestApiFunctions(unittest.TestCase): 
    """Tests portant sur le contexte et l'API des règles de corrélation."""
    
    def setUp(self):
        """Initialisation d'un contexte préalable à chacun des tests."""
        setup_mc()
        setup_db()
        
    def tearDown(self):
        """Nettoyage du contexte à la fin de chaque test."""
        DBSession.flush()
        DBSession.expunge_all()
        teardown_db()
        teardown_mc()

    def test_contexts(self):
        """Création d'un contexte associé à un nom quelconque"""
        # import it now because we override MEMCACHE_CONN_PORT in setup_mc
        from vigilo.corr.rulesapi import Api
        api = Api(queue=None)
        name = str(random.random())
        ctx = api.get_or_create_context(name)
        assert ctx

    def run_concurrently(self, parallelism, func, *args, **kwargs):
        """Exécute plusieurs processus (légers ou lourds) en parallèle."""
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

    def test_concurrency(self):
        """Comportement du corrélateur en cas de concurrence"""

        # Check the logs to see if we really exercised concurrency.
        # Apparently we didn't manage.
        from vigilo.corr.rulesapi import Api
    
        def create_context(name):
            """Crée un contexte portant le nom passé en paramètre."""
            # Don't share libmemcached connections across threads or processes
            api = Api(queue=None)
            ctx = api.get_or_create_context(name)

        for i in xrange(16):
            name = str(random.random())
            self.run_concurrently(8, create_context, name)


