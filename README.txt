VigiRules (correlator)
======================

VigiRules (ou Correlator) est le corrélateur d'évènements de Vigilo. Il est
abonné au bus de messages d'où il reçoit les messages émis par Nagios, et où
il émet les messages résultants de la corrélation.

VigiRules est aussi connecté à la base de données Vigilo pour effectuer la
corrélation et y insérer les événements bruts et les événements corrélés.

Pour les détails du fonctionnement de VigiRules, se reporter à la
`documentation officielle`_.


Dépendances
-----------
Vigilo nécessite une version de Python supérieure ou égale à 2.5. Le chemin de
l'exécutable python peut être passé en paramètre du ``make install`` de la
façon suivante::

    make install PYTHON=/usr/bin/python2.6

Le corrélateur VigiRules a besoin des modules Python suivants :

- setuptools (ou distribute)
- vigilo-common
- vigilo-connector
- vigilo-models
- memcached
- networkx


Installation
------------
L'installation se fait par la commande ``make install`` (à exécuter en
``root``).


License
-------
VigiRules est sous licence `GPL v2`_.


.. _documentation officielle: Vigilo_
.. _Vigilo: https://www.vigilo-nms.com
.. _GPL v2: http://www.gnu.org/licenses/gpl-2.0.html

.. vim: set syntax=rst fileencoding=utf-8 tw=78 :
