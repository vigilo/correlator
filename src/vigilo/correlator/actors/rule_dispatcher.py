# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Exécution des règles du corrélateur
"""
import os
import errno
import Queue
import warnings
import pkg_resources
import transaction

from vigilo.correlator.actors.pool import VigiloPool
from vigilo.correlator.libs import etree
from vigilo.correlator.xml import namespaced_tag, NS_EVENTS
from vigilo.correlator import rulesapi
#from vigilo.correlator.xml import NS_DOWNTIME

from vigilo.correlator.actors import rule_runner
from vigilo.correlator.registry import get_registry

from vigilo.correlator.connect import connect
from vigilo.correlator.context import Context, TOPOLOGY_PREFIX

#from vigilo.correlator.handle_downtime import handle_downtime

from vigilo.correlator.db_insertion import insert_event, insert_state
from vigilo.correlator.publish_messages import publish_state
from vigilo.correlator.correvent import make_correvent

from vigilo.models import Change
from vigilo.models.configure import DBSession

from datetime import datetime

from vigilo.common.conf import settings
from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

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
                       "type": None,
                       "author": None,
                       "comment": None,}
        
    # Récupération du namespace utilisé
    namespace = payload.tag.split("}")[0][1:]
    
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
        conn = connect()
        conn.delete(TOPOLOGY_PREFIX)
        LOGGER.info(_("Topology has been reloaded."))

def create_rule_runners_pool(out_queue):
    """
    Création du pool de processus utilisé par le rule_dispatcher.
    Suppression de l'ancien s'il en existait un.
    """
    try:
        # Si "rule_runners_count" a été défini dans la configuration,
        # on honore sa valeur.
        processes = settings['correlator'].as_int('rule_runners_count')
    except KeyError:
        try:
            # Sinon, on tente d'être malin en utilisant
            # tous les processeurs à disposition.
            processes = mp.cpu_count()
        except NotImplementedError:
            # Et sinon, on utilise une valeur par défaut
            # complètement arbitraire.
            processes = 4
        finally:
            LOGGER.info(_('You did not set the number of rule runners to use. '
                        'I chose to use %d. Set "rule_runners_count" in the '
                        'settings if this unacceptable.') % processes)

    # Crée un nouveau pool de processus compatibles avec Twisted.
    return VigiloPool(
        processes = processes,
        initializer = rule_runner.init,
        initargs = (out_queue, )
    )
    
def handle_rules_errors(results, rules_graph, out_queue, rule_runners_pool):
    """ Fonction de traitement des valeurs de retour des règles """
    
    regenerate_pool = False
    
    # On vérifie le code de retour de chacune des règles
    for (rule_name, result, ex) in results:
        LOGGER.debug(_("##### Rule %(name)r -> Result : %(result)r #####") % {
                        "name": rule_name,
                        "result": result,
                    })
        if ex:
            LOGGER.debug(_("##### Exception raised : %r #####") % ex)
        # Si une erreur s'est produite,
        if result != rulesapi.ENOERROR:
            # On retire la règle du graphe 
            # de dépendance des règles.
            rules_graph.remove_rule(rule_name)
            # Et on reconstruit le pool de processus utilisé.
            regenerate_pool = True
    
    if regenerate_pool:
        LOGGER.info(_('At least one of the rules failed, '
                        'recreating worker processes.'))
        if rule_runners_pool:
            rule_runners_pool.terminate()
            rule_runners_pool.join()
        rule_runners_pool = create_rule_runners_pool(out_queue)
        
    return rule_runners_pool

def handle_bus_message(manager, conn, schema, rule_runners_pool, xml):
    """ Lecture et traitement d'un message du bus XMPP """
    dom = etree.fromstring(xml)

    # Extraction des informations du message
    info_dictionary = extract_information(dom[0])

#    # S'il s'agit d'un message concernant une mise en silence :
#    if dom[0].tag == namespaced_tag(NS_DOWNTIME, 'downtime'):
#        # On insère les informations la concernant dans la BDD ;
#        handle_downtime(info_dictionary)
#        # Et on passe au message suivant.
#        return

    # Sinon, s'il ne s'agit pas d'un message d'événement (c'est à dire
    # un message d'alerte de changement d'état), on ne le traite pas.
