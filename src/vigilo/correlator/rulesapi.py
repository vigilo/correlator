# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
The rules API is a small api rules can safely use.
"""

from vigilo.correlator import context, connect

# Codes d'erreurs
ENOERROR = 0
ETIMEOUT = -1
EEXCEPTION = -2

class Timer(object):
    """
    Timers are used to trigger plugin calls at a specific time.
    """

    pass

class Api(object):
    """API utilisée par les règles"""
    Timer = Timer

    def __init__(self, queue=None, conn=None):
        if conn is None:
            conn = connect.connect()
        self.__conn = conn
        self.__queue = queue

    def get_or_create_context(self, idnt):
        """
        Récupère le contexte associé à une alerte ou le crée si nécessaire.
        """
        return context.Context.get_or_create(self.__conn, self.__queue, idnt)

    def send_to_bus(self, payload):
        """Envoie un message sur le bus XMPP"""
        self.__queue.put_nowait(payload)

