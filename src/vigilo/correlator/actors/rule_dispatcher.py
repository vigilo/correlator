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
from sqlalchemy.exc import SQLAlchemyError, InvalidRequestError

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

from vigilo.models.tables import Change
from vigilo.models.session import DBSession

from vigilo.pubsub.xml import namespaced_tag, NS_EVENT, \
                                    NS_TICKET
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

def check_topology(last_topology_update):
    """
    Vérifie que la date de dernière modification de la topologie du parc,
    consignée dans la base de données, est bien antérieure à la date de
    dernière mise à jour de l'arbre topologique utilisé par le corrélateur
    (passée en paramètre). Reconstruit cet arbre si nécessaire.
    """

    # On récupère la date de dernière modification de la topologie
    # du parc, insérée dans la base de données par Vigiconf.
    last_topology_modification = \
        DBSession.query(Change.last_modified
            ).filter(Change.element == u"Topology"
            ).scalar()

    # Si aucune date n'a été insérée par Vigiconf
    if not last_topology_modification:
        # On affiche un message mais on ne
        # reconstruit pas l'arbre topologique
        # (inutile, car il est déjà à jour).
        LOGGER.info(_(u"No information from Vigiconf concerning the "
                       "topology's last modification date. Therefore the "
                       "topology has NOT been rebuilt."))
        return

    # On compare cette date à celle de la dernière modification
    # de l'arbre topologique utilisé par le corrélateur,
    # et on reconstruit l'arbre si nécessaire.
    if not last_topology_update \
        or last_topology_update < last_topology_modification:
        conn = MemcachedConnection()
        conn.delete('vigilo:topology')
        LOGGER.info(_(u"Topology has been reloaded."))

class RuleDispatcher(PubSubSender):
    """
    Cette classe corrèle les messages reçus depuis le bus XMPP
    et envoie ensuite les résultats sur le bus.
    """

    def __init__(self):
        super(RuleDispatcher, self).__init__()
        self.max_send_simult = 1
        self.tree_end = None

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
            starter=ProcessStarter(self),
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

    @defer.inlineCallbacks
    def processMessage(self, xml):
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
            LOGGER.error(_(u"Received invalid XMPP item ID (None)"))
            return

        # Extraction des informations du message
        info_dictionary = extract_information(dom[0])

        # S'il s'agit d'un message concernant un ticket d'incident :
        if dom[0].tag == namespaced_tag(NS_TICKET, 'ticket'):
            # On insère les informations la concernant dans la BDD ;
            transaction.begin()
            handle_ticket(info_dictionary)
            transaction.commit()
            # Et on passe au message suivant.
            return

        # Sinon, s'il ne s'agit pas d'un message d'événement (c'est-à-dire
        # un message d'alerte de changement d'état), on ne le traite pas.
        if dom[0].tag != namespaced_tag(NS_EVENT, 'event'):
            return

        # On initialise le contexte et on y insère
        # les informations de l'alerte traitée.
        ctx = Context(idxmpp)
        yield ctx.set('hostname', info_dictionary["host"])
        yield ctx.set('servicename', info_dictionary["service"])
        yield ctx.set('statename', info_dictionary["state"])
        yield ctx.set('timestamp', info_dictionary["timestamp"])

        # On met à jour l'arbre topologique si nécessaire.
        def handle_topology(ctx):
            last_topology_update = yield ctx.last_topology_update
            check_topology(last_topology_update)

        self.__do_in_transaction(
            _("Error while retrieving the network's topology"),
            xml, Exception,
            handle_topology, ctx,
        )

        # On insère le message dans la BDD, sauf s'il concerne un HLS.
        if not info_dictionary["host"]:
            raw_event_id = None
            self.__do_in_transaction(
                _("Error while adding an entry in the HLS history"),
                xml, SQLAlchemyError,
                insert_hls_history, info_dictionary
            )
        else:
            raw_event_id = self.__do_in_transaction(
                _("Error while adding an entry in the history"),
                xml, SQLAlchemyError,
                insert_event, info_dictionary
            )

        # On insère l'état dans la BDD
        previous_state = self.__do_in_transaction(
            _("Error while saving state"),
            xml, SQLAlchemyError,
            insert_state, info_dictionary
        )

        yield ctx.set('previous_state', previous_state)

        if raw_event_id:
            yield ctx.set('raw_event_id', raw_event_id)

        self._messages_sent += 1

        # On construit l'arbre d'exécution, on prépare la suite
        # du traitement (code à exécuter en sortie) et on déclenche
        # l'exécution des règles de corrélation.
        payload = etree.tostring(dom[0])
        tree_start, self.tree_end = self.__executor.build_execution_tree()

        # Gère les erreurs détectées à la fin du processus de corrélation,
        # ou émet l'alerte corrélée s'il n'y a pas eu de problème.
        self.tree_end.addCallbacks(
            self.__prepare_result, self.__correlation_eb,
            callbackArgs=[xml, info_dictionary],
            errbackArgs=[idxmpp, payload],
        )
        self.tree_end.addErrback(self.__send_result_eb, idxmpp, payload)

        # On lance le processus de corrélation.
        tree_start.callback((idxmpp, payload))
        yield defer.returnValue(self.tree_end)

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
        dom = etree.fromstring(xml)
        idnt = dom.get('id')

        # Pour les services de haut niveau, on s'arrête ici,
        # on NE DOIT PAS générer d'événement corrélé.
        if info_dictionary["host"] == settings['correlator']['nagios_hls_host']:
            return

        dom = dom[0]
        self.__do_in_transaction(
            _("Error while saving the correlated event"),
            xml, SQLAlchemyError,
            make_correvent, self, dom, idnt
        )

    def __prepare_result(self, result, xml, info_dictionary):
        """
        Permet de ne réaliser le traitement du résultat
        que lorsque toutes les règles de corrélation ont
        été exécutées, ainsi que les callbacks post-corrélation.
        """
        # On publie sur le bus XMPP l'état de l'hôte
        # ou du service concerné par l'alerte courante.
        publish_state(self, info_dictionary)
        return self.__send_result(result, xml, info_dictionary)

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
                        'message #%(id)s (%(payload)s)'), {
            'id': idxmpp,
            'payload': payload,
        })

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
        transaction.begin()
        try:
            LOGGER.debug(_("Executing %s with %r, %r"), func.__name__, args, kwargs)
            res = func(*args, **kwargs)
        except exc:
            LOGGER.info(_("%s. The message will be handled once more.") %
                        error_desc)
            transaction.abort()
            self.queue.append(xml)
        else:
            transaction.commit()
        return res

