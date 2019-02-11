# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2019 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Tests portant sur les plugins du corrélateur.
"""

# pylint: disable-msg=C0111,W0212,R0904,W0201
# - C0111: Missing docstring
# - W0212: Access to a protected member of a client class
# - R0904: Too many public methods
# - W0201: Attribute defined outside __init__

from __future__ import print_function
import unittest
from vigilo.correlator.test.helpers import settings

from vigilo.correlator.registry import get_registry
from vigilo.correlator.rule import Rule


class TestRuleWithNoDependencies(Rule):
    """Module d'exemple pour les règles de corrélation."""
    pass

class TestRuleWithDependency(Rule):
    depends = ["TestRuleWithNoDependencies", ]

class TestRuleWithCyclicDependency1(Rule):
    depends = ["TestRuleWithCyclicDependency2"]

class TestRuleWithCyclicDependency2(Rule):
    depends = ["TestRuleWithCyclicDependency1"]

class TestRule1(Rule):
    pass

class TestRule2(Rule):
    pass


class TestRuleLoading(unittest.TestCase):
    """Teste l'enregistrement des règles de corrélation."""

    def tearDown(self):
        registry = get_registry()
        registry.rules.clear()
        settings.reset()
        settings.load_file('settings_tests.ini')

    def test_rules_loading(self):
        """Chargement des règles de corrélation dans le désordre."""
        registry = get_registry()
        # On charge volontairement la règle ayant une dépendance
        # avant sa dépendance, pour vérifier que le corrélateur est
        # capable de gérer le chargement dans n'importe quel ordre.
        rules = [
            TestRuleWithDependency,
            TestRuleWithNoDependencies,
        ]

        for rule in rules:
            registry.rules.register(rule())
        # Validation des dépendances.
        registry.check_dependencies()

        # On vérifie que toutes les règles demandées
        # ont bien pu être chargées.
        for rule in rules:
            self.assertEqual(
                registry.rules.lookup(rule.__name__).name,
                rule.__name__
            )

    def test_missing_rule_dependency(self):
        """Échec du chargement à cause d'une dépendance manquante."""
        settings.reset()
        get_registry().rules.register(TestRuleWithDependency())
        self.assertRaises(RuntimeError, get_registry().check_dependencies)

    def test_cyclic_dependencies(self):
        """Échec du chargement à cause d'une dépendance circulaire."""
        settings.reset()
        # La 1è règle dépend de la 2nde et vice-versa.
        get_registry().rules.register(TestRuleWithCyclicDependency1())
        self.assertRaises(RuntimeError, get_registry().rules.register,
                          TestRuleWithCyclicDependency2())

    def test_rule_confkey(self):
        """
        La clé de configuration de la règle peut être donné au constructeur
        """
        r = TestRule1(confkey="testname")
        self.assertEqual(r.confkey, "testname")

    def test_rule_dependencies(self):
        """Les dépendances de la règle peuvent être données au constructeur"""
        r = TestRule1(["TestRule2"])
        self.assertEqual(r.depends, ["TestRule2", ])
        r = TestRule1(depends=["TestRule2"])
        self.assertEqual(r.depends, ["TestRule2", ])

    def test_rule_dependencies_nolist(self):
        """Les dépendences doivent être spécifiées sous forme de liste"""
        self.assertRaises(TypeError, TestRule1, depends="TestRule2")
        class TestWrongDeps(Rule):
            depends = "chaine au lieu d'une liste"
        self.assertRaises(TypeError, TestWrongDeps)

    def test_rules_loading_twice(self):
        """Une même règle ne peut pas être chargée deux fois"""
        registry = get_registry()
        rules = [ TestRule1, TestRule1 ]
        for rule in rules:
            registry.rules.register(rule())
        self.assertEqual(len(registry.rules), 1)

    def test_rules_load_from_settings(self):
        """
        Les règles doivent pouvoir être chargées depuis une section [rules] de la conf
        """
        settings["rules"] = {
            "rule1": "%s:%s" % (self.__module__, TestRule1.__name__),
            "rule2": "%s:%s" % (self.__module__, TestRule2.__name__),
        }
        registry = get_registry()
        registry._load_from_settings()
        print(registry.rules.keys())
        self.assertEqual(len(registry.rules), 2)
        self.assertEqual(registry.rules.keys(), ["TestRule2", "TestRule1"])

    def test_rules_load_from_settings_twice(self):
        """
        Une même règle configurée dans settings.ini ne peut être chargée deux fois
        """
        settings["rules"] = {
            "nodeps1": "%s:%s" % (self.__module__, TestRule1.__name__),
            "nodeps2": "%s:%s" % (self.__module__, TestRule1.__name__),
        }
        registry = get_registry()
        registry._load_from_settings()
        print(registry.rules.keys())
        self.assertEqual(len(registry.rules), 1)