#    elif dom[0].tag != namespaced_tag(NS_EVENTS, 'event'):
    if dom[0].tag != namespaced_tag(NS_EVENTS, 'event'):
        return rule_runners_pool
    
    # On initialise le contexte et on y insère 
    # les informations de l'alerte traitée.
    idnt = dom.get('id')
    ctx = Context.get_or_create(manager.out_queue, idnt)
    ctx.hostname = info_dictionary["host"]
    ctx.servicename = info_dictionary["service"]
    ctx.statename = info_dictionary["state"]
    
    # On met à jour l'arbre topologique si nécessaire.
    check_topology(ctx.last_topology_update)

    # On insère le message dans la BDD, sauf s'il concerne un HLS.
    if not info_dictionary["host"]:
        raw_event_id = None
    else:
        raw_event_id = insert_event(info_dictionary)
        transaction.commit()
        transaction.begin()

    # On insère l'état dans la BDD
    insert_state(info_dictionary)
    transaction.commit()
    transaction.begin()

    if raw_event_id:
        ctx.raw_event_id = raw_event_id

    if schema is not None:
        # Validation before dispatching.
        # This breaks the policy of not doing computing
        # in the main process, but this must be computed once.
        try:
            schema.assertValid(dom[0])
        except etree.DocumentInvalid, e:
            warnings.warn(e.message)

    # Préparation du 1er étage d'exécution des règles.
    LOGGER.debug(_('Spawning for payload: %s') % xml)
    
    rules_graph = get_registry().global_instance().rules.step_rules
    
    for (step, step_rules) in enumerate(rules_graph.rules):
        LOGGER.debug(_('Running rules from step #%(step)d: %(rules)r') % {
            'step': step + 1,
            'rules': step_rules,
        })

        work_units = [(rule_name, xml)
                for rule_name in step_rules]

        if not rule_runners_pool:
            # Process the message in serial order.
            for work_unit in work_units:
                rule_runner.api = None
                rule_runner.init(manager.out_queue)
                if rule_runner.process(work_unit)[1] != rulesapi.ENOERROR:
                    # @TODO Faire d'autres traitements ici.
                    rules_graph.remove_rule(work_unit[0])

        elif True:
            # Blocks, better for debugging multiprocessing problems
            # (see test_mprocess)
            # or stalled rules (the latter should be reaped somehow btw).
            # TODO: le choix du "chunksize" est arbitraire (défaut = 1).
            # Il faudrait en faire une option de la configuration.
            try:
                chunksize = settings['correlator'].as_int('map_chunksize')
            except KeyError:
                chunksize = 1
            results = rule_runners_pool.imap_unordered(
                rule_runner.process, work_units, chunksize)

            # On vérifie le code de retour de chacune des règles
            rule_runners_pool = handle_rules_errors(results, rules_graph, 
                manager.out_queue, rule_runners_pool)

# TODO : Implémenter un traitement des règles en "flux tendu", c'est à dire
#    que les règles devraient être traitées dès que les règles dont elles
#    dépendent ont retourné leur résultat. On pourra utiliser à cet effet la
#    la fonction map_async de multiprocessing, mais cela demandera une
#    synchronisation plus fine de l'exécution des règles.

#        else:
#            # Not a twisted deferred, a similar multiprocessing construct
#            def callback_function(results):
#                """
#                Fonction appelée par map_async pour traiter les résultats.
#                Elle se contente d'appeler la fonction handle_rules_errors
#                avec les bons paramètres.
#                """
#                LOGGER.debug(_("##### CALLBACK #####"))
#                handle_rules_errors(results, rules_graph, 
#                    manager.out_queue, rule_runners_pool)
#            
#            LOGGER.debug(_("##### BEFORE MAP_ASYNC #####"))
#                
#            rule_runners_pool.map_async(rule_runner.process, 
#                work_units, callback = callback_function)
#            
#            LOGGER.debug(_("##### AFTER MAP_ASYNC #####"))

