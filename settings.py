# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from twisted.words.protocols.jabber.jid import JID

MEMCACHE_CONN_TYPE = 'inet'
MEMCACHE_CONN_HOST = 'localhost'
# Non-standard, do not interfere with a global instance.
MEMCACHE_CONN_PORT = 11215

PLUGINS_ENABLED = (
    'vigilo.corr.rules.same_target_same_time_interval',
    'vigilo.corr.rules.topo_deps',
    'vigilo.corr.rules.high_level_state',
    )

# Set to None to connect using the CORR_JID host and SRV records.
XMPP_SERVER_HOST = 'localhost'
XMPP_PUBSUB_SERVICE = JID('pubsub.localhost')
# Respect the ejabberd namespacing, for now. It will be too restrictive soon.
#VIGILO_ALERTS_TOPIC = '/vigilo/alerts'
VIGILO_ALERTS_TOPIC = '/home/localhost/correlator/alerts'
VIGILO_CORRALERTS_TOPIC = '/home/localhost/correlator/corralerts'
VIGILO_CORR_JID = JID('correlator@localhost')
VIGILO_CORR_PASS = 'coloration'

