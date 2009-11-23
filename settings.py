# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
import logging

MEMCACHE_SRV_COMMAND = '/usr/sbin/memcached'
MEMCACHE_CONN_TYPE = 'inet'
MEMCACHE_CONN_HOST = '127.0.0.1'
# Non-standard, do not interfere with a global instance.
MEMCACHE_CONN_PORT = 11215

PLUGINS_ENABLED = (
        'vigilo.corr.rules.priority',
        'vigilo.corr.rules.high_level_state',
#        'vigilo.corr.rules.same_target_same_time_interval',
#        'vigilo.corr.rules.test',
        'vigilo.corr.rules.topo_deps',
        'vigilo.corr.rules.hls_deps',
        'vigilo.corr.rules.lls_deps',
        'vigilo.corr.rules.update_attribute',
        'vigilo.corr.rules.update_occurrences_count',
        )
LOGGING_PLUGINS = (
        'vigilo.pubsub.logging',
        'vigilo.corr.logging',
        )
LOGGING_SETTINGS = {
        # 5 is the 'SUBDEBUG' level.
        'level': logging.INFO,
        'format': '%(levelname)s::%%(processName)s::%(name)s::%(message)s',
        }
LOGGING_LEVELS = {
        'multiprocessing': logging.INFO,
        'rum.basefactory': logging.INFO,
        'twisted': logging.INFO,
        'vigilo.pubsub': logging.INFO,
        'vigilo.corr.db_insertion': logging.DEBUG,
        'vigilo.corr.correvent': logging.DEBUG,
        'vigilo.corr.pubsub': logging.INFO,
        'vigilo.corr.context': logging.INFO,
        'vigilo.corr.actors.twisted': logging.INFO,
        'vigilo.corr.actors.rule_dispatcher': logging.INFO,
        'vigilo.corr.actors.rule_runner': logging.INFO,
        'vigilo.corr.rules': logging.INFO,
        'vigilo.corr.rulesapi': logging.INFO,
        'vigilo.corr.rules.topo_deps': logging.DEBUG,
        'vigilo.corr.rules.hls_deps': logging.DEBUG,
#        'vigilo.corr.rules.lls_deps': logging.DEBUG,
        'vigilo.corr.rules.update_attribute': logging.DEBUG,
        'vigilo.corr.rules.update_occurrences_count': logging.DEBUG,
        #'vigilo.corr.rules.high_level_state': logging.DEBUG,
    }
LOGGING_SYSLOG = False

LOG_TRAFFIC = True

VALIDATE_MESSAGES = False

# Set to None to connect using the CORR_JID host and SRV records.
XMPP_SERVER_HOST = 'localhost'
#XMPP_SERVER_HOST = 'vigilo-dev'
XMPP_PUBSUB_SERVICE = 'pubsub.localhost'

# Liste des nœuds sur lesquels le corrélateur est consommateur.
VIGILO_CORRELATOR_TOPIC_CONSUMER = [
    '/home/localhost/connectorx/state',
    '/home/localhost/connectorx/event',
]
# Liste des nœuds sur lesquels le corrélateur est producteur.
VIGILO_CORRELATOR_TOPIC_OWNER = [
    '/home/localhost/correlator/correvent',
    '/home/localhost/correlator/aggr',
]
# Indique le nœud cible du message en fonction du type.
VIGILO_CORRELATOR_TOPIC_PUBLISHER = {
    'correvent': '/home/localhost/correlator/correvent',
    'aggr': '/home/localhost/correlator/aggr',
}

VIGILO_CORR_JID = 'correlator@localhost'
VIGILO_CORR_PASS = 'correlator'
CORR_DEMO_PERIOD_SECS = 0

VIGILO_CORRELATOR_BACKUP_FILE = '/var/lib/vigilo/correlator/correlator.sqlite'
VIGILO_CORRELATOR_BACKUP_TABLE_FROMBUS = 'frombus'
VIGILO_CORRELATOR_BACKUP_TABLE_TOBUS = 'tobus'

VIGILO_MODELS_BDD_BASENAME = ''
VIGILO_SQLALCHEMY = {
    'url': 'postgres://vigiboard:tandreja@localhost/vigiboard',
}

NAGIOS_HLS_JID = 'connector-nagios@localhost'
NAGIOS_HLS_HOST = 'HLS'