#    # On récupère dans le contexte les informations 
#    # sur les noms de l'hôte et du service, et l'état.
#    # Elles ont en effet pu être modifiées par les règles.
#    info_dictionary["host"] = ctx.hostname
#    info_dictionary["service"] = ctx.servicename
#    info_dictionary["state"] = ctx.statename
    
    # On publie sur le bus XMPP l'état de l'hôte
    # ou du service concerné par l'alerte courante.
    publish_state(manager.out_queue, info_dictionary)
    
    # Pour les services de haut niveau, on s'arrête ici,
    # on NE DOIT PAS générer d'événement corrélé.
    if info_dictionary["host"] == settings['correlator']['nagios_hls_host']:
        return rule_runners_pool

    make_correvent(manager, conn, xml)
    transaction.commit()
    transaction.begin()
    
    return rule_runners_pool
        

def main(manager):
    """
    Lit les messages sur le bus, en extrait l'information pour
    l'insérer dans le contexte, exécute les règles de corrélation
    avant de lancer la création des événements corrélés.
    """
    import signal
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

    # On instancie le registre dès le début (il s'agit d'un singleton), afin
    # que les règles ne s'enregistrent qu'une seule fois (au lieu de quoi elles
    # s'enregistreraient à chaque traitement d'une règle dans le rule_runner).
    get_registry()

    # On annule le join_thread() réalisé automatiquement par multiprocessing
    # sur les files à la fin de l'exécution du processus. Ceci évite un
    # blocage du rule dispatcher (et donc du corrélateur).
    manager.in_queue.cancel_join_thread()
    manager.out_queue.cancel_join_thread()

    # On se connecte au serveur MemcacheD
    conn = connect()

    # This flag can be used to turn off multiprocessing/multithreading
    # completely, running the rules in a serial fashion.
    # This can be useful when multiprocessing exits with '#TRACEBACK' messages.
    try:
        debugging = settings['correlator'].as_bool('debug')
    except KeyError:
        debugging = False

    if not debugging:
        rule_runners_pool = create_rule_runners_pool(manager.out_queue)
    else:
        rule_runners_pool = None

    # Prépare les schémas de validation XSD.
    try:
        validate = settings['correlator'].as_bool('validate_messages')
    except KeyError:
        validate = False

    if validate:
        schema_file = pkg_resources.resource_stream(
                'vigilo.pubsub', 'data/schemas/event1.xsd')
        catalog_fname = pkg_resources.resource_filename(
                'vigilo.pubsub', 'data/catalog.xml')
        # We override whatever this was set to.
        os.environ['XML_CATALOG_FILES'] = catalog_fname
        schema = etree.XMLSchema(file=schema_file)
    else: 
        schema = None

    # Tant que l'événement demandant l'arrêt
    # n'est pas actif, on traite des messages.

    # Boucle d'attente d'un message provenant du bus XMPP.
    while True:
        try:
            # On tente de récupérer un message.
            xml = manager.in_queue.get(block=True)

        except IOError, e:
            # Si le get() a été interrompu par un signal,
            # on recommence l'attente.
            if e.errno != errno.EINTR:
                raise
            continue

        # Si on obtient un message à traiter, on sort de l'attente.
        else:
            # Si le message demande l'arrêt, on s'arrête.
            if xml == None:
                LOGGER.debug(_('Received request to shutdown '
                                'the Rule dispatcher.'))
                if rule_runners_pool:
                    rule_runners_pool.close()
                break

            rule_runners_pool = handle_bus_message(manager,
                conn, schema, rule_runners_pool, xml)

    # On tue le pool de rule_runners.
    if rule_runners_pool is not None:
        rule_runners_pool.terminate()
        rule_runners_pool.join()

    LOGGER.debug(_('Closed the pool, closing queues.'))

    # Marque les files comme n'étant plus utilisées.
    manager.in_queue.close()
    manager.out_queue.close()

    LOGGER.debug(_('Stopping the Rule dispatcher.'))

