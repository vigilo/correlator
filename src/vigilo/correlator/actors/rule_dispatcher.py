# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Ce module fournit les mécanismes permettant de traiter les messages
provenant du bus XMPP, afin que ceux-ci soient corrélés.

Il met également à disposition un moyen pour les règles de corrélation
d'émettre de nouveaux messages XML à destination du bus (par exemple,
des commandes pour Nagios).
"""

import sys
from datetime import datetime

import transaction
from sqlalchemy.exc import SQLAlchemyError

from twisted.internet import defer, reactor
from twisted.protocols import amp
from ampoule import pool
from wokkel.generic import parseXml
from lxml import etree

from vigilo.common.conf import settings

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

from vigilo.connector.forwarder import PubSubSender
from vigilo.connector import MESSAGEONETOONE

from vigilo.models.session import DBSession

from vigilo.pubsub.xml import namespaced_tag, NS_EVENT, NS_TICKET
from vigilo.correlator.actors import rule_runner, executor
from vigilo.correlator.memcached_connection import MemcachedConnection
from vigilo.correlator.context import Context
from vigilo.correlator.handle_ticket import handle_ticket
from vigilo.correlator.db_insertion import insert_event, insert_state, \
                                            insert_hls_history
from vigilo.correlator.publish_messages import publish_state
from vigilo.correlator.correvent import make_correvent
from vigilo.correlator.amp.correlator import Correlator
from vigilo.correlator.amp.starter import ProcessStarter

LOGGER = get_logger(__name__)
_ = translate(__name__)

def extract_information(payload):
    """
    Extrait les informations d'un message, en le parcourant
    une seule fois afin d'optimiser les performances.
    """

    info_dictionary = {"host": None,
                       "service": None,
                       "state": None,
                       "timestamp": None,
                       "message": None,
                       "impacted_HLS": None,
                       "ticket_id": None,
                       "acknowledgement_status": None,}

    # Récupération du namespace utilisé
    namespace = payload.nsmap[payload.prefix]

    for element in payload.getchildren():
        for tag in info_dictionary.keys():
            if element.tag == namespaced_tag(namespace, tag):
                if not element.text is None:
                    if element.tag == namespaced_tag(namespace, "timestamp"):
                        try:
                            info_dictionary["timestamp"] = \
                                datetime.fromtimestamp(int(element.text))
                        except ValueError:
                            info_dictionary["timestamp"] = datetime.now()
                    else:
                        info_dictionary[tag] = u'' + element.text

    if info_dictionary["host"] == settings['correlator']['nagios_hls_host']:
        info_dictionary["host"] = None

    return info_dictionary

class RuleDispatcher(PubSubSender):
    """
    Cette classe corrèle les messages reçus depuis le bus XMPP
    et envoie ensuite les résultats sur le bus.
    """

    def __init__(self, database):
        super(RuleDispatcher, self).__init__()
        self.max_send_simult = 1
        self.tree_end = None
        self.__database = database

        # Préparation du pool d'exécuteurs de règles.
        timeout = settings['correlator'].as_int('rules_timeout')
        if timeout <= 0:
            timeout = None

        min_runner = settings['correlator'].as_int('min_rule_runners')
        max_runner = settings['correlator'].as_int('max_rule_runners')

        try:
            max_idle = settings['correlator'].as_int('rule_runners_max_idle')
        except KeyError:
            max_idle = 20

        self.rrp = pool.ProcessPool(
            maxIdle=max_idle,
            ampChild=rule_runner.RuleRunner,
            ampParent=Correlator,
            timeout=timeout,
            name='RuleDispatcher',
            min=min_runner,
            max=max_runner,
            ampChildArgs=(sys.argv[0], ),
            starter=ProcessStarter(self, database),
        )
        self.__executor = executor.Executor(self)

    def doWork(self, *args, **kwargs):
        """
        Délègue le travail aux processus dédiés à la corrélation.
        """
        return self.rrp.doWork(*args, **kwargs)

    def itemsReceived(self, event):
        """
        Méthode appelée lorsque des éléments ont été reçus depuis
        le bus XMPP.

        @param event: Événement XMPP reçu.
        @type event: C{twisted.words.xish.domish.Element}
        """
        for item in event.items:
            # Item is a domish.IElement and a domish.Element
            # Serialize as XML before queueing,
            # or we get harmless stderr pollution  × 5 lines:
            # Exception RuntimeError: 'maximum recursion depth exceeded in
            # __subclasscheck__' in <type 'exceptions.AttributeError'> ignored
            #
            # stderr pollution caused by http://bugs.python.org/issue5508
            # and some touchiness on domish attribute access.
            xml = item.toXml()
            if item.name != 'item':
                # The alternative is 'retract', which we silently ignore
                # We receive retractations in FIFO order,
                # ejabberd keeps 10 items before retracting old items.
                LOGGER.debug(_(u'Skipping unrecognized item (%s)'), item.name)
                continue
            self.forwardMessage(xml)

    def processMessage(self, xml):
        try:
            return self._processMessage(xml)
        except KeyboardInterrupt:
            raise
        except:
            LOGGER.exception("Runtime exception")
            raise

    def _processMessage(self, xml):
        """
        Transfère un message XML sérialisé vers la file.

        @param xml: message XML à transférer.
        @type xml: C{str}
        @return: Un objet C{Deferred} correspondant au traitement
            du message par les règles de corrélation ou C{None} si
            le message n'a pas pu être traité (ex: message invalide).
        @rtype: C{twisted.internet.defer.Deferred} ou C{None}
        """
        dom = etree.fromstring(xml)

        # Extraction de l'id XMPP.
        # Note: dom['id'] ne fonctionne pas dans lxml, dommage.
        idxmpp = dom.get('id')
        if idxmpp is None:
            LOGGER.error(_("Received invalid XMPP item ID (None)"))
            return defer.succeed(None)

        # Extraction des informations du message
        info_dictionary = extract_information(dom[0])

        # S'il s'agit d'un message concernant un ticket d'incident :
        if dom[0].tag == namespaced_tag(NS_TICKET, 'ticket'):
            d = self.__do_in_transaction(
                _("Error while modifying ticket"),
                xml, Exception,
                handle_ticket, info_dictionary,
            )
            return d

        # Sinon, s'il ne s'agit pas d'un message d'événement (c'est-à-dire
        # un message d'alerte de changement d'état), on ne le traite pas.
        if dom[0].tag != namespaced_tag(NS_EVENT, 'event'):
            return defer.succeed(None)

        idsupitem = self.__do_in_transaction(
            _("Error while retrieving supervised item ID"),
            xml, SQLAlchemyError,
            SupItem.get_supitem,
            info_dictionary['host'],
            info_dictionary['service']
        )
        idsupitem.addCallback(self.__finalizeInfo,
            idxmpp,
            dom, xml,
            info_dictionary
        )
        return idsupitem

    def __finalizeInfo(self, idsupitem, idxmpp, dom, xml, info_dictionary):
        # Ajoute l'identifiant du SupItem aux informations.
        info_dictionary['idsupitem'] = idsupitem

        # On initialise le contexte et on y insère
        # les informations sur l'alerte traitée.
        ctx = Context(idxmpp, self.__database)

        attrs = {
            'hostname': 'host',
            'servicename': 'service',
            'statename': 'state',
            'timestamp': 'timestamp',
        }

        d = defer.Deferred()

        def prepare_ctx(res, ctx_name, value):
            return ctx.set(ctx_name, value)
        def eb(failure):
            LOGGER.error(_("Error: %s"), str(failure).decode('utf-8'))
            return failure

        for ctx_name, info_name in attrs.iteritems():
            d.addCallback(prepare_ctx, ctx_name, info_dictionary[info_name])
            d.addErrback(eb)

        # Dans l'ordre :
        # - On insère une entrée d'historique pour l'événement.
        # - On enregistre l'état correspondant à l'événement.
        # - On réalise la corrélation.
        d.addCallback(self.__insert_history, info_dictionary, xml)
        d.addCallback(self.__insert_state, info_dictionary, xml)
        d.addCallback(self.__do_correl, info_dictionary, idxmpp, dom, xml, ctx)
        def end(result):
            LOGGER.debug(_('Correlation process ended'))
            return result
        d.addCallback(end)
        d.callback(None)
        return d

    def __insert_history(self, result, info_dictionary, xml):
        # On insère le message dans la BDD, sauf s'il concerne un HLS.
        if not info_dictionary["host"]:
            LOGGER.debug(_('Inserting an entry in the HLS history'))
            d = self.__do_in_transaction(
                _("Error while adding an entry in the HLS history"),
                xml, SQLAlchemyError,
                insert_hls_history, info_dictionary
            )
        else:
            LOGGER.debug(_('Inserting an entry in the history'))
            d = self.__do_in_transaction(
                _("Error while adding an entry in the history"),
                xml, SQLAlchemyError,
                insert_event, info_dictionary
            )
        return d

    def __insert_state(self, raw_event_id, info_dictionary, xml):
        LOGGER.debug(_('Inserting state'))

        def cb(result):
            return result, raw_event_id

        d = self.__do_in_transaction(
            _("Error while saving state"),
            xml, SQLAlchemyError,
            insert_state, info_dictionary
        )
        d.addCallback(cb)
        return d

    def __do_correl(self, result, info_dictionary, idxmpp, dom, xml, ctx):
        LOGGER.debug(_('Actual correlation'))
        previous_state, raw_event_id = result

        d = defer.Deferred()
        d.addCallback(lambda result: ctx.set('previous_state', previous_state))

        if raw_event_id:
            d.addCallback(lambda result: ctx.set('raw_event_id', raw_event_id))

        d.addCallback(lambda result: etree.tostring(dom[0]))

        def start_correl(payload, defs):
            tree_start, self.tree_end = defs
            # Gère les erreurs détectées à la fin du processus de corrélation,
            # ou émet l'alerte corrélée s'il n'y a pas eu de problème.
            self.tree_end.addCallbacks(
                self.__send_result,
                self.__correlation_eb,
                callbackArgs=[xml, info_dictionary],
                errbackArgs=[idxmpp, payload],
            )
            self.tree_end.addErrback(self.__send_result_eb, idxmpp, payload)
            # On lance le processus de corrélation.
            tree_start.callback((idxmpp, payload))
            return self.tree_end
        d.addCallback(start_correl, self.__executor.build_execution_tree())

        d.callback(None)
        return d

    def __send_result(self, result, xml, info_dictionary):
        """
        Traite le résultat de l'exécution de TOUTES les règles
        de corrélation.

        @param result: Résultat de la corrélation (transmis
            automatiquement par Twisted, vaut toujours None
            chez nous).
        @type result: C{None}
        @param xml: Message XML sérialisé traité par la corrélation.
        @type xml: C{unicode}
        @param info_dictionary: Informations extraites du message XML.
        @param info_dictionary: C{dict}
        """
        LOGGER.debug(_('Handling correlation results'))

        # On publie sur le bus XMPP l'état de l'hôte
        # ou du service concerné par l'alerte courante.
        publish_state(self, info_dictionary)

        d = defer.Deferred()
        def inc_messages(result):
            self._messages_sent += 1
        d.addCallback(inc_messages)

        dom = etree.fromstring(xml)
        idnt = dom.get('id')

        # Pour les services de haut niveau, on s'arrête ici,
        # on NE DOIT PAS générer d'événement corrélé.
        if info_dictionary["host"] == settings['correlator']['nagios_hls_host']:
            d.callback(None)
            return d

        dom = dom[0]
        def cb(result, dom, idnt):
            return make_correvent(self, self.__database, dom, idnt)
        def eb(failure, xml):
            LOGGER.info(_(
                'Error while saving the correlated event (%s). '
                'The message will be handled once more.'),
                str(failure).decode('utf-8')
            )
            self.queue.append(xml)
            return None
        d.addCallback(lambda res: self.__database.run(
            transaction.begin, transaction=False))
        d.addCallback(cb, dom, idnt)
        d.addCallback(lambda res: self.__database.run(
            transaction.commit, transaction=False))
        d.addErrback(eb, xml)

        d.callback(None)
        return d

    def __correlation_eb(self, failure, idxmpp, payload):
        """
        Cette méthode est appelée lorsque la corrélation échoue.
        Elle se contente d'afficher un message d'erreur.

        @param failure: L'erreur responsable de l'échec.
        @type failure: C{Failure}
        @param idxmpp: Identifiant du message XMPP.
        @type idxmpp: C{str}
        @param payload: Le message reçu à corréler.
        @type payload: C{Element}
        @return: L'erreur reponsable de l'échec.
        @rtype: C{Failure}
        """
        LOGGER.error(_('Correlation failed for '
                        'message #%(id)s (%(payload)s)'), {
            'id': idxmpp,
            'payload': payload,
        })
        return failure

    def __send_result_eb(self, failure, idxmpp, payload):
        """
        Cette méthode est appelée lorsque la corrélation
        s'est bien déroulée mais que le traitement des résultats
        a échoué.
        Elle se contente d'afficher un message d'erreur.

        @param failure: L'erreur responsable de l'échec.
        @type failure: C{Failure}
        @param idxmpp: Identifiant du message XMPP.
        @type idxmpp: C{str}
        @param payload: Le message reçu à corréler.
        @type payload: C{Element}
        """
        LOGGER.error(_('Unable to store correlated alert for '
                        'message #%(id)s (%(payload)s) : %(error)s'), {
            'id': idxmpp,
            'payload': payload,
            'error': str(failure).decode('utf-8'),
        })

    def connectionInitialized(self):
        """
        Cette méthode est appelée lorsque la connexion avec le bus XMPP
        est prête.
        """
        super(RuleDispatcher, self).connectionInitialized()
        self.rrp.start()

    def connectionLost(self, reason):
        """
        Cette méthode est appelée lorsque la connexion avec le bus XMPP
        est perdue. Dans ce cas, on arrête les tentatives de renvois de
        messages et on arrête le pool de rule runners.
        Le renvoi de messages et le pool seront relancés lorsque la
        connexion sera rétablie (cf. connectionInitialized).
        """
        super(RuleDispatcher, self).connectionLost(reason)
        LOGGER.debug(_(u'Connection lost'))

        try:
            self.rrp.stop()
        except KeyError:
            # Race condition: si on arrête le corrélateur trop rapidement
            # après son lancement, les pipes pour l'intercommunication ne sont
            # pas encore créés et on tente d'écrire dedans pour demander
            # l'arrêt du pool ce qui lève une exception.
            # On ignore l'erreur silencieusement ici.
            pass

    def sendItem(self, item):
        if not isinstance(item, etree.ElementBase):
            item = parseXml(item.encode('utf-8'))
        if item.name == MESSAGEONETOONE:
            self.sendOneToOneXml(item)
            return defer.succeed(None)
        else:
            result = self.publishXml(item)
            return result

    def __do_in_transaction(self, error_desc, xml, exc, func, *args, **kwargs):
        """
        Encapsule une opération nécessitant d'accéder à la base de données
        dans une transaction.

        @param error_desc: Un message d'erreur décrivant la nature de
            l'opération et qui sera affiché si l'opération échoue.
        @type error_desc: C{unicode}
        @param xml: Le message XML sérialisé en cours de traitement.
        @type xml: C{unicode}
        @param exc: Le type d'exceptions à capturer. En général, il s'agit
            de C{SQLAlchemyError}.
        @type exc: C{Exception}
        @param func: La fonction à appeler pour exécuter l'opération.
        @type func: C{callable}
        @note: Des paramètres additionnels (nommés ou non) peuvent être
            passés à cette fonction. Ils seront transmis tel quel à C{func}
            lors de son appel.
        @post: En cas d'erreur, le message XML est réinséré dans la file
            d'attente du corrélateur pour pouvoir être à nouveau traité
            ultérieurement.
        """
        d = self.__database.run(func, *args, **kwargs)
        def eb(failure):
            if failure.check(exc):
                LOGGER.info(_('%s. The message will be handled once more.') %
                    error_desc)
                self.queue.append(xml)
            else:
                LOGGER.error(failure)
            return failure
        d.addErrback(eb)
        return d

