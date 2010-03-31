# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""Suite de tests pour la classe 'Api"""

import unittest

import random
import threading

from vigilo.models.session import DBSession

from utils import setup_mc, teardown_mc
from utils import setup_db, teardown_db

from vigilo.correlator.context import Context

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
        name = str(random.random())
        ctx = Context(name)
        assert ctx

