# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Ce module est un demi-connecteur qui assure la redirection des messages
issus du bus XMPP vers une file d'attente (C{Queue.Queue} ou compatible).
"""
import os.path
import pkg_resources
import transaction
from sqlalchemy.exc import OperationalError
from datetime import datetime

from twisted.internet import task, defer, reactor
from twisted.internet.error import ProcessTerminated
from twisted.words.xish import domish
from ampoule import pool
from wokkel.pubsub import PubSubClient, Item
from wokkel.generic import parseXml
from lxml import etree

from vigilo.common.conf import settings
settings.load_module(__name__)

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

from vigilo.connector.store import DbRetry
from vigilo.connector.sockettonodefw import MESSAGEONETOONE

from vigilo.models.tables import Change
from vigilo.models.session import DBSession

from vigilo.correlator.xml import namespaced_tag, NS_EVENTS, \
                                    NS_TICKET#, NS_DOWNTIME
from vigilo.correlator.actors import rule_runner
from vigilo.correlator.registry import get_registry
from vigilo.correlator.memcached_connection import MemcachedConnection
from vigilo.correlator.context import Context, TOPOLOGY_PREFIX
#from vigilo.correlator.handle_downtime import handle_downtime
from vigilo.correlator.handle_ticket import handle_ticket
from vigilo.correlator.db_insertion import insert_event, insert_state
from vigilo.correlator.publish_messages import publish_state
from vigilo.correlator.correvent import make_correvent

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
    namespace = etree.QName(payload.tag).namespace
    
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
        LOGGER.info(_("No information from Vigiconf concerning the "
                       "topology's last modification date. Therefore the "
                       "topology has NOT been rebuilt."))
        return
    
    # On compare cette date à celle de la dernière modification
    # de l'arbre topologique utilisé par le corrélateur,
    # et on reconstruit l'arbre si nécessaire.
    if not last_topology_update \
        or last_topology_update < last_topology_modification:
        conn = MemcachedConnection()
        conn.delete(TOPOLOGY_PREFIX)
        LOGGER.info(_("Topology has been reloaded."))

class DependencyError(Exception):
    pass

class RuleDispatcher(PubSubClient):
    """
    Cette classe corrèle les messages reçus depuis le bus XMPP
    et envoie ensuite les résultats sur le bus.
    """

    def __init__(self, dbfilename, from_table, to_table,
        nodetopublish, service):
        """
        Initialisation du demi-connecteur.
        
        @param dbfilename: Emplacement du fichier SQLite de sauvegarde.
            Ce fichier est utilisé pour stocker temporairement les messages.
            Les messages dans cette base de données seront automatiquement
            traités lorsque les éléments nécessaires au traitement seront
            de nouveau disponibles.
        @type dbfilename: C{basestring}
        @param from_table: Nom de la table à utiliser dans le fichier
            de sauvegarde L{dbfilename} pour stocker les messages qui
            arrivent dans le corrélateur mais qui ne peuvent pas être
            traités immédiatement.
        @type from_table: C{basestring}
        @param to_table: Nom de la table à utiliser dans le fichier
            de sauvegarde L{dbfilename} pour stocker les messages qui
            ont été traités par le corrélateur mais pour lesquels
            l'envoi des résultats sur le bus XMPP a échoué (par exemple,
            parce que la connexion avec le bus a été perdue).
        @type to_table: C{basestring}
        @param nodetopublish: Dictionnaire pour la correspondance entre
            le type de message et le noeud PubSub de destination.
        @type nodetopublish: C{dict}
        @param service: Le service de souscription qui gère les nœuds.
        @type service: L{twisted.words.protocols.jabber.jid.JID}
        """
        super(RuleDispatcher, self).__init__()
        self.from_retry = DbRetry(dbfilename, from_table)
        self.to_retry = DbRetry(dbfilename, to_table)
        self._service = service
        self._nodetopublish = nodetopublish
        self.parallel_messages = 0
        self.loop_call = task.LoopingCall(self.__sendQueuedMessages)

        # Préparation du pool d'exécuteurs de règles.
        timeout = settings['correlator'].as_int('rules_timeout')
        min_runner = settings['correlator'].as_int('min_rule_runners')
        max_runner = settings['correlator'].as_int('max_rule_runners')

        try:
            max_idle = settings['correlator'].as_int('rule_runners_max_idle')
        except KeyError:
            max_idle = 20

        self.rrp = pool.ProcessPool(
            maxIdle=max_idle,
            ampChild=rule_runner.VigiloAMPChild,
            # @XXX Désactivé pour le moment car pose des problèmes.
            # Lorsqu'un processus atteint le timeout, il est tué,
            # mais lorsqu'une tâche arrive, ampoule semble ne pas
            # attendre que le processus soit créé pour lui envoyer
            # la tâche. On tombe dans une race condition et la règle
            # échoue (à cause d'un timeout). Plusieurs messages
            # peuvent ainsi défiler sans être traités...
#            timeout=timeout,
            name='RuleDispatcher',
            min=min_runner,
            max=max_runner,
        )

        # Prépare les schémas de validation XSD.
        self.schema = {}
        try:
            validate = settings['correlator'].as_bool('validate_messages')
        except KeyError:
            validate = False

        if validate:
            catalog_fname = pkg_resources.resource_filename(
                    'vigilo.pubsub', 'data/catalog.xml')
            # We override whatever this was set to.
            os.environ['XML_CATALOG_FILES'] = catalog_fname

            file_mapping = {
                namespaced_tag(NS_EVENTS, 'events'): 'data/schemas/event1.xsd',
            }

            for tag, filename in file_mapping:
                schema_file = pkg_resources.resource_stream(
                        'vigilo.pubsub', filename)
                self.schema[tag] = etree.XMLSchema(file=schema_file)

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
            LOGGER.debug(_('Got item: %s') % xml)
            if item.name != 'item':
                # The alternative is 'retract', which we silently ignore
                # We receive retractations in FIFO order,
                # ejabberd keeps 10 items before retracting old items.
                LOGGER.debug(_('Skipping unrecognized item (%s)') % item.name)
                continue
            self.handleMessage(xml)

    def handleMessage(self, xml):
        """
        Transfère un message XML sérialisé vers la file.

        @param xml: message XML à transférer.
        @type xml: C{str}
        @return: Un objet C{Deferred} correspondant au traitement
            du message par les règles de corrélation ou C{None} si
            le message n'a pas pu être traité (ex: message invalide).
        @rtype: C{twisted.internet.defer.Deferred} ou C{None}
        """
        # Si il y a déjà un message en cours de traitement,
        # on le stocke en base SQLite directement.
        if self.parallel_messages:
            self.from_retry.store(xml)
            return

        def handle_rule_error(failure, rule_name):
            """
            Parcourt les erreurs Twisted survenues pendant l'exécution
            d'une règle à la recherche d'informations indiquant que la
            règle a dépassé le délai autorisé.
            Lorsqu'une telle erreur est trouvée, un message est loggué
            et une nouvelle exception (différente) est levée.
            Ceci permet d'empêcher l'exécution des règles qui dépendent
            de la règle qui a échoué, tout en évitant d'enregistrer à
            nouveau le message d'erreur pour les règles dépendantes.

            @param failure: Erreur remontée par Twisted.
            @type failure: C{twisted.python.failure.Failure}
            @param rule_name: Nom de la règle de corrélation à l'origine
                du problème.
            @type rule_name: C{basestring}
            @return: L'erreur originale ou une nouvelle erreur.
            @type: C{Exception} ou C{twisted.python.failure.Failure}
            """
            # On remonte la pile des FirstError jusqu'à
            # tomber sur la véritable erreur.
            while True:
                try:
                    failure.raiseException()
                # S'il s'agit d'une FirstError, il faut analyser
                # l'erreur sous-jacente (sub-failure).
                except defer.FirstError, e:
                    failure = e.subFailure
                # L'exception ProcessTerminated est levée lorsqu'une règle
                # vient juste d'échouer (timeout).
                # On enregistre le problème et on lève une (autre) exception.
                except ProcessTerminated:
                    LOGGER.info(_('Rule %(rule_name)s timed out') % {
                        'rule_name': rule_name,
                    })
                    return DependencyError(failure)
                # Pour les autres types d'exception, on les transmet
                # intactes pour qu'un autre errback puisse éventuellement
                # les traiter.
                except Exception:
                    break
            return failure

        deferred_cache = {}
        def buildDeferredList(graph, node, idxmpp, xml):
            """
            Construit récursivement les nœuds intermédiaires de l'arbre
            de C{Deferred}s correspondant à l'arbre des dépendances
            entre les règles de corrélation.
            
            N'utilisez pas directement cette fonction, à la place,
            utilisez buildExecutionGraph() qui appelera buildDeferredList()
            au besoin.

            @param graph: Graphe des dépendances entre règles.
            @type graph: C{networkx.DiGraph}
            @param node: Nom de la règle de corrélation en cours de
                traitement dans le graphe.
            @type node: C{basestring}
            @param idxmpp: Identifiant XMPP du message à traiter.
            @type idxmpp: C{basestring}
            @param xml: Message XML sérialisé à traiter.
            @type xml: C{unicode}
            @return: DeferredList correspondant au traitement de la règle
                et de ses dépendances.
            @rtype: C{twisted.internet.defer.DeferredList}
            """
            if deferred_cache.has_key(node):
                return deferred_cache[node]

            subdeferreds = [buildDeferredList(graph, r[1], idxmpp, xml) \
                            for r in graph.out_edges_iter(node)]
            work = self.rrp.doWork(rule_runner.RuleRunner,
                        rule_name=node, idxmpp=idxmpp, xml=xml)
            work.addErrback(handle_rule_error, node)
            subdeferreds.append(work)
            dl = defer.DeferredList(subdeferreds, fireOnOneErrback=1)
            dl.addErrback(handle_rule_error, node)

            deferred_cache[node] = dl
            return dl

        def buildExecutionGraph(idxmpp, payload):
            """
            Construit l'arbre de C{Deferred}s correspondant à l'arbre
            des dépendances entre les règles.

            @param idxmpp: Identifiant XMPP du message à traiter.
            @type idxmpp: C{basestring}
            @param xml: Message XML sérialisé à traiter.
            @type xml: C{unicode}
            @return: DeferredList correspondant au traitement des règles
                qui ne sont en dépendance d'aucune autre (ie: les sources
                dans le graphe des dépendances).
            @rtype: C{twisted.internet.defer.DeferredList}
            """
            rules_graph = get_registry().rules.rules_graph
            subdeferreds = [buildDeferredList(rules_graph, r, idxmpp, payload)
                            for r in rules_graph.nodes_iter() \
                            if not rules_graph.in_degree(r)]
            graph = defer.DeferredList(subdeferreds)
            return graph

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
            # On ne doit pas émettre plus de résultats que
            # le nombre de calculs qui nous a été demandé.
            assert(self.parallel_messages > 0)
            self.parallel_messages -= 1

            # On publie sur le bus XMPP l'état de l'hôte
            # ou du service concerné par l'alerte courante.
            publish_state(self, info_dictionary)
            
            # Pour les services de haut niveau, on s'arrête ici,
            # on NE DOIT PAS générer d'événement corrélé.
            if info_dictionary["host"] == \
                settings['correlator']['nagios_hls_host']:
                return

            make_correvent(self, xml)
            transaction.commit()
            transaction.begin()

        LOGGER.debug(_('Spawning for payload: %s') % xml)
        dom = etree.fromstring(xml)

        # Extraction de l'id XMPP.
        # Note: dom['id'] ne fonctionne pas dans lxml, dommage.
        idxmpp = dom.get('id')
        if idxmpp is None:
            LOGGER.critical(_("Received invalid XMPP item ID (None)"))
            return

        if self.schema.get(dom[0].tag) is not None:
            # Validation before dispatching.
            # This breaks the policy of not doing computing
            # in the main process, but this must be computed once.
            try:
                self.schema[dom[0].tag].assertValid(dom[0])
            except etree.DocumentInvalid, e:
                LOGGER.error(_("Validation failure: %s") % e.message)
                return

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
            handle_ticket(info_dictionary)
            transaction.commit()
            transaction.begin()
            # Et on passe au message suivant.
            return

        # Sinon, s'il ne s'agit pas d'un message d'événement (c'est-à-dire
        # un message d'alerte de changement d'état), on ne le traite pas.
        if dom[0].tag != namespaced_tag(NS_EVENTS, 'event'):
            return

        # On initialise le contexte et on y insère 
        # les informations de l'alerte traitée.
        ctx = Context(idxmpp)
        ctx.hostname = info_dictionary["host"]
        ctx.servicename = info_dictionary["service"]
        ctx.statename = info_dictionary["state"]
        
        # On met à jour l'arbre topologique si nécessaire.
        try:
            check_topology(ctx.last_topology_update)
        except OperationalError:
            LOGGER.critical(_("Could not connect to the "
                "database server, make sure it is running"))
            reactor.stop()
            return

        # On insère le message dans la BDD, sauf s'il concerne un HLS.
        if not info_dictionary["host"]:
            raw_event_id = None
        else:
            raw_event_id = insert_event(info_dictionary)
            transaction.commit()
            transaction.begin()

        # On insère l'état dans la BDD
        previous_state = insert_state(info_dictionary)
        transaction.commit()
        transaction.begin()

        ctx.previous_state = previous_state

        if raw_event_id:
            ctx.raw_event_id = raw_event_id

        # Le vrai travaille commence ici.
        self.parallel_messages += 1

        # 1 -   On génère un graphe avec des DeferredLists qui reproduit
        #       le graphe des dépendances entre les règles de corrélation.

        payload = etree.tostring(dom[0], encoding='utf-8')
        correlation_graph = buildExecutionGraph(idxmpp, payload)

        # 2 -   Quand toutes les règles de corrélation ont été exécutées,
        #       le callback associé à correlation_graph est appelé pour
        #       finaliser le traitement (envoyer l'événement corrélé).

        # À la fin des traitements, on doit ignorer les erreurs issues
        # d'une règle précédente (elles ont déjà enregistrées et le
        # traitement de la corrélation doit continuer dans ce cas).
        def ignore_previous_dependency_failures(failure):
            """
            Capture l'exception DependencyError qui indique qu'une
            des règles de corrélation a échoué.
            """
            if failure.check(DependencyError):
                return ""
            return failure

        correlation_graph.addErrback(ignore_previous_dependency_failures)
        correlation_graph.addCallback(sendResult, xml, info_dictionary)
        return correlation_graph

    def __sendQueuedMessages(self):
        """
        Déclenche l'envoi des messages stockées localement (retransmission
        des messages suite à une panne).
        """

        # Tout d'abord, réinsertion des messages dans la table en sortie.
        needs_vacuum = False
        while True:
            msg = self.to_retry.unstore()
            if msg is None:
                break
            else:
                needs_vacuum = True
                item = parseXml(msg)
                if item is None:
                    pass
                else:
                    self.sendItem(msg)

        # On fait du nettoyage au besoin.
        if needs_vacuum:
            self.to_retry.vacuum()

        # On essaye de traiter un nouveau message qui serait en attente en
        # entrée du corrélateur.
        # On fait les traitements dans cet ordre afin d'éviter de renvoyer
        # immédiatement un message dont l'envoi initial aurait échoué.
        needs_vacuum = False
        if not self.parallel_messages:
            msg = self.from_retry.unstore()
            if msg is not None:
                needs_vacuum = True
                self.handleMessage(msg)

        # On fait du nettoyage au besoin.
        if needs_vacuum:
            self.from_retry.vacuum()

    def chatReceived(self, msg):
        """ 
        function to treat a received chat message 
        
        @param msg: msg to treat
        @type  msg: twisted.words.xish.domish.Element

        """
        # Il ne devrait y avoir qu'un seul corps de message (body)
        bodys = [element for element in msg.elements()
                         if element.name in ('body',)]

        for b in bodys:
            # the data we need is just underneath
            # les données dont on a besoin sont juste en dessous
            for data in b.elements():
                LOGGER.debug(_("Chat message to forward: '%s'") %
                               data.toXml().encode('utf8'))
                self.messageForward(data.toXml().encode('utf8'))

    def connectionInitialized(self):
        """
        Cette méthode est appelée lorsque la connexion avec le bus XMPP
        est prête. On se contente d'appeler la méthode L{consomeQueue}
        depuis le reactor de Twisted pour commencer le transfert.
        """
        super(RuleDispatcher, self).connectionInitialized()
        self.xmlstream.addObserver("/message[@type='chat']", self.chatReceived)
        LOGGER.debug(_('Connection initialized'))

        # Vérifie la présence de messages dans la base de données
        # locale toutes les queue_delay secondes, ou 0.1 par défaut.
        try:
            queue_delay = float(settings['correlator'].get(
                'queue_delay', None))
        except ValueError:
            queue_delay = 0.1

        LOGGER.info(_('Starting the queue manager with a delay '
                        'of %f seconds.') % queue_delay)
        self.loop_call.start(queue_delay)
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
        LOGGER.debug(_('Connection lost'))

        if self.loop_call.running:
            self.loop_call.stop()
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
            item = parseXml(item)
        if item.name == MESSAGEONETOONE:
            return self.__sendOneToOneXml(item)
        else:
            return self.__publishXml(item)

    def __sendOneToOneXml(self, xml):
        """ 
        function to send a XML msg to a particular jabber user
        @param xml: le message a envoyé sous forme XML 
        @type xml: twisted.words.xish.domish.Element
        """
        # il faut l'envoyer vers un destinataire en particulier
        msg = domish.Element((None, "message"))
        msg["to"] = xml['to']
        msg["from"] = self.parent.jid.userhostJID().full()
        msg["type"] = 'chat'
        body = xml.firstChildElement()
        msg.addElement("body", content=body)
        # if not connected store the message
        if self.xmlstream is None:
            xml_src = xml.toXml().encode('utf8')
            LOGGER.error(_('Unable to forward one-to-one message to XMPP '
                            'server (no connection established). The message '
                            '(%s) has been stored for later retransmission.') %
                            xml_src)
            self.to_retry.store(xml_src)
            return False
        else:
            self.send(msg)
            return True

    def __publishXml(self, xml):
        """ 
        function to publish a XML msg to node 
        @param xml: le message a envoyé sous forme XML 
        @type xml: twisted.words.xish.domish.Element
        """
        def eb(e, xml):
            """errback"""
            xml_src = xml.toXml().encode('utf8')
            LOGGER.error(_('Unable to forward the message (%(error)r), it '
                        'has been stored for later retransmission '
                        '(%(xml_src)s)') % {
                            'xml_src': xml_src,
                            'error': e,
                        })
            self.to_retry.store(xml_src)

        item = Item(payload=xml)
        
        if xml.name not in self._nodetopublish:
            LOGGER.error(_("No destination node configured for messages "
                           "of type '%s'. Skipping.") % xml.name)
            return
        node = self._nodetopublish[xml.name]
        try:
            result = self.publish(self._service, node, [item])
            result.addErrback(eb, xml)
        except AttributeError:
            xml_src = xml.toXml().encode('utf8')
            LOGGER.error(_('Message from Socket impossible to forward'
                           ' (no connection to XMPP server), the message '
                           'is stored for later reemission (%s)') % xml_src)
            self.to_retry.store(xml_src)

