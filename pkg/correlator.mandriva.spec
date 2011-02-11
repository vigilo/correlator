%define module  correlator
%define name    vigilo-%{module}
%define version 2.0.0
%define release 1%{?svn}%{?dist}

Name:       %{name}
Summary:    Vigilo correlator
Version:    %{version}
Release:    %{release}
Source0:    %{name}-%{version}.tar.gz
URL:        http://www.projet-vigilo.org
Group:      System/Servers
BuildRoot:  %{_tmppath}/%{name}-%{version}-%{release}-build
License:    GPLv2
Buildarch:  noarch

BuildRequires:   python-setuptools
BuildRequires:   python-babel

Requires:   python >= 2.5
Requires:   python-setuptools
Requires:   vigilo-common vigilo-pubsub vigilo-connector vigilo-models
Requires:   python-lxml
Requires:   python-memcached
Requires:   python-twisted-words
Requires:   python-networkx
Requires:   python-ampoule
######### Dependance from python dependance tree ########
Requires:   vigilo-common
Requires:   vigilo-connector
Requires:   vigilo-pubsub
Requires:   vigilo-models
Requires:   python-ampoule
Requires:   python-networkx
Requires:   python-memcached
Requires:   python-lxml
Requires:   python-setuptools
Requires:   python-OpenSSL
Requires:   python-twisted
Requires:   python-wokkel
Requires:   python-transaction
Requires:   python-pastescript
Requires:   python-zope.sqlalchemy
Requires:   python-sqlalchemy
Requires:   python-psycopg2
Requires:   python-babel
Requires:   python-zope-interface
Requires:   python-configobj
Requires:   python-pastedeploy
Requires:   python-paste

Requires(pre): rpm-helper

%description
Vigilo event correlator.
This application is part of the Vigilo Project <http://vigilo-project.org>

%prep
%setup -q

%build
make PYTHON=%{__python} \
    SYSCONFDIR=%{_sysconfdir} \
    LOCALSTATEDIR=%{_localstatedir}

%install
rm -rf $RPM_BUILD_ROOT
make install \
    DESTDIR=$RPM_BUILD_ROOT \
    PREFIX=%{_prefix} \
    SYSCONFDIR=%{_sysconfdir} \
    LOCALSTATEDIR=%{_localstatedir} \
    PYTHON=%{_bindir}/python

# Splitted Twisted
sed -i -e 's/^Twisted$/Twisted_Words/' $RPM_BUILD_ROOT%{_prefix}/lib*/python*/site-packages/vigilo*.egg-info/requires.txt

%find_lang %{name}


%pre
%_pre_useradd %{name} %{_localstatedir}/lib/vigilo/%{module} /bin/false

%post
%_post_service %{name}

%preun
%_preun_service %{name}


%clean
rm -rf $RPM_BUILD_ROOT

%files -f %{name}.lang
%defattr(644,root,root,755)
%doc COPYING doc/*
%attr(755,root,root) %{_bindir}/%{name}
%attr(744,root,root) %{_initrddir}/%{name}
%dir %{_sysconfdir}/vigilo/
%dir %{_sysconfdir}/vigilo/%{module}
%attr(640,root,%{name}) %config(noreplace) %{_sysconfdir}/vigilo/%{module}/settings.ini
%config(noreplace) %{_sysconfdir}/sysconfig/%{name}
%{python_sitelib}/*
%dir %{_localstatedir}/lib/vigilo
%attr(-,%{name},%{name}) %{_localstatedir}/lib/vigilo/%{module}


%changelog
* Mon Feb 08 2010 Aurelien Bompard <aurelien.bompard@c-s.fr> - 1.0-1
- initial package
