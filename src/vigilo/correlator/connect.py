# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Connect to our memcached.
"""
from __future__ import absolute_import

__all__ = ( 'connect', )

from .libs import mc

from vigilo.common.logging import get_logger
LOGGER = get_logger(__name__)
from vigilo.common.gettext import translate
_ = translate(__name__)

def __connect():
    """
    Renvoie une connection au serveur memcached.
    Cette fonction met en cache la connexion afin d'éviter
    d'en créer de nouvelles à chaque fois. Elle vérifie en
    outre l'état de la connexion actuelle afin d'en créer
    une nouvelle si celle en cache ne répond plus.
    """

    conn = None

    while True:
        if conn:
            # On teste l'état de la connexion en ajoutant
            # une valeur quelconque avec une durée avant
            # expiration d'une (1) seconde.
            if conn.set('vigilo', '', 1):
                yield conn
                continue
            else:
                # Si l'ajout échoue, la connexion est probablement
                # morte, donc on la clôt.
                LOGGER.error(_('Lost connection to memcached! Reconnecting...'))
                conn.disconnect_all()
        
        from vigilo.common.conf import settings
        host = settings['correlator']['memcached_host']
        port = settings['correlator'].as_int('memcached_port')

        conn_str = '%s:%d' % (host, port)

        # On ne peut pas utiliser isinstance ici
        # car les types n'existent pas toujours.
        mc_type = mc.__name__

        # XXX Choisir une seule librairy pour memcache et éliminer ces tests.
        # La manière d'indiquer à memcache que l'on souhaite activer
        # le support de CAS change en fonction de la librairie utilisée.
        if mc_type == 'cmemcached':
            conn = mc.Client([conn_str], behaviors={'support_cas': 1})

        elif mc_type == 'memcache':
            try:
                debug = settings['correlator'].as_bool('memcached_debug')
            except KeyError:
                debug = False
            conn = mc.Client([conn_str], debug=int(debug))
            conn.behaviors = {'support_cas': 1}

        else:
            # La librairie de base pour memcached en python ne supporte pas CAS.
            conn = mc.Client([conn_str])

        yield conn

# Définition de la vraie fonction de connexion.
connect = __connect().next

