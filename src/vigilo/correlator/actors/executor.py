# -*- coding: utf-8 -*-
# Copyright (C) 2011-2020 CS GROUP – France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

import time

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

    La variable d'instance C{_stats} contient les temps d'exécution des règles.
    Elle est de la forme suivante::

        {"NomRegle1": [duree1, duree2, duree3, duree4, ...,
         "NomRegle2": [duree1, duree2, duree3, duree4, ...,
         "NomRegle3": [duree1, duree2, duree3, duree4, ...,
        }

    La fonction L{getStats}() utilise ensuite ces valeurs pour publier des
    moyennes d'exécution donnant lieu à de la métrologie.

    @ivar _stats: statistiques d'exécution, au format ci-dessus
    @type _stats: C{dict}
    @ivar _stats_tmp: stockage temporaire des timestamps d'exécution
    @type _stats_tmp: C{dict}
    """

    def __init__(self, dispatcher):
        self.__dispatcher = dispatcher
        self._stats = {}
        self._stats_tmp = {}
        self._runners = {}
        reg = get_registry()
        for rule_name in reg.rules.keys():
            rule_obj = reg.rules.lookup(rule_name)
            self._runners[rule_name] = \
                rule_runner.RuleRunner(dispatcher, rule_name, rule_obj)

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
            fireOnOneErrback=1,
            consumeErrors=True,
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

        def before_work(result, rule):
            LOGGER.debug('Executing correlation rule "%s"', rule)
            self._stats_tmp[rule] = time.time()
            return result

        def after_work(result, rule):
            time_spent = time.time() - self._stats_tmp[rule]
            LOGGER.debug('Done executing correlation rule "%(rule)s" (%(time).4fs)',
                         {"rule": rule, "time": time_spent})
            self._stats.setdefault(rule, []).append(time_spent)
            return result

        # L'exécution de la règle échoue si au moins une de ses dépendances
        # n'a pas pu être exécutée. À l'inverse, elle n'est exécutée que
        # lorsque TOUTES ses dépendances ont été exécutées.
        dl = defer.DeferredList(
            dependencies,
            fireOnOneCallback=0,
            fireOnOneErrback=1,
        )
        dl.addCallback(before_work, rule)
        dl.addCallback(self.__do_work, rule)
        dl.addErrback(rule_failure, rule)
        dl.addCallback(after_work, rule)
        cache[rule] = dl
        return dl

    def __do_work(self, result, rule_name):
        # result est une liste de tuples (1) de tuples (2) :
        # - le tuple (1) est composé d'un booléen indiquant
        #   si le deferred s'est exécuté (toujours True ici
        #   car fireOnOneCallback vaut 0).
        # - le tuple (2) contient l'identifiant de l'événement.
        msgid = result[0][1]

        d = defer.Deferred()

        def cb(_result, msgid):
            d.callback(msgid)

        def eb(failure):
            d.errback(failure)

        work = self.__dispatcher.doWork(self._runners[rule_name].run, msgid)
        work.addCallback(cb, msgid)
        work.addErrback(eb)
        return d

    def getStats(self):
        prefix = "rule-"
        stats = {}
        for rulename, durations in self._stats.iteritems():
            if not durations:
                continue # pas de messages depuis la dernière fois
            average = sum(durations) / len(durations)
            stats[prefix + rulename] = round(average, 5)
            # et on ré-initialise
            self._stats[rulename] = []
        return stats
