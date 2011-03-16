# -*- coding: utf-8 -*-
# vim: set et ts=4 sw=4:
"""
Gestion de la haute-disponibilité de la plate-forme Vigilo.

Il faut configurer la règle en ajoutant dans le settings.ini une section
similaire à la suivante ::

    [vigilo.correlator.rules.ha]

    # Identifiant jabber du connector-vigiconf
    vigiconf_jid = vigiconf@localhost

    # Préfixe du nom des services représentant l'état des serveurs vigilo
    hls_prefix = vigilo-server:

    # Nom du service indiquant aux administrateurs
    # qu'un redéploiement manuel est nécessaire et nom
    # de l'hôte associé (hébergeant la base de données)
    deployment_service = deployment
    deployment_host = vigilo-admin-server

    # Durée maximale au-delà de laquelle le rétablissement
    # ne peut plus s'opérer de manière automatique
    max_auto_recovery = 15

    # Conversion du nom d'hôte Nagios vers le nom dans appgroups-servers.py
    #server_template = %s.vigilo.example.com

Il faut aussi activer la règle en ajoutant dans la section [rules] la ligne suivante ::

    ha = vigilo.correlator.rules.ha:HighAvailabilityRule

"""

from vigilo.correlator.rule import Rule
from vigilo.correlator.context import Context

from vigilo.common.conf import settings
settings.load_module(__name__)

from vigilo.models.session import DBSession
from vigilo.models.tables import StateName, HighLevelService, HLSHistory
import time
from datetime import datetime, timedelta
from sqlalchemy.sql.expression import desc

from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

from vigilo.connector import MESSAGEONETOONE
from vigilo.pubsub.xml import NS_COMMAND
from vigilo.correlator.actors import rule_dispatcher

LOGGER = get_logger(__name__)
_ = translate(__name__)


class MissingConfig(Exception):
    pass

class HighAvailabilityRule(Rule):

    def __init__(self):
        super(HighAvailabilityRule, self).__init__([])

    def check_config(self):
        """Vérification de la bonne configuration de la règle."""
        if __name__ not in settings:
            message = _('The rule "%(rule)s" requires a section called '
                        '"%(section)s" be present in the configuration '
                        'file. Skipping this rule until the configuration '
                        'gets fixed!') % {
                            'rule': '%s:%s' % (
                                __name__,
                                self.__class__.__name__
                            ),
                            'section': __name__,
                        }
            raise MissingConfig(message)
        for param in ('vigiconf_jid', 'hls_prefix'):
            if param not in settings[__name__]:
                message = _('The rule "%(rule)s" requires a parameter '
                            'called "%(param)s" under the section '
                            '[%(section)s]. Skipping this rule until '
                            'its configuration gets fixed!') % {
                                'rule': '%s:%s' % (
                                    __name__,
                                    self.__class__.__name__
                                ),
                                'section': __name__,
                                'param': param,
                            }
                raise MissingConfig(message)

    def process(self, link, xmpp_id, payload):
        try:
            self.check_config()
        except MissingConfig, e:
            LOGGER.warning(str(e))
            return

        ctx = Context(xmpp_id)
        if ctx.hostname is not None:
            return # On ne traite que les services de haut niveau
        prefix = settings[__name__]["hls_prefix"]
        if not ctx.servicename.startswith(prefix):
            return # rien à faire
        server = ctx.servicename[len(prefix):]

        if ctx.previous_state is not None:
            previous_statename = None
        else:
            previous_statename = StateName.value_to_statename(ctx.previous_state)

        if ctx.statename == previous_statename:
            return # Pas de changement

        if ctx.statename == u"OK":
            # On récupère la durée de l'interruption de service.
            previous_state_duration = self._get_previous_state_duration(ctx.servicename)
            threshold = int(settings[__name__].get("max_auto_recovery", 0))
            # Si elle est inférieure à la durée autorisée, on
            # envoie un message à VigiConf pour réactiver le serveur.
            if threshold == 0:
                action = "enable" # Pas de limite
            elif (previous_state_duration and
                    previous_state_duration <= timedelta(minutes=threshold)):
                action = "enable"
            # Sinon, une intervention manuelle sera nécessaire.
            else:
                LOGGER.warning(_("Vigilo server %(server)s was disabled for "
                    "too long (%(duration)s) before becoming avalaible "
                    "again, a manual VigiConf deployment will be necessary."),
                    { "server": server,
                      "duration": previous_state_duration
                    })
                message = self._build_nagios_message()
                link.callRemote(rule_dispatcher.SendToBus, item=message)
                return

        elif ctx.statename == u"CRITICAL":
            action = "disable"
        else:
            LOGGER.info(_("Unsupported state: %s"), ctx.statename)
            return

        LOGGER.info(_("Flagging Vigilo server %(server)s with status "
                      "%(status)s"), {"server": server, "status": action})

        server = self._get_server_name(server)
        message = self._build_vigiconf_message(server, action)
        link.callRemote(rule_dispatcher.SendToBus, item=message)

    def _get_server_name(self, server):
        server_template = settings[__name__].get("server_template", None)
        if server_template is None:
            return server
        else:
            return server_template % server

    def _get_previous_state_duration(self, servicename):
        timestamps = DBSession.query(
            HLSHistory.timestamp
        ).join(
            (HighLevelService, HLSHistory.idhls == HighLevelService.idservice),
        ).filter(HighLevelService.servicename == servicename
        ).order_by(desc(HLSHistory.timestamp))
        try:
            duration = timestamps[0][0] - timestamps[1][0]
        except IndexError:
            return None
        return duration

    def _build_vigiconf_message(self, server, action):
        message = """
            <%(onetoone)s to="%(vigiconf)s">
                <command xmlns="%(ns)s">
                    <cmdname>server-status</cmdname>
                    <arg>%(action)s</arg>
                    <arg>%(server)s</arg>
                </command>
            </%(onetoone)s>
        """ % {
            "onetoone": MESSAGEONETOONE,
            "vigiconf": settings[__name__]["vigiconf_jid"],
            "ns": NS_COMMAND,
            "action": action,
            "server": server,
            }
        return message

    def _build_nagios_message(self):
        message = """
            <command xmlns="%(ns)s">
                <timestamp>%(timestamp)f</timestamp>
                <cmdname>PROCESS_SERVICE_CHECK_RESULT</cmdname>
                <value>%(host)s;%(service)s;%(return_code)s;%(output)s</value>
            </command>
        """ % {
            "ns": NS_COMMAND,
            "timestamp": time.time(),
            "service": settings[__name__]["deployment_service"],
            "host": settings[__name__]["deployment_host"],
            "return_code": 2,
            "output": _("Manual deployment necessary."),
            }
        return message
