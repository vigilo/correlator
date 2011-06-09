# -*- coding: utf-8 -*-

from twisted.internet import defer
from twisted.internet.error import ProcessTerminated

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

from vigilo.correlator.registry import get_registry
from vigilo.correlator.actors import rule_runner

LOGGER = get_logger(__name__)
_ = translate(__name__)

class Executor(object):
    """
    Construit un arbre d'exécution à base de L{Deferred}s,
    en suivant la hiérarchie des règles de corrélation.
    """

    def __init__(self, dispatcher):
        self.__dispatcher = dispatcher

    def build_execution_tree(self):
        d = defer.Deferred()
        cache = {}

        rules_graph = get_registry().rules.rules_graph
        subdeferreds = [
            self.__build_sub_execution_tree(cache, d, rules_graph, r)
            for r in rules_graph.nodes_iter()
            if not rules_graph.in_degree(r)
        ]
        # La corrélation sur l'alerte n'échoue que si TOUTES les règles
        # de corrélation ont échoué. Elle réussit lorsque TOUTES les règles
        # ont été exécutées.
        end = defer.DeferredList(
            subdeferreds,
            fireOnOneCallback=0,
            fireOnOneErrback=0,
        )
        return (d, end)

    def __build_sub_execution_tree(self, cache, trigger, rules_graph, rule):
        if cache.has_key(rule):
            return cache[rule]

        dependencies = [
            self.__build_sub_execution_tree(cache, trigger, rules_graph, r[1])
            for r in rules_graph.out_edges_iter(rule)
        ]

        if not dependencies:
            dependencies = [trigger]

        def rule_failure(failure, rule_name):
            if failure.check(ProcessTerminated):
                LOGGER.warning(_('Rule %(rule_name)s timed out'), {
                    'rule_name': rule_name
                })
            return failure

        # L'exécution de la règle échoue si au moins une de ses dépendances
        # n'a pas pu être exécutée. À l'inverse, elle n'est exécutée que
        # lorsque TOUTES ses dépendances ont été exécutées.
        dl = defer.DeferredList(
            dependencies,
            fireOnOneCallback=0,
            fireOnOneErrback=1,
        )
        dl.addCallback(self.__do_work, rule)
        dl.addErrback(rule_failure, rule)
        cache[rule] = dl
        return dl

    def __do_work(self, result, rule_name):
        # result est une liste de tuples (1) de tuples (2) :
        # - le tuple (1) est composé d'un booléen indiquant
        #   si le deferred s'est exécuté (toujours True ici
        #   car fireOnOneCallback vaut 0).
        # - le tuple (2) contient l'identifiant XMPP et le XML.
        idxmpp, xml = result[0][1]

        d = defer.Deferred()

        def cb(result, idxmpp, xml):
            d.callback((idxmpp, xml))

        def eb(failure, rule_name, *args):
            d.errback(failure)

        work = self.__dispatcher.doWork(rule_runner.RuleCommand,
            rule_name=rule_name, idxmpp=idxmpp, xml=xml)
        work.addCallback(cb, idxmpp, xml)
        work.addErrback(eb, rule_name)
        return d

