# vim: set fileencoding=utf-8 sw=4 ts=4 et :
import logging

MEMCACHE_SRV_COMMAND = '/usr/sbin/memcached'
MEMCACHE_CONN_TYPE = 'inet'
PLUGINS_ENABLED = (
)
LOGGING_PLUGINS = (
        'vigilo.pubsub.logging',
        'vigilo.corr.logging',
        )
LOGGING_SETTINGS = {}
LOGGING_LEVELS = {}
LOGGING_SYSLOG = False

## Set to None to connect using the CORR_JID host and SRV records.
XMPP_SERVER_HOST = 'vigilo-dev'
XMPP_PUBSUB_SERVICE = 'pubsub.localhost'

# Nœuds XMPP de tests.
VIGILO_CORRELATOR_TOPIC_OWNER = [
    '/home/localhost/correlator.tests/event',
]

VIGILO_CORR_JID = 'correlator.tests@localhost'
VIGILO_CORR_PASS = 'coloration'

VIGILO_MODELS_BDD_BASENAME = ''
VIGILO_SQLALCHEMY = {
    'url': 'sqlite:///:memory:',
}

NAGIOS_HLS_JID = 'hls@localhost'
NAGIOS_HLS_HOST = 'HLS'

PRIORITY_ORDER = 'desc'
UNKNOWN_PRIORITY_VALUE = 4

