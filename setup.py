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

setup(name='vigilo-correlator',
        version='0.1',
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
            # order is important (wokkel before Twisted)
            'setuptools',
            'lxml', # ElementTree-compatible, validation…
            'multiprocessing >= 2.6.2.1',
            'psycopg2',
            'python-memcached',
            'python-daemon',
            'rel',
            'vigilo-common',
            'vigilo-models',
            'vigilo-pubsub',
            'wokkel',
            'Twisted',
            #'docutils',
            'vigilo-connector',
            'networkx',
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
                'vigilo-correlator = vigilo.correlator.actors.main:main_cmdline',
                ],
            },
        package_dir={'': 'src'},
        data_files=[
                    (os.path.join(sysconfdir, "vigilo/correlator"),
                        ["settings.ini"]),
                    (os.path.join(localstatedir, "lib/vigilo/correlator"), []),
                    (os.path.join(localstatedir, "run/vigilo-correlator"), []),
                   ],
        )

