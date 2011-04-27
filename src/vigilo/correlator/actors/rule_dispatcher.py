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
from twisted.internet.error import ProcessTerminated
from twisted.protocols import amp
from ampoule import pool, main
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
                                    NS_TICKET#, NS_DOWNTIME
from vigilo.correlator.actors import rule_runner
from vigilo.correlator.registry import get_registry
from vigilo.correlator.memcached_connection import MemcachedConnection, \
                                                    MemcachedConnectionError
from vigilo.correlator.context import Context
#from vigilo.correlator.handle_downtime import handle_downtime
from vigilo.correlator.handle_ticket import handle_ticket
from vigilo.correlator.db_insertion import insert_event, insert_state, \
                                            insert_hls_history
from vigilo.correlator.publish_messages import publish_state
from vigilo.correlator.correvent import make_correvent
from vigilo.correlator.amp import SendToBus, RegisterCallback

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
#                       "type": None,
#                       "author": None,
#                       "comment": None,
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

class ProcessStarter(main.ProcessStarter):
    def __init__(self, rule_dispatcher, *args, **kwargs):
        self.rule_dispatcher = rule_dispatcher
        super(ProcessStarter, self).__init__(*args, **kwargs)

    def startPythonProcess(self, prot, *args):
        prot.amp.rule_dispatcher = self.rule_dispatcher
        return super(ProcessStarter, self).startPythonProcess(prot, *args)

class Correlator(amp.AMP):
    def __init__(self):
        super(Correlator, self).__init__()

    @SendToBus.responder
    def send_to_bus(self, item):
        LOGGER.debug(_('Sending this payload to the XMPP bus: %r'), item)
        self.rule_dispatcher.sendItem(item)
        return {}

    @RegisterCallback.responder
    def register_callback(self, fn, idnt):
        LOGGER.debug(_('Registering post-correlation callback function '
                        '"%(fn)s" for alert with ID %(id)s'), {
                            'fn': fn,
                            'id': idnt,
                        })

        def callback_wrapper(result):
            try:
                transaction.begin()
                res = fn(result, self.rule_dispatcher, idnt)
            except:
                transaction.abort()
            else:
                transaction.commit()

        self.rule_dispatcher.tree_end.addCallback(callback_wrapper)
        return {}

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

        ## Prépare les schémas de validation XSD.
        #self.schema = {}
        #try:
        #    validate = settings['correlator'].as_bool('validate_messages')
        #except KeyError:
        #    validate = False

        #if validate:
        #    catalog_fname = pkg_resources.resource_filename(
        #            'vigilo.pubsub', 'data/catalog.xml')
        #    # We override whatever this was set to.
        #    os.environ['XML_CATALOG_FILES'] = catalog_fname

        #    file_mapping = {
        #        namespaced_tag(NS_EVENT, 'events'): 'data/schemas/event1.xsd',
        #    }

        #    for tag, filename in file_mapping:
        #        schema_file = pkg_resources.resource_stream(
        #                'vigilo.pubsub', filename)
        #        self.schema[tag] = etree.XMLSchema(file=schema_file)

    def __build_execution_tree(self):
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

        work = self.rrp.doWork(rule_runner.RuleCommand,
            rule_name=rule_name, idxmpp=idxmpp, xml=xml)
        work.addCallback(cb, idxmpp, xml)
        work.addErrback(eb, rule_name)
        return d

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
        """
        Transfère un message XML sérialisé vers la file.

        @param xml: message XML à transférer.
        @type xml: C{str}
        @return: Un objet C{Deferred} correspondant au traitement
            du message par les règles de corrélation ou C{None} si
            le message n'a pas pu être traité (ex: message invalide).
        @rtype: C{twisted.internet.defer.Deferred} ou C{None}
        """


        def sendResult(result, xml, info_dictionary):
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
            transaction.begin()
            try:
                make_correvent(self, dom, idnt)
            except SQLAlchemyError:
                LOGGER.info(_("Error while saving the correlated event. "
                                "The message will be handled once more."))
                transaction.abort()
                self.queue.append(xml)
            else:
                transaction.commit()


        #LOGGER.debug(_(u'Spawning for payload: %s'), xml)
        dom = etree.fromstring(xml)

        # Extraction de l'id XMPP.
        # Note: dom['id'] ne fonctionne pas dans lxml, dommage.
        idxmpp = dom.get('id')
        if idxmpp is None:
            LOGGER.error(_(u"Received invalid XMPP item ID (None)"))
            return

        #-#if self.schema.get(dom[0].tag) is not None:
        #-#    # Validation before dispatching.
        #-#    # This breaks the policy of not doing computing
        #-#    # in the main process, but this must be computed once.
        #-#    try:
        #-#        self.schema[dom[0].tag].assertValid(dom[0])
        #-#    except etree.DocumentInvalid, e:
        #-#        LOGGER.error(_(u"Validation failure: %s"), e.message)
        #-#        return

        # Extraction des informations du message
        info_dictionary = extract_information(dom[0])

