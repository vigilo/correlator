#!/usr/bin/env python
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
import os
from setuptools import setup

tests_require = [
    'coverage',
    'nose',
    'pylint',
]

sysconfdir = os.getenv("SYSCONFDIR", "/etc")
localstatedir = os.getenv("LOCALSTATEDIR", "/var")

def install_i18n(i18ndir, destdir):
    data_files = []
    langs = []
    for f in os.listdir(i18ndir):
        if os.path.isdir(os.path.join(i18ndir, f)) and not f.startswith("."):
            langs.append(f)
    for lang in langs:
        for f in os.listdir(os.path.join(i18ndir, lang, "LC_MESSAGES")):
            if f.endswith(".mo"):
                data_files.append(
                        (os.path.join(destdir, lang, "LC_MESSAGES"),
                         [os.path.join(i18ndir, lang, "LC_MESSAGES", f)])
                )
    return data_files


setup(name='vigilo-correlator',
        version='2.0.0',
        author='Vigilo Team',
        author_email='contact@projet-vigilo.org',
        url='http://www.projet-vigilo.org/',
        description='vigilo correlation component',
        license='http://www.gnu.org/licenses/gpl-2.0.html',
        long_description='The vigilo correlation engine aggregates vigilo\n'
        +'alerts to reduce information overload and help point out\n'
        +'the cause of a problem.\n',
        install_requires=[
            # dashes become underscores
            'setuptools',
            'lxml',
            'psycopg2',
            # @TODO Doit-on utiliser twisted.protocols.memcache à la place ?
            'python-memcached',
            'vigilo-models',
            'vigilo-pubsub',
            'vigilo-connector',
            'networkx',
            'ampoule',
            ],
        extras_require={
            'tests': tests_require,
            },
        namespace_packages = [
            'vigilo',
            ],
        packages=[
            'vigilo',
            'vigilo.correlator',
            'vigilo.correlator.actors',
            'vigilo.correlator.rules',
            ],
        entry_points={
            'console_scripts': [
                'vigilo-correlator = vigilo.correlator.main:main',
                ],
            },
        package_dir={'': 'src'},
        data_files=[
                    (os.path.join(sysconfdir, "vigilo/correlator"),
                        ["settings.ini"]),
                    (os.path.join(localstatedir, "lib/vigilo/correlator"), []),
                    (os.path.join(localstatedir, "run/vigilo-correlator"), []),
                   ] + install_i18n("i18n", "/usr/share/locale"),
        )

