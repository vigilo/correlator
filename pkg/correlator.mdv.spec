%define module  correlator
%define name    vigilo-%{module}
%define version 1.0
%define release 2

Name:       %{name}
Summary:    Vigilo correlator
Version:    %{version}
Release:    %{release}
Source0:    %{module}.tar.bz2
URL:        http://www.projet-vigilo.org
Group:      System/Servers
BuildRoot:  %{_tmppath}/%{name}-%{version}-%{release}-build
License:    GPLv2

BuildRequires:   python-setuptools

Requires:   python >= 2.5
Requires:   python-setuptools
Requires:   vigilo-common vigilo-pubsub vigilo-connector vigilo-models
Requires:   python-daemon lxml multiprocessing networkx rel

Requires(pre): rpm-helper

Buildarch:  noarch


%description
Vigilo event correlator.
This application is part of the Vigilo Project <http://vigilo-project.org>

%prep
%setup -q -n %{module}

%build
make PYTHON=%{_bindir}/python SYSCONFDIR=%{_sysconfdir} LOCALSTATEDIR=%{_localstatedir}

%install
rm -rf $RPM_BUILD_ROOT
make install \
	DESTDIR=$RPM_BUILD_ROOT \
	PREFIX=%{_prefix} \
	SYSCONFDIR=%{_sysconfdir} \
	LOCALSTATEDIR=%{_localstatedir} \
	PYTHON=%{_bindir}/python

# Mandriva splits Twisted
sed -i -e 's/^Twisted$/Twisted_Words/' $RPM_BUILD_ROOT%{_prefix}/lib*/python*/site-packages/vigilo_correlator-*-py*.egg-info/requires.txt

# Listed explicitely in %%files as %%config:
grep -v '^%{_sysconfdir}/vigilo/' INSTALLED_FILES \
	| grep -v '^%{_sysconfdir}/sysconfig' \
	> INSTALLED_FILES.filtered
mv -f INSTALLED_FILES.filtered INSTALLED_FILES


%post
%_post_service %{name}

%preun
%_preun_service %{name}


%clean
rm -rf $RPM_BUILD_ROOT

%files -f INSTALLED_FILES
%defattr(-,root,root)
%doc COPYING doc/*
%dir %{_sysconfdir}/vigilo
%config(noreplace) %{_sysconfdir}/vigilo/%{module}
%config(noreplace) %{_sysconfdir}/sysconfig/*


%changelog
* Mon Feb 08 2010 Aurelien Bompard <aurelien.bompard@c-s.fr> - 1.0-1
- initial package
