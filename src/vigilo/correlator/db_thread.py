# -*- coding: utf-8 -*-
# Copyright (C) 2011-2013 CS-SI
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Ce module permet d'encapsuler les échanges avec la base de données
de Vigilo dans un processus léger (thread) séparé.

L'idée vient de http://markmail.org/message/22wlumhabfuh2plj
mais a été adaptée pour utiliser les outils spécifiques
fournis par Twisted pour la gestion des processus léger.
"""

import Queue

from twisted.internet import reactor
from twisted.internet import defer
from twisted.internet import threads
from twisted.python.failure import Failure

import transaction

class DatabaseWrapper(object):
    """
    Cette classe permet de gérer tous les accès à la base de données
    au travers d'un processus léger (thread) dédié.
    """

    def __init__(self, settings):
        """
        Crée un thread dédié à la gestion de la base de données.
        Cette méthode configure également la session d'accès à
        la base de données pour qu'elle soit partagée entre les
        threads.

        @param settings: Options de configuration du corrélateur,
            contenant en particulier les options relatives à la
            base de données (préfixées par "sqlalchemy_").
        @type settings: C{dict}
        """
        from vigilo.models.configure import configure_db
        self.engine = configure_db(settings, 'sqlalchemy_')

        from sqlalchemy.orm import sessionmaker
        from zope.sqlalchemy import ZopeTransactionExtension
        from vigilo.models import session

        # On remplace l'objet DBSession par une session partagée
        # entre les threads. L'idée est que tous les threads peuvent
        # s'en servir pour générer des Query, mais seul le thread
        # géré par cette classe peut s'en servir pour exécuter le SQL.
        session.DBSession = sessionmaker(
            autoflush=True,
            autocommit=False,
            extension=ZopeTransactionExtension()
        )()

        self.queue = Queue.Queue()
        self.defer = threads.deferToThread(self._db_thread)

    def __del__(self):
        """
        Cette méthode se contente d'appeler L{DatabaseWrapper.shutdown}
        lorsque l'objet est détruit afin de s'assurer que le thread créé
        dans le constructeur est bien arrêté.
        """
        self.shutdown()

    def _db_thread(self):
        """
        Cette méthode est exécutée dans un thread séparé.
        C'est elle qui traite les demandes d'opérations sur la base de données
        et retourne les résultats sous la forme d'un objet C{Deferred}.

        @note: Cette méthode ne retourne pas tant que la méthode
            L{DatabaseWrapper.shutdown} n'a pas été appelée.
        """
        from vigilo.common.logging import get_logger
        from vigilo.common.gettext import translate

        logger = get_logger(__name__)
        _ = translate(__name__)

        while True:
            op = self.queue.get()
            if op is None:
                return
            else:
                func, args, kwargs, d, txn = op

            if txn:
                transaction.begin()
            try:
                result = d.callback, func(*args, **kwargs)
                if txn:
                    transaction.commit()
            except Exception:
                if txn:
                    transaction.abort()
                result = d.errback, Failure()
            self.queue.task_done()
            reactor.callFromThread(*result)

    def run(self, func, *args, **kwargs):
        """
        Cette méthode reçoit les demandes d'accès destinées à la base
        de données et les transmet au thread dédié à cette fonction.

        @param func: La fonction à exécuter qui utilise la base de données.
        @type func: C{callable}
        @note: Les arguments supplémentaires passés à cette méthode
            sont transmis à la fonction indiquée par C{func} lorsque
            celle-ci est appelée.
        @note: Cette méthode accepte également un paramètre nommé
            C{transaction} qui indique si le traitement doit avoir
            lieu dans une transaction ou non.
        @return: Un Deferred qui sera appelé avec le résultat de
            l'exécution de la fonction.
        @rtype: L{defer.Deferred}
        """
        result = defer.Deferred()
        txn = kwargs.pop('transaction', True)
        self.queue.put((func, args, kwargs, result, txn))
        return result

    def shutdown(self):
        """
        Arrête le thread dédié à la gestion des accès
        à la base de données.
        """
        self.queue.put(None)
        return self.defer


class DummyDatabaseWrapper(object):
    """
    Une classe ayant la même API que la classe L{DatabaseWrapper}
    et pouvant être utilisée en lieu et place de celle-ci lorsqu'il
    n'est pas utile de déléguer les accès à la base de données à un
    processus léger dédié (ie. dans les tests unitaires et dans les
    règles de corrélation).
    """

    def __init__(self, disable_txn=False, async=True):
        """
        Créer le wrapper autour des accès.

        @param disable_txn: Désactive globalement les transactions,
            en ignorant la valeur de l'option C{transaction}
            éventuellement passée à la méthode L{DummyDatabaseWrapper.run}.
            Ce paramètre est surtout utile dans les tests unitaires pour
            éviter que les bases de données en mémoire ne soient perdues
            après un commit.
        @type disable_txn: C{bool}
        """
        from vigilo.common.logging import get_logger
        from vigilo.common.gettext import translate

        self.logger = get_logger(__name__)
        self.gettext = translate(__name__)
        self.disable_txn = disable_txn
        self.async = async

    def _return(self, result):
        if self.async:
            if isinstance(result, Failure):
                return defer.fail(result)
            else:
                return defer.succeed(result)
        else:
            if isinstance(result, Failure):
                raise result.value
            else:
                return result

    def run(self, func, *args, **kwargs):
        """
        Exécute une fonction interagissant avec la base de données.


        @param func: La fonction à exécuter qui utilise la base de données.
        @type func: C{callable}
        @note: Les arguments supplémentaires passés à cette méthode
            sont transmis à la fonction indiquée par C{func} lorsque
            celle-ci est appelée.
        @note: Cette méthode accepte également un paramètre nommé
            C{transaction} qui indique si le traitement doit avoir
            lieu dans une transaction ou non. Si le paramètre C{disable_txn}
            a été positionné à True à l'initialisation de l'objet,
            le traitement NE SERA PAS encapsulé dans une transaction,
            quelle que soit la valeur de ce paramètre.
        @return: Un Deferred qui sera appelé avec le résultat de
            l'exécution de la fonction.
        @rtype: L{defer.Deferred}
        """
        from vigilo.common.logging import get_logger
        logger = get_logger(__name__)

        txn = kwargs.pop('transaction', True) and not self.disable_txn
        if txn:
            transaction.begin()
        try:
            res = func(*args, **kwargs)
            if txn:
                transaction.commit()
        except KeyboardInterrupt:
            raise
        except:
            res = Failure()
            if txn:
                transaction.abort()
            self.logger.error(res)
        return self._return(res)

    def shutdown(self):
        """
        Cette méthode ne fait rien, elle est fournie uniquement
        pour respecter l'API de la classe L{DatabaseWrapper}.
        """
        pass
