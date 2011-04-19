# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2011 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Prend en charge les messages concernant les mises en silence.
"""

#from sqlalchemy import not_, or_
#import transaction
#
#from vigilo.models.session import DBSession
#from vigilo.models.tables import Downtime, DowntimeStatus
#
#import re
#
#from vigilo.common.logging import get_logger
#LOGGER = get_logger(__name__)
#
#from vigilo.common.gettext import translate
#_ = translate(__name__)
#
#
#def handle_downtime(info_dictionary):
#    """
#    Met à jour le statut d'une opération de mise en silence dans la base
#    de données grâce aux informations envoyées par Nagios sur le bus XMPP.
#
#    @param info_dictionary: Dictionnaire contenant les
#    informations extraites du message reçu par le rule dispatcher.
#    @type info_dictionary: C{dictionary}
#    """
#    LOGGER.debug(_(u'handle_downtime: Downtime message received. '
#                 'Timestamp = %r. Host = %r. Service = %r. '
#                 'Type = %r. Author = %r. Comment = %r.' % 
#                 (info_dictionary["timestamp"], info_dictionary["host"],
#                  info_dictionary["service"], info_dictionary["type"],
#                  info_dictionary["author"], info_dictionary["comment"])))
#    
#    # On récupère l'identifiant de la mise en silence
#    # concernée en le séparant du reste du commentaire
#    match = re.match ("\[(?P<id>\d*)\]\s(?P<comment>.*)",
#                            info_dictionary["comment"])
#    if match:
#        downtime_id = match.group('id')
#        comment = match.group('comment')
#    else:
#        LOGGER.error(_(u'handle_downtime: Message concerning a non ' 
#                       'configured downtime on item (%r, %r), skipping')% 
#                       (info_dictionary["host"], info_dictionary["service"]))
#        return
#
#    # On cherche dans la BDD la mise en silence associée à cet identifiant.
#    downtime = DBSession.query(
#                Downtime
#            ).filter(Downtime.iddowntime == downtime_id
#            ).filter(not_(or_(
#                    Downtime.idstatus == 
#                        DowntimeStatus.status_name_to_value(u'Finished'),
#                    Downtime.idstatus == 
#                        DowntimeStatus.status_name_to_value(u'Cancelled')
#                ))
#            ).first()
#    if downtime:
#        LOGGER.debug(_(u'handle_downtime: Maching downtime : %r' 
#                        % downtime.iddowntime))
#    else:
#        LOGGER.error(_(u'handle_downtime: No matching downtime found : %r' % 
#                   downtime_id))
#        return         
#                 
#    # Traitement du message en fonction de l'opération souhaitée :
#    
#    # - Si le message est de type 'DOWNTIMESTART';
#    if info_dictionary["type"] == u'DOWNTIMESTART':
#        
#        # Si la mise en silence était déjà commencée,
#        # on loggue une erreur et on ignore le message.
#        if downtime.idstatus == DowntimeStatus.status_name_to_value(
#                                                                u'Active'): 
#            LOGGER.error(_(u'handle_downtime: Downtime has already started, '
#                                'skipping the message'))
#            return
#        
#        # Sinon on met à jour le statut de la mise en silence.
#        else:
#            LOGGER.debug(_(u'handle_downtime: Downtime status was : %r' 
#                            % downtime.idstatus))
#            downtime.idstatus = DowntimeStatus.status_name_to_value(u'Active')
#    
#    
#    # - Sinon, si le message est de type 'DOWNTIMEEND';
#    elif info_dictionary["type"] == u'DOWNTIMEEND':
#        
#        # Si la mise en silence n'était pas encore commencée,
#        # on loggue une erreur et on ignore le message.
#        if downtime.idstatus == DowntimeStatus.status_name_to_value(
#                                                                u'Scheduled'):
#            LOGGER.error(_(u'handle_downtime: Downtime has not started yet, '
#                                'skipping the message'))
#            return
#        
#        # Sinon on met à jour le statut de la mise en silence.
#        else:
#            LOGGER.debug(_(u'handle_downtime: Downtime status was : %r' 
#                            % downtime.idstatus))
#            downtime.idstatus = DowntimeStatus.status_name_to_value(
#                                                                u'Finished')
#    
#    
#    # - Sinon, si le message est de type 'DOWNTIMECANCELLED';
#    elif info_dictionary["type"] == u'DOWNTIMECANCELLED':
#        # On met à jour le statut de la mise en silence.
#        LOGGER.debug(_(u'handle_downtime: Downtime status was : %r' 
#                            % downtime.idstatus))
#        downtime.idstatus = DowntimeStatus.status_name_to_value(u'Cancelled')
#    
#    
#    # - Sinon, le message est invalide.
#    else:
#        LOGGER.error(_(u'handle_downtime: received an invalid message: '
#                     '%r, skipping' % info_dictionary["type"]))
#        return
#    
#    DBSession.flush()
#    LOGGER.debug(_(u'handle_downtime: Downtime status set to : %r' 
#                            % downtime.idstatus))
#    transaction.commit()
#    transaction.begin()
#    return
#    
#    
#    
