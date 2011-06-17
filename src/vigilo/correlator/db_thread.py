# -*- coding: utf-8 -*-
"""
Ce module permet d'encapsuler les échanges avec la base de données
de Vigilo dans un thread séparé.

Voir http://markmail.org/message/22wlumhabfuh2plj#query:+page:1+mid:22wlumhabfuh2plj+state:results
"""

import Queue
import threading

from twisted.internet import reactor
from twisted.internet import defer
from twisted.python.failure import Failure

import transaction

class DatabaseWrapper(object):
    def __init__(self, db_settings):
        self.queue = Queue.Queue()
        self.started = threading.Event()
        self.dbthread = threading.Thread(
            target=self._dbThread,
            args=(db_settings, ),
        )
        self.dbthread.setDaemon(True)
        self.dbthread.start()
        self.started.wait()
        self.engine = None

    def __del__(self):
        self.shutdown()
        super(DatabaseWrapper, self).__del__()

    def _dbThread(self, settings):
        from vigilo.common.logging import get_logger
        from vigilo.common.gettext import translate

        logger = get_logger(__name__)
        _ = translate(__name__)

        from vigilo.models.configure import configure_db
        self.engine = configure_db(settings, 'sqlalchemy_')

        from sqlalchemy.orm import sessionmaker
        from zope.sqlalchemy import ZopeTransactionExtension
        from vigilo.models import session

        # On remplace l'objet DBSession par une session partagée
        # entre les threads. L'idée est que tous les threads peuvent
        # s'en servir pour générer des Query, mais seul ce thread-ci
        # peut s'en servir pour exécuter la requête générée.
        session.DBSession = sessionmaker(
            autoflush=True,
            autocommit=False,
            extension=ZopeTransactionExtension()
        )()
        self.started.set()

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
            except:
                if txn:
                    transaction.abort()
                result = d.errback, Failure()
                logger.error(result[1])
            else:
                if txn:
                    transaction.commit()
            reactor.callFromThread(*result)

    def run(self, func, *args, **kwargs):
        result = defer.Deferred()
        txn = kwargs.pop('transaction', True)
        self.queue.put((func, args, kwargs, result, txn))
        return result

    def shutdown(self):
        self.queue.put(None)
        self.dbthread.join(2) 


class DummyDatabaseWrapper(object):
    def __init__(self, disable_txn=False):
        from vigilo.common.logging import get_logger
        from vigilo.common.gettext import translate

        self.logger = get_logger(__name__)
        self.gettext = translate(__name__)
        self.disable_txn = disable_txn

    def run(self, func, *args, **kwargs):
        txn = kwargs.pop('transaction', True) and not self.disable_txn
        if txn:
            transaction.begin()
        try:
            res = func(*args, **kwargs)
        except KeyboardInterrupt:
            raise
        except:
            res = Failure()
            if txn:
                transaction.abort()
            self.logger.error(res)
            return res
        else:
            if txn:
                transaction.commit()
            return defer.succeed(res)

