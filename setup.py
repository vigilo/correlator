#!/usr/bin/env python
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from distutils.core import setup

setup(name='vigilo-correlator',
        version='0.1',
        author='Gabriel de Perthuis',
        author_email='gabriel.de-perthuis@c-s.fr',
        url='http://www.projet-vigilo.org/',
        description='vigilo correlation component',
        license='http://www.gnu.org/licenses/gpl-2.0.html',
        long_description='The vigilo correlation engine aggregates vigilo\n'
        +'alerts to reduce information overload and help pin out\n'
        +'the cause of a problem.\n',
        install_requires=[
            'multiprocessing',
            'processing',
            'pylibmc',
            'python_memcached',
            'rel',
            'wokkel',
            ],
        packages=[
            'vigilo',
            'vigilo.common',
            'vigilo.corr',
            'vigilo.corr.actors',
            'vigilo.corr.rules',
            ],
        entry_points={
            'console_scripts': [
                'correlator = vigilo.corr.actors.main:main',
                ],
            },
        package_dir={'': 'lib'},
        )

