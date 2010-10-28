# vim: set fileencoding=utf-8 sw=4 ts=4 et :
"""
Un module permettant de gérer les règles de corrélation
ainsi que les dépendances entre ces règles.
"""

import networkx
import pkg_resources

from vigilo.correlator.datatypes import Named
from vigilo.correlator.rule import Rule

from vigilo.common.conf import settings
from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate

LOGGER = get_logger(__name__)
_ = translate(__name__)

__all__ = ( 'get_registry', )


class RegistryDict(object):
    """
    A registry for named items.

    Items must be L{Named}.
    """

    def __init__(self, pytype):
        """
        Initialisation du registre.

        @param pytype: Type python des objets stockés dans le registre.
        @type pytype: C{type}
        """
        self.__dict = {}
        self.__pytype = pytype
        self.__graph = networkx.DiGraph()

    def register(self, item):
        """
        Ajoute un élément dans le registre.

        @param item: Élement à ajouter au registre.
        @type item: C{Named}
        """

        if not isinstance(item, Named):
            raise TypeError
        if not isinstance(item, self.__pytype):
            raise TypeError

        if item.name in self.__dict:
            LOGGER.info(_(u'Rule %r has already been registered, '
                        'ignoring attempt to re-register it.'), item.name)
            return

        self.__graph.add_node(item.name)

        for dep in item.dependancies:
            if dep not in self.__dict:
                raise RuntimeError(_(u'The rule %(depended)r must be loaded '
                                    'before %(dependent)r.') % {
                                        'dependent': item.name,
                                        'depended': dep,
                                    })
            self.__graph.add_edge(item.name, dep)

        self.__dict[item.name] = item
        LOGGER.debug(_(u'Successfully registered rule %r'), item.name)

    def clear(self):
        """Supprime toutes les règles actuellement enregistrées."""
        self.__dict = {}
        self.__graph = networkx.DiGraph()

    def lookup(self, name):
        """"
        Renvoie la règle dont le nom est L{name}.

        @param name: Nom de la règle à retourner.
        @type name: C{str}
        @return La règle portant le nom L{name}.
        @rtype: L{Rule}
        @raise KeyError: Aucune règle portant ce nom n'est enregistrée.
        """
        return self.__dict[name]

    def keys(self):
        """
        Renvoie la liste des noms de règles enregistrées dans le registre.

        @return: La liste des noms des règles enregistrées.
        @rtype: C{list} of C{str}
        """
        return self.__dict.keys()

    def __iter__(self):
        """
        Renvoie une itérateur sur les règles enregistrées.

        @return: Un itérateur sur les règles enregistrées.
        @rtype: C{ValueIterator}
        """
        return self.__dict.itervalues()

    def __repr__(self):
        """
        Retourne la représentation de cet objet.

        @return: La représentation de l'objet.
        @rtype: C{str}
        """
        return '<%s>' % self.__dict

    @property
    def rules_graph(self):
        return self.__graph

class Registry(object):
    """
    A registry for various types and things.
    """

    def __new__(cls):
        """Constructeur des instances de registres."""
        if hasattr(cls, '_global_instance'):
            LOGGER.warning(_(u'Singleton has already been instanciated, '
                            'ignoring attempt to create a new instance.'))
            return cls._global_instance

        inst = super(Registry, cls).__new__(cls)
        cls._global_instance = inst
        return inst

    @classmethod
    def global_instance(cls):
        """
        Renvoie le "singleton" d'une classe donnée.

        @param cls: Classe dont on veut une instance.
        @type cls: C{type}
        @return: Une instance de la classe L{cls} (toujours la même).
        @rtype: L{cls}
        """

        if not hasattr(cls, '_global_instance'):
            cls()
        return cls._global_instance

    def __init__(self):
        """Initialise le registre."""
        self.__rules = RegistryDict(Rule)
        for plugin_name in settings['rules'].itervalues():
            try:
                ep = pkg_resources.EntryPoint.parse('rule = %s' % plugin_name)
            except ValueError:
                LOGGER.error(_('Not a valid rule name "%s"'), plugin_name)
                continue

            try:
                rule = ep.load(False)
            except ImportError:
                LOGGER.error(_('Unable to load rule "%s"'), plugin_name)
                continue

            self.rules.register(rule())

    @property
    def rules(self):
        """Renvoie un wrapper autour d'un dict des règles de corrélation."""
        return self.__rules

def get_registry():
    """Renvoie l'instance globale du registre des règles de corrélation."""
    return Registry.global_instance()