#        # S'il s'agit d'un message concernant une mise en silence :
#        if dom[0].tag == namespaced_tag(NS_DOWNTIME, 'downtime'):
#            # On insère les informations la concernant dans la BDD ;
#            handle_downtime(info_dictionary)
#            transaction.commit()
#            transaction.begin()
#            # Et on passe au message suivant.
#            return

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
        try:
            ctx = Context(idxmpp)
        except MemcachedConnectionError:
            LOGGER.error(_("Error connecting to MemcacheD! Check its log "
                           "for more information"))
            return
        ctx.hostname = info_dictionary["host"]
        ctx.servicename = info_dictionary["service"]
        ctx.statename = info_dictionary["state"]

        # On met à jour l'arbre topologique si nécessaire.
        transaction.begin()
        try:
            check_topology(ctx.last_topology_update)
        except:
            LOGGER.info(_("Error while retrieving the network's topology. "
                            "The message will be handled once more."))
            transaction.abort()
            try:
                return self.queue.append(xml)
            except Exception, e:
                print "@@ %r @@" % e
        else:
            transaction.commit()

        # On insère le message dans la BDD, sauf s'il concerne un HLS.
        if not info_dictionary["host"]:
            raw_event_id = None
            transaction.begin()
            try:
                insert_hls_history(info_dictionary)
            except SQLAlchemyError:
                LOGGER.info(_("Error while adding an entry in the HLS history. "
                                "The message will be handled once more."))
                transaction.abort()
                self.queue.append(xml)
                return
            else:
                transaction.commit()
        else:
            transaction.begin()
            try:
                raw_event_id = insert_event(info_dictionary)
            except SQLAlchemyError:
                LOGGER.info(_("Error while adding an entry in the history. "
                                "The message will be handled once more."))
                transaction.abort()
                self.queue.append(xml)
                return
            else:
                transaction.commit()

        # On insère l'état dans la BDD
        transaction.begin()
        try:
            previous_state = insert_state(info_dictionary)
        except SQLAlchemyError:
            LOGGER.info(_("Error while saving state. "
                        "The message will be handled once more."))
            transaction.abort()
            self.queue.append(xml)
            return
        else:
            transaction.commit()

        ctx.previous_state = previous_state

        if raw_event_id:
            ctx.raw_event_id = raw_event_id

        self._messages_sent += 1

        # On construit l'arbre d'exécution, on prépare la suite
        # du traitement (code à exécuter en sortie) et on déclenche
        # l'exécution des règles de corrélation.
        payload = etree.tostring(dom[0])
        tree_start, self.tree_end = self.__build_execution_tree()

        def correlation_eb(failure, idxmpp, payload):
            LOGGER.error(_('Correlation failed for '
                            'message #%(id)s (%(payload)s)'), {
                'id': idxmpp,
                'payload': payload,
            })
            return failure

        def send_result_eb(failure):
            LOGGER.error(_('Unable to store correlated alert for '
                            'message #%(id)s (%(payload)s)'), {
                'id': idxmpp,
                'payload': payload,
            })

        def prepareToSendResult(result, xml, info_dictionary):
            """
            Permet de ne réaliser le traitement du résultat
            que lorsque toutes les règles de corrélation ont
            été exécutées, ainsi que les callbacks post-corrélation.
            """
            # On publie sur le bus XMPP l'état de l'hôte
            # ou du service concerné par l'alerte courante.
            publish_state(self, info_dictionary)
            self.tree_end.addCallback(sendResult, xml, info_dictionary)

        # Gère les erreurs détectées à la fin du processus de corrélation,
        # ou émet l'alerte corrélée s'il n'y a pas eu de problème.
        self.tree_end.addCallbacks(
            prepareToSendResult, correlation_eb,
            callbackArgs=[xml, info_dictionary],
            errbackArgs=[idxmpp, payload],
        )
        self.tree_end.addErrback(send_result_eb, idxmpp, payload)

        # On lance le processus de corrélation.
        tree_start.callback((idxmpp, payload))
        return self.tree_end

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
