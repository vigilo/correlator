# vim: set fileencoding=utf-8 sw=4 ts=4 et :
# Copyright (C) 2006-2020 CS GROUP - France
# License: GNU GPL v2 <http://www.gnu.org/licenses/gpl-2.0.html>

"""
Un module permettant de gérer les règles de corrélation
ainsi que les dépendances entre ces règles.
"""

import sys
import pkg_resources

from vigilo.correlator.datatypes import Named
from vigilo.correlator.rule import Rule

from vigilo.common.conf import settings
from vigilo.common.logging import get_logger
from vigilo.common.gettext import translate
from vigilo.common.nx import networkx

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
            raise TypeError()
        if not isinstance(item, self.__pytype):
            raise TypeError()

        if item.name in self.__dict:
            LOGGER.info(_('Rule %(name)s (%(class)s) has already been '
                           'registered, ignoring attempt to re-register it.'),
                        {"name": item.confkey, "class": item.__class__})
            return

        self.__graph.add_node(item.name)
        for dep in item.depends:
            if self.__graph.has_node(dep):
                try:
                    path = networkx.shortest_path(self.__graph, dep, item.name)
                    path.append(path[0])
                    LOGGER.error(_('Cyclic dependencies found: %(path)s') % {
                                    'path': " -> ".join(path),
                                })
                    raise RuntimeError()
                except networkx.NetworkXNoPath:
                    pass
            self.__graph.add_edge(item.name, dep)

        self.__dict[item.name] = item
        LOGGER.debug(_('Successfully registered rule %r'), item.name)

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

    def __len__(self):
        """
        @return: le nombre de règles enregistrées.
        @rtype: C{int}
        """
        return len(self.__dict)

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
            LOGGER.warning(_('Singleton has already been instanciated, '
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
        self._load_from_settings()
        self.check_dependencies()

    def _load_from_settings(self):
        """Charge le registre depuis le fichier de settings"""

        # permet de placer les règles directement dans le dossier de plugins
        if "correlator" not in settings:
            return
        plugins_path = settings["correlator"].get("pluginsdir",
                                "/etc/vigilo/correlator/plugins")
        sys.path.append(plugins_path)

        for rule_name, rule_class in settings.get('rules', {}).iteritems():
            try:
                ep = pkg_resources.EntryPoint.parse('%s = %s'
                                            % (rule_name, rule_class))
            except ValueError:
                LOGGER.error(_('Not a valid rule name "%s"'), rule_name)
                continue

            try:
                rule = ep.load(False)
            except ImportError:
                LOGGER.error(_('Unable to load rule "%(name)s" (%(class)s)'),
                             {"name": rule_name, "class": rule_class})
                continue

            self.rules.register(rule(confkey=rule_name))

        del sys.path[-1]

    def check_dependencies(self):
        """
        Vérifie que les dépendances des règles sont bien respectées.

        Lève une RuntimeException si ce n'est pas le cas.
        """
        graph = self.__rules.rules_graph
        diff = set(graph.nodes()) - set(self.__rules.keys())
        for dependency in diff:
            for rule in graph.predecessors(dependency):
                LOGGER.error(_( 'The rule "%(rule)s" depends on the rule '
                                '"%(dependency)s", which has not been '
                                'loaded.') % {
                                    'rule': rule,
                                    'dependency': dependency,
                                })
            raise RuntimeError()

    @property
    def rules(self):
        """Renvoie un wrapper autour d'un dict des règles de corrélation."""
        return self.__rules

def get_registry():
    """Renvoie l'instance globale du registre des règles de corrélation."""
    return Registry.global_instance()
