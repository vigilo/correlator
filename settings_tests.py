# vim: set fileencoding=utf-8 sw=4 ts=4 et :
import logging

MEMCACHE_SRV_COMMAND = '/usr/sbin/memcached'
MEMCACHE_CONN_TYPE = 'inet'
PLUGINS_ENABLED = ()
LOGGING_PLUGINS = (
        'vigilo.pubsub.logging',
        'vigilo.corr.logging',
        )
LOGGING_SETTINGS = {}
LOGGING_LEVELS = {}
LOGGING_SYSLOG = False

## Set to None to connect using the CORR_JID host and SRV records.
XMPP_SERVER_HOST = 'localhost'
XMPP_PUBSUB_SERVICE = 'pubsub.localhost'
#
VIGILO_TESTALERTS_TOPIC = '/home/localhost/correlator.tests/testalerts'
VIGILO_CORR_JID = 'correlator.tests@localhost'
VIGILO_CORR_PASS = 'coloration'
