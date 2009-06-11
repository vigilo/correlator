# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from twisted.words.protocols.jabber.jid import JID

from settings import *

# Respect the ejabberd namespacing, for now.
VIGILO_ALERTS_TOPIC = '/home/localhost/correlator.tests/alerts'
VIGILO_CORRALERTS_TOPIC = '/home/localhost/correlator.tests/corralerts'
VIGILO_TESTALERTS_TOPIC = '/home/localhost/correlator.tests/testalerts'
VIGILO_CORR_JID = JID('correlator.tests@localhost')
VIGILO_CORR_PASS = 'coloration'

