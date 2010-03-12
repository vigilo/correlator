# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Tests portant sur les plugins du corrélateur.
"""
import unittest

from vigilo.correlator.pluginmanager import load_plugin
from vigilo.correlator.registry import get_registry

from vigilo.correlator.rule import Rule

class TestRuleWithNoDependencies(Rule):
    """Module d'exemple pour les règles de corrélation."""

    def __init__(self):
        """Initialisation du module."""
        super(TestRuleWithNoDependencies, self).__init__()

class TestRuleWithDependency(Rule):
    def __init__(self):
        """Initialisation du module."""
        super(TestRuleWithDependency, self).__init__([
            'TestRuleWithNoDependencies',
        ])

class TestRuleLoading(unittest.TestCase):
    """Teste l'enregistrement des règles de corrélation."""

    def test_rules_loading(self):
        """Chargement des règles de corrélation avec dépendances."""
        registry = get_registry()
        rules = [
            TestRuleWithNoDependencies,
            TestRuleWithDependency,
        ]

        for rule in rules:
            registry.rules.register(rule())
            self.assertEquals(registry.rules.lookup(
                rule.__name__).name, rule.__name__)

    def test_check_rule_loading_failure(self):
        """Échec du chargement d'une règle à cause d'une dépendance."""
        self.assertRaises(RuntimeError, get_registry().rules.register,
            TestRuleWithDependency())

