#!/usr/bin/env python
# vim: set fileencoding=utf-8 sw=4 ts=4 et :
from distutils.command.bdist_rpm import bdist_rpm as _bdist_rpm
from distutils.core import setup
from distutils.dist import Distribution as _Distribution

class Distribution(_Distribution, object):
    def __init__ (self, attrs=None):
        if attrs is not None and 'install_requires' in attrs:
            self.__install_requires = attrs.pop('install_requires')
        super(Distribution, self).__init__(attrs)

    def get_install_requires(self):
        return self.__install_requires

class bdist_rpm(_bdist_rpm, object):
    """
    Generates rpm dependency requirements for python dependencies.
    """

    """
    XXX Maybe this should be moved out.
    The mappings are distro-specific, we need m name mappings × n eggs.
    Could fit into buildout, paver, etc, and possibly use pip.
    """

    user_options = _bdist_rpm.user_options + [
            ('no-translate-req', None,
                'do not translate distutils/setuptools dependencies into rpm dependencies'),
            ]

    boolean_options = _bdist_rpm.boolean_options + ['no-translate-req', ]

    def initialize_options(self):
        super(bdist_rpm, self).initialize_options()
        self.no_translate_req = 0

    def finalize_options(self):
        super(bdist_rpm, self).finalize_options()
        if self.no_translate_req:
            return
        # The distutils consensus
        distutils_requires = self.distribution.get_requires()
        # The setuptools consensus, unfortunately there's a difference
        setuptools_requires = self.distribution.get_install_requires()
        raw_requires = distutils_requires + setuptools_requires
        if self.requires is None:
            self.requires = []
        for raw_req in raw_requires:
            req = raw_req
            self.requires.append(req)

setup(name='vigilo-correlator',
        version='0.1',
        author='Gabriel de Perthuis',
        author_email='gabriel.de-perthuis@c-s.fr',
        url='http://www.projet-vigilo.org/',
        description='vigilo correlation component',
        license='http://www.gnu.org/licenses/gpl-2.0.html',
        long_description='The vigilo correlation engine aggregates vigilo\n'
        +'alerts to reduce information overload and help point out\n'
        +'the cause of a problem.\n',
        install_requires=[
            # dashes become underscores
            # order is important (wokkel before Twisted)
            'coverage',
            'nose',
            'pylint',

            'multiprocessing',
            'pylibmc',
            'python_memcached',
            'python_libmemcached',
            'PyYAML',
            'rel',
            'vigilo-common-pubsub',
            'wokkel',
            'Twisted',
            ],
        namespace_packages = [
            'vigilo',
            'vigilo.common',
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
                'vigilo-config = vigilo.corr.conf:main',
                ],
            },
        package_dir={'': 'src'},
        cmdclass={'bdist_rpm': bdist_rpm, },
        distclass=Distribution,
        )

