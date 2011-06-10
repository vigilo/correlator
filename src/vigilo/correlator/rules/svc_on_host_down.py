# -*- coding: utf-8 -*-
# vim: set et ts=4 sw=4:
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Gestion de l'état des service d'un hôte DOWN.

Lorsque Nagios détecte qu'un hôte est DOWN, il n'envoie une notification que
sur l'hôte lui-même. Cette règle permet de marquer tous les services de cet
hôte comme UNKNOWN, et de re-demander leur état lorsque l'hôte est rétabli.

Cette règle s'active en ajoutant dans la section [rules] la ligne
suivante ::

    svc_on_host_down = vigilo.correlator.rules.svc_on_host_down:SvcHostDown

"""

import time
from datetime import datetime#, timedelta
#from sqlalchemy.sql.expression import desc
from twisted.internet import defer

from vigilo.common.conf import settings
settings.load_module("vigilo.correlator")

from vigilo.correlator.rule import Rule

from vigilo.models.session import DBSession
from vigilo.models.tables import StateName, Host, LowLevelService#, HighLevelService, HLSHistory

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

#from vigilo.connector import MESSAGEONETOONE
from vigilo.pubsub.xml import NS_COMMAND
from vigilo.correlator import amp
from vigilo.correlator.db_insertion import insert_state

LOGGER = get_logger(__name__)
_ = translate(__name__)


NAGIOS_MESSAGE = """
<command xmlns="%(ns)s">
    <timestamp>%(timestamp)d</timestamp>
    <cmdname>SEND_CUSTOM_SVC_NOTIFICATION</cmdname>
    <value>%(host)s;%%(svc)s;4;Vigilo;Host came up</value>
</command>
"""

class SvcHostDown(Rule): # pylint: disable-msg=W0232
    """
    Règle de gestion des services dont l'hôte est DOWN.

    Si l'hôte passe DOWN: on marque tous ses services comme UNKNOWN
    Si l'hôte passe UP : on demande à Nagios l'état de ses services
    """

    @defer.inlineCallbacks
    def process(self, link, xmpp_id, payload): # pylint: disable-msg=W0613
        """
        Traitement du message par la règle.

        @param link: Objet servant de lien avec le dispatcher et pouvant
            par exemple être utilisé pour envoyer des messages XML sur
            le bus XMPP.
        @type link: C{vigilo.correlator.actors.rule_runner.RuleRunner}
        @param xmpp_id: Identifiant XMPP de l'alerte brute traitée.
        @type xmpp_id: C{unicode}
        @param payload: Le message reçu par le corrélateur sur le bus XMPP.
        @type payload: C{unicode}
        """

        ctx = self._get_context(xmpp_id)
        hostname = yield ctx.get('hostname')
        servicename = yield ctx.get('servicename')

        if servicename or not hostname:
            return # On ne traite que les évènements sur les hôtes

        statename = yield ctx.get('statename')
        previous_state = yield ctx.get('previous_state')
        if previous_state is None:
            previous_statename = "UP" # inconnu = UP
        else:
            previous_statename = StateName.value_to_statename(previous_state)
        if statename == previous_statename:
            return # Pas de changement

        if previous_statename == "UP" and statename == "DOWN":
            yield self._on_host_down(hostname, ctx)
        elif previous_statename == "DOWN" and statename == "UP":
            self._on_host_up(hostname, link)
        else:
            LOGGER.debug("%s: unsupported transition: %s -> %s", __name__,
                         previous_statename, statename)

    def _get_all_services(self, hostname):
        return DBSession.query(LowLevelService).join(
                    (Host, Host.idsupitem == LowLevelService.idhost)
                ).filter(Host.name == unicode(hostname)
                ).all()

    @defer.inlineCallbacks
    def _on_host_down(self, hostname, ctx):
        timestamp = yield ctx.get('timestamp')
        timestamp = datetime.fromtimestamp(timestamp)
        message = _("Host is down")
        services = self._get_all_services(hostname)
        LOGGER.debug("%s: setting %d services to UNKNOWN",
                     __name__, len(services))
        for svc in services:
            insert_state({
                    "host": hostname,
                    "service": svc.servicename,
                    "message": message,
                    "timestamp": timestamp,
                    "state": "UNKNOWN",
                    })

    def _on_host_up(self, hostname, link):
        message_tpl = NAGIOS_MESSAGE % {
            "ns": NS_COMMAND,
            "timestamp": int(time.mktime(datetime.now().timetuple())),
            "host": hostname,
        }
        services = self._get_all_services(hostname)
        LOGGER.debug("%s: asking Nagios for updates on %d services",
                     __name__, len(services))
        for svc in services:
            link.callRemote(amp.SendToBus,
                            item=message_tpl % {"svc": svc.servicename})
