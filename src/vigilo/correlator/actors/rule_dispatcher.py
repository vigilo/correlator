# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2015 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Ce module fournit les mécanismes permettant de traiter les messages
provenant du bus, afin que ceux-ci soient corrélés.

Il met également à disposition un moyen pour les règles de corrélation
d'émettre de nouveaux messages XML à destination du bus (par exemple,
des commandes pour Nagios).
"""

import time, itertools
from datetime import datetime

try:
    import json
except ImportError:
    import simplejson as json

import transaction
from sqlalchemy import exc

from twisted.internet import defer, reactor, error
from twisted.python import threadpool

from vigilo.common.logging import get_logger, get_error_message
from vigilo.common.gettext import translate

from vigilo.models.tables import SupItem, Version

from vigilo.connector.options import parseSubscriptions, parsePublications
from vigilo.connector.handlers import MessageHandler
from vigilo.correlator.correvent import CorrEventBuilder
from vigilo.correlator.publish_messages import MessagePublisher

from vigilo.correlator.actors import executor
from vigilo.correlator.context import Context
from vigilo.correlator.handle_ticket import handle_ticket
from vigilo.correlator.db_insertion import insert_event, insert_state, \
        insert_hls_history, OldStateReceived, NoProblemException
from vigilo.correlator import registry

LOGGER = get_logger(__name__)
_ = translate(__name__)


class RuleDispatcher(MessageHandler):
    """
    Cette classe corrèle les messages reçus depuis le bus
    et envoie ensuite les résultats sur le bus.
    """

    _context_factory = Context


    def __init__(self, database, nagios_hls_host, timeout, min_runner,
                 max_runner, max_idle, instance):
        self.instance = instance
        super(RuleDispatcher, self).__init__()
        self.tree_end = None
        self._database = database
        self.nagios_hls_host = nagios_hls_host
        self.timeout = timeout

        # @TODO: #875: réimplémenter le timeout avec des threads.
        self.rrp = threadpool.ThreadPool(min_runner, max_runner, "Rule runners")
        self._executor = executor.Executor(self)
        self.bus_publisher = None
        self.correvent_builder = None
        self._tmp_correl_time = None
        self._correl_times = []


    def check_database_connectivity(self):
        def _db_request():
            """
            Requête SQL élémentaire afin de vérifier
            la connectivité avec la base de données.
            """
            return Version.by_object_name('vigilo.models')

        # Évite de boucler sur une erreur si la base de données
        # n'est pas disponible au lancement du corrélateur.
        d = self._database.run(_db_request)

        def no_database(failure):
            """
            Méthode appelée lorsque la connexion avec la base de données
            ne peut être établie.
            """
            LOGGER.error(_("Unable to contact the database: %s"),
                get_error_message(failure.getErrorMessage()))
            try:
                reactor.stop()
            except error.ReactorNotRunning:
                pass
        d.addErrback(no_database)


    def startService(self):
        LOGGER.debug("Starting rule runners")
        return self.rrp.start()

    def stopService(self):
        return self.rrp.stop()


    def _putResultInDeferred(self, deferred, f, args, kwargs):
        d = defer.maybeDeferred(f, *args, **kwargs)
        d.addCallbacks(
            lambda res: reactor.callFromThread(deferred.callback, res),
            lambda fail: reactor.callFromThread(deferred.errback, fail),
        )


    def doWork(self, f, *args, **kwargs):
        """
        Délègue le travail aux threads dédiés à la corrélation.
        """
        d = defer.Deferred()
        self.rrp.callInThread(self._putResultInDeferred, d, f, args, kwargs)
        return d


    def write(self, msg):
        content = json.loads(msg.content.body)
        msgid = msg.fields[1]
        if msgid is None:
            LOGGER.error(_("Received invalid item ID (None)"))
            return defer.succeed(None)
        content["id"] = "%s.%s" % (msgid, self.instance)
        d = defer.maybeDeferred(self.processMessage, content)
        d.addCallbacks(self.processingSucceeded, self.processingFailed,
                       callbackArgs=(msg, ))
        if self.keepProducing:
            d.addBoth(lambda _x: self.producer.resumeProducing())
        return d


    def _processException(self, failure):
        if not failure.check(KeyboardInterrupt):
            LOGGER.error(_('Unexpected error: %s'),
                get_error_message(failure.getErrorMessage()))
        return failure


    def processMessage(self, msg):
        res = defer.maybeDeferred(self._processMessage, msg)
        res.addErrback(self._processException)
        return res


    def _processMessage(self, msg):

        # Ordre de calcul de l'état d'un service de haut niveau.
        if msg["type"] == "computation-order":
            return self._computation_order(msg)

        # Extraction des informations du message
        info_dictionary = self.extract_information(msg)

        # S'il s'agit d'un message concernant un ticket d'incident :
        if msg["type"] == "ticket":
            d = self._do_in_transaction(
                _("Error while modifying the ticket"),
                [exc.OperationalError],
                handle_ticket, info_dictionary,
            )
            return d

        # Sinon, s'il ne s'agit pas d'un message d'événement (c'est-à-dire
        # un message d'alerte de changement d'état), on ne le traite pas.
        if msg["type"] != "event":
            return defer.succeed(None)

        idsupitem = self._do_in_transaction(
            _("Error while retrieving supervised item ID"),
            [exc.OperationalError],
            SupItem.get_supitem,
            info_dictionary['host'],
            info_dictionary['service']
        )
        idsupitem.addCallback(self._finalizeInfo, info_dictionary)
        return idsupitem


    def _computation_order(self, msg):
        if 'HighLevelServiceDepsRule' not in \
            registry.get_registry().rules.keys():
            LOGGER.warning(_("The rule 'vigilo.correlator_enterprise."
                            "rules.hls_deps:HighLevelServiceDepsRule' "
                            "must be loaded for computation orders to "
                            "be handled properly."))
            return defer.succeed(None)

        rule = registry.get_registry().rules.lookup('HighLevelServiceDepsRule')

        def eb(failure):
            if failure.check(defer.TimeoutError, error.ConnectionDone):
                LOGGER.info(_("The connection to memcached timed out. "
                                "The message will be handled once more."))
                return failure # Provoque le retraitement du message.
            LOGGER.warning(failure.getErrorMessage())
            return None # on passe au suivant

        ctx = self._context_factory(msg["id"])

        hls_names = set()
        for servicename in msg["hls"]: # TODO: adapter l'envoi
            if not isinstance(servicename, unicode):
                servicename = servicename.decode('utf-8')
            hls_names.add(servicename)

        hls_names = list(hls_names)
        d = ctx.set('impacted_hls', hls_names)
        d.addCallback(lambda _dummy: ctx.set('hostname', None))
        d.addCallback(lambda _dummy: ctx.set('servicename', None))
        d.addErrback(eb)
        d.addCallback(lambda _dummy: \
            self.doWork(
                rule.compute_hls_states,
                self, msg["id"],
                None, None,
                hls_names
            )
        )
        return d


    def extract_information(self, msg):
        """
        Extrait les informations d'un message
        """

        info_dictionary = {"host": None,
                           "service": None,
                           "state": None,
                           "message": None,
                           "impacted_HLS": None,
                           "ticket_id": None,
                           "acknowledgement_status": None,}
        for key, value in msg.iteritems():
            if value is not None:
                info_dictionary[key] = unicode(value)

        if "timestamp" in msg:
            try:
                info_dictionary["timestamp"] = datetime.fromtimestamp(
                        int(msg["timestamp"]))
            except ValueError:
                info_dictionary["timestamp"] = datetime.now()

        if info_dictionary["host"] == self.nagios_hls_host:
            info_dictionary["host"] = None

        # Le message vaut None lorsqu'on force l'envoi d'une notification
        # sur un service qui se trouve dans l'état PENDING côté Nagios (#1085).
        if info_dictionary["message"] is None:
            info_dictionary["message"] = u''

        return info_dictionary


    def _finalizeInfo(self, idsupitem, info_dictionary):
        # Ajoute l'identifiant du SupItem aux informations.
        info_dictionary['idsupitem'] = idsupitem

        # On initialise le contexte et on y insère
        # les informations sur l'alerte traitée.
        ctx = self._context_factory(info_dictionary["id"])

        attrs = {
            'hostname': 'host',
            'servicename': 'service',
            'statename': 'state',
            'timestamp': 'timestamp',
            'idsupitem': 'idsupitem',
        }

        d = defer.Deferred()

        def prepare_ctx(_res, ctx_name, value):
            return ctx.set(ctx_name, value)
        def eb(failure):
            if failure.check(defer.TimeoutError, error.ConnectionDone):
                LOGGER.info(_("The connection to memcached timed out. "
                                "The message will be handled once more."))
                return failure # Provoque le retraitement du message.
            LOGGER.warning(failure.getErrorMessage())
            return None # on passe au suivant

        for ctx_name, info_name in attrs.iteritems():
            d.addCallback(prepare_ctx, ctx_name, info_dictionary[info_name])

        # Dans l'ordre :
        # - On enregistre l'état correspondant à l'événement.
        # - On insère une entrée d'historique pour l'événement.
        # - On réalise la corrélation.
        d.addCallback(self._insert_state, info_dictionary)
        d.addCallback(self._insert_history, info_dictionary, ctx)
        d.addErrback(eb)
        d.callback(None)
        return d


    def _insert_state(self, _result, info_dictionary):
        LOGGER.debug(_('Inserting state'))
        d = self._do_in_transaction(
            _("Error while saving state"),
            [exc.OperationalError],
            insert_state, info_dictionary
        )
        return d


    def _insert_history(self, previous_state, info_dictionary, ctx):
        if isinstance(previous_state, OldStateReceived):
            LOGGER.debug("Ignoring old state for host %(host)s and service "
                         "%(srv)s (current is %(cur)s, received %(recv)s)"
                         % {"host": info_dictionary["host"],
                            "srv": info_dictionary["service"],
                            "cur": previous_state.current,
                            "recv": previous_state.received,
                            }
                         )
            return # on arrête le processus ici
        # On insère le message dans la BDD, sauf s'il concerne un HLS.
        if not info_dictionary["host"]:
            LOGGER.debug(_('Inserting an entry in the HLS history'))
            d = self._do_in_transaction(
                _("Error while adding an entry in the HLS history"),
                [exc.OperationalError],
                insert_hls_history, info_dictionary
            )
        else:
            LOGGER.debug(_('Inserting an entry in the history'))
            d = self._do_in_transaction(
                _("Error while adding an entry in the history"),
                [exc.OperationalError],
                insert_event, info_dictionary
            )

        d.addCallback(self._do_correl, previous_state, info_dictionary, ctx)
        d.addCallback(self._commit)

        def no_problem(fail):
            """
            Court-circuite l'exécution des règles de corrélation
            lorsqu'aucun événement corrélé n'existe en base de données
            et qu'on reçoit un message indiquant un état nominal (OK/UP).
            """
            fail.trap(NoProblemException)
        d.addErrback(no_problem)
        return d

    def _commit(self, res):
        transaction.commit()
        return res

    def _do_correl(self, raw_event_id, previous_state, info_dictionary, ctx):
        LOGGER.debug(_('Actual correlation'))
        if raw_event_id is None:
            LOGGER.error(_('Received inconsitent raw_event_id for event: %s') % info_dictionary)
            return defer.succeed(None)

        d = defer.Deferred()
        d.addCallback(lambda _result: ctx.set('payload', info_dictionary))
        d.addCallback(lambda _result: ctx.set('previous_state', previous_state))

        if raw_event_id:
            d.addCallback(lambda _result: ctx.set('raw_event_id', raw_event_id))

        def start_correl(_ignored, defs):
            tree_start, self.tree_end = defs

            def send(res):
                sr = self._send_result(res, info_dictionary)
                sr.addErrback(self._send_result_eb, info_dictionary)
                return sr

            # Gère les erreurs détectées à la fin du processus de corrélation,
            # ou émet l'alerte corrélée s'il n'y a pas eu de problème.
            self.tree_end.addCallbacks(
                send,
                self._correlation_eb,
                errbackArgs=[info_dictionary],
            )

            # On lance le processus de corrélation.
            self._tmp_correl_time = time.time()
            tree_start.callback(info_dictionary["id"])
            return self.tree_end
        d.addCallback(start_correl, self._executor.build_execution_tree())

        def end(result):
            duration = time.time() - self._tmp_correl_time
            self._correl_times.append(duration)
            LOGGER.debug(_('Correlation process ended (%.4fs)'), duration)
            return result
        d.addCallback(end)
        d.callback(None)
        return d


    def _send_result(self, _result, info_dictionary):
        """
        Traite le résultat de l'exécution de TOUTES les règles
        de corrélation.

        @param _result: Résultat de la corrélation (transmis automatiquement par
            Twisted, vaut toujours None chez nous).
        @type  _result: C{None}
        @param info_dictionary: Informations extraites du message XML.
        @param info_dictionary: C{dict}
        """
        LOGGER.debug(_('Handling correlation results'))

        d = defer.Deferred()

        # Pour les services de haut niveau, on s'arrête ici,
        # on NE DOIT PAS générer d'événement corrélé.
        if info_dictionary["host"] == self.nagios_hls_host:
            d.callback(None)
            return d

        def cb(_result, *args, **kwargs):
            assert self.correvent_builder is not None
            return self.correvent_builder.make_correvent(*args, **kwargs)
        def eb(failure):
            try:
                error_message = unicode(failure)
            except UnicodeDecodeError:
                error_message = unicode(str(failure), 'utf-8', 'replace')

            LOGGER.info(_(
                'Error while saving the correlated event (%s). '
                'The message will be handled once more.'),
                error_message
            )
            return failure
        d.addCallback(lambda res: self._database.run(
            transaction.begin, transaction=False))
        d.addCallback(cb, info_dictionary)
        d.addCallback(lambda res: self._database.run(
            transaction.commit, transaction=False))
        d.addErrback(eb)

        d.callback(None)
        return d


    def _correlation_eb(self, failure, msg):
        """
        Cette méthode est appelée lorsque la corrélation échoue.
        Elle se contente d'afficher un message d'erreur.

        @param failure: L'erreur responsable de l'échec.
        @type  failure: C{Failure}
        @param msg: Message concerné.
        @type  msg: C{dict}
        @return: L'erreur reponsable de l'échec.
        @rtype: C{Failure}
        """
        LOGGER.error(_('Correlation failed for '
                        'message #%(id)s (%(payload)s)'), {
            'id': msg["id"],
            'payload': msg,
        })
        return failure


    def _send_result_eb(self, failure, msg):
        """
        Cette méthode est appelée lorsque la corrélation
        s'est bien déroulée mais que le traitement des résultats
        a échoué.
        Elle se contente d'afficher un message d'erreur.

        @param failure: L'erreur responsable de l'échec.
        @type  failure: C{Failure}
        @param msg: Message concerné.
        @type  msg: C{dict}
        """
        LOGGER.error(_('Unable to store correlated alert for '
                        'message #%(id)s (%(payload)s) : %(error)s'), {
            'id': msg["id"],
            'payload': msg,
            'error': str(failure).decode('utf-8'),
        })


    def _do_in_transaction(self, error_desc, ex, func, *args, **kwargs):
        """
        Encapsule une opération nécessitant d'accéder à la base de données
        dans une transaction.

        En cas d'erreur, le message XML est réinséré dans la file d'attente du
        corrélateur pour pouvoir être à nouveau traité ultérieurement.

        @param error_desc: Un message d'erreur décrivant la nature de
            l'opération et qui sera affiché si l'opération échoue.
        @type  error_desc: C{unicode}
        @param ex: Le type d'exceptions à capturer. Il peut également s'agir
            d'une liste de types d'exceptions.
        @type  ex: C{Exception} or C{list} of C{Exception}
        @param func: La fonction à appeler pour exécuter l'opération.
        @type  func: C{callable}
        @note: Des paramètres additionnels (nommés ou non) peuvent être
            passés à cette fonction. Ils seront transmis tel quel à C{func}
            lors de son appel.
        """
        if not isinstance(ex, list):
            ex = [ex]

        def eb(failure):
            if failure.check(*ex):
                LOGGER.info(_('%s. The message will be handled once more.'),
                    error_desc)
                return failure
            if failure.check(NoProblemException):
                raise NoProblemException()
            LOGGER.warning(failure.getErrorMessage())
            return None

        d = self._database.run(func, *args, **kwargs)
        d.addErrback(eb)
        return d


    def getStats(self):
        """Récupère des métriques de fonctionnement du corrélateur"""
        def add_publisher_stats(stats):
            if self.bus_publisher is None:
                return stats
            p_stats_d = self.bus_publisher.getStats()
            def update(p_stats):
                stats["sent"] = p_stats["sent"]
                return stats
            p_stats_d.addCallback(update)
            return p_stats_d
        def add_exec_stats(stats):
            # En cas d'absence de messages durant la dernière minute,
            # le temps d'exécution de chacune des règles est de 0.0 seconde.
            rule_stats = dict(zip(
                ["rule-%s" % rule for rule in
                 registry.get_registry().rules.keys()],
                itertools.repeat(0.0)
            ))
            # On met à jour le dictionnaire avec les vraies stats d'exécution.
            rule_stats.update(self._executor.getStats())
            stats.update(rule_stats)
            if self._correl_times:
                stats["rule-total"] = round(sum(self._correl_times) /
                                            len(self._correl_times), 5)
                self._correl_times = []
            else:
                stats["rule-total"] = 0.0
            return stats
        d = super(RuleDispatcher, self).getStats()
        d.addCallback(add_publisher_stats)
        d.addCallback(add_exec_stats)
        return d


    def registerCallback(self, fn, idnt):
        self.tree_end.addCallback(fn, self, self._database, idnt)


    def sendItem(self, msg):
        """Envoi des résultats sur le bus"""
        if self.bus_publisher is not None:
            return self.bus_publisher.write(msg)



def ruledispatcher_factory(settings, database, client):
    nagios_hls_host = settings['correlator']['nagios_hls_host']

    timeout = settings['correlator'].as_int('rules_timeout')
    if timeout <= 0:
        timeout = None

    min_runner = settings['correlator'].as_int('min_rule_runners')
    max_runner = settings['correlator'].as_int('max_rule_runners')

    # Identifiant (supposé) unique de l'instance.
    instance = settings['instance']

    try:
        max_idle = settings['correlator'].as_int('rule_runners_max_idle')
    except KeyError:
        max_idle = 20

    msg_handler = RuleDispatcher(database, nagios_hls_host, timeout,
                                 min_runner, max_runner, max_idle, instance)
    msg_handler.check_database_connectivity()
    msg_handler.setClient(client)
    subs = parseSubscriptions(settings)
    queue = settings["bus"]["queue"]
    queue_message_ttl = int(settings['bus'].get('queue_messages_ttl', 0))
    msg_handler.subscribe(queue, queue_message_ttl, subs)

    # Expéditeur de messages
    publications = parsePublications(settings.get('publications', {}).copy())
    publisher = MessagePublisher(nagios_hls_host, publications)
    publisher.setClient(client)
    msg_handler.bus_publisher = publisher

    # Créateur de correvents
    correvent_builder = CorrEventBuilder(publisher, database)
    msg_handler.correvent_builder = correvent_builder

    return msg_handler
