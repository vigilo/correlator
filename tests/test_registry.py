# -*- coding: utf-8 -*-
"""Tests pour le registre des règles de corrélation."""
import unittest

from vigilo.corr.registry import get_registry
from vigilo.corr.rule import Rule

def rule_maker(name, deps):
    """
    Crée une règle dynamiquement.

    @param name: Nom (unique) de la nouvelle règle.
    @type name: C{str}
    @param deps: Liste des noms des dépendances de la nouvelle règle.
    @type deps: C{list} of C{str}
    @return: Une nouvelle règle (qui ne fait rien), nommée L{name}.
    @rtype: C{type}
    """

    def __init(obj, d):
        """Servira de __init__ pour la classe créée dynamiquement."""
        super(obj.__class__, obj).__init__(d)

    def __process(obj, *args, **kwargs):
        """Fonction de traitement dans la classe créée dynamiquement."""
        pass

    classdict = {
        '__init__': __init,
        'process': __process,
    }
    cls = type.__new__(type, name, (Rule, ), classdict)
    obj = cls(deps)
    return obj


class TestRegistry(unittest.TestCase):
    """Teste le registre des règles de corrélation."""

    def setUp(self):
        """Préparatifs pour le test."""
        self.registry = get_registry()
        self.registry.rules.clear()

        # On génère quelques règles indépendantes
        # et on les enregistre pour les tests.
        self.r11 = rule_maker('r11', [])
        self.registry.rules.register(self.r11)

        self.r21 = rule_maker('r21', ['r11'])
        self.registry.rules.register(self.r21)
        self.r22 = rule_maker('r22', ['r11'])
        self.registry.rules.register(self.r22)

        self.r31 = rule_maker('r31', ['r21'])
        self.registry.rules.register(self.r31)

        self.r41 = rule_maker('r41', ['r31', 'r22'])
        self.registry.rules.register(self.r41)

        self.r51 = rule_maker('r51', ['r41'])
        self.registry.rules.register(self.r51)

        self.r61 = rule_maker('r61', ['r51'])
        self.registry.rules.register(self.r61)

    def assertValues(self, expected, value, msg=None):
        """
        Teste si les valeurs de 2 tableaux sont identiques,
        en ignorant l'ordre d'apparition des éléments.
        """
        if msg:
            self.assertEqual(len(expected), len(value), msg=msg)
            for i in expected:
                self.assertTrue(i in value, msg=msg)
        else:
            self.assertEqual(len(expected), len(value), repr(value))
            for i in expected:
                self.assertTrue(i in value, repr(value))

    def test_rule_steps(self):
        """Vérifie les règles exécutées à chaque étape"""
        rules_tree = self.registry.rules.step_rules
        rules = rules_tree.rules

        self.assertValues(['r11'], rules.next())
        self.assertValues(['r21', 'r22'], rules.next())
        self.assertValues(['r31'], rules.next())
        self.assertValues(['r41'], rules.next())
        self.assertValues(['r51'], rules.next())

        # On simule un échec de la règle r51 et son élimination du pool.
        # Comme r51 a échoué, r61 NE DOIT PAS apparaître ensuite.
        rules_tree.remove_rule('r51')

        # On vérifie qu'il n'y a plus d'autres règles à exécuter.
        self.assertRaises(StopIteration, rules.next)

