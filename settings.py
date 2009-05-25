# vim: set fileencoding=utf-8 sw=4 ts=4 et :

MEMCACHE_CONN_TYPE = 'inet'
MEMCACHE_CONN_HOST = 'localhost'
# Non-standard, do not interfere with a global instance.
MEMCACHE_CONN_PORT = 11215

PLUGINS_ENABLED = (
    'vigilo.corr.rules.same_target_same_time_interval',
    'vigilo.corr.rules.topo_deps',
    )

