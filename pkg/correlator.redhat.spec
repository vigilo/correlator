%define module  correlator
%define name    vigilo-%{module}
%define version 2.0.0
%define release 1%{?svn}%{?dist}

%define pyver 26
%define pybasever 2.6
%define __python /usr/bin/python%{pybasever}
%define __os_install_post %{__python26_os_install_post}
%{!?python26_sitelib: %define python26_sitelib %(python26 -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

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

BuildRequires:   python26-distribute
BuildRequires:   python26-babel

Requires:   python26-distribute
Requires:   vigilo-common vigilo-pubsub vigilo-connector vigilo-models
Requires:   python26-lxml
Requires:   python26-memcached
Requires:   python26-twisted-words
Requires:   python26-networkx
Requires:   python26-ampoule

# Init
Requires(pre): shadow-utils
Requires(post): chkconfig
Requires(preun): chkconfig
Requires(preun): initscripts
Requires(postun): initscripts

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
    PYTHON=%{__python}

%find_lang %{name}


%pre
getent group %{name} >/dev/null || groupadd -r %{name}
getent passwd %{name} >/dev/null || useradd -r -g %{name} -d %{_localstatedir}/lib/vigilo/%{module} -s /sbin/false %{name}
exit 0

%post
/sbin/chkconfig --add %{name} || :
%{_libexecdir}/twisted-dropin-cache-%{pybasever} >/dev/null 2>&1 || :

%preun
if [ $1 = 0 ]; then
    /sbin/service %{name} stop > /dev/null 2>&1 || :
    /sbin/chkconfig --del %{name} || :
fi

%postun
if [ "$1" -ge "1" ] ; then
    /sbin/service %{name} condrestart > /dev/null 2>&1 || :
fi
%{_libexecdir}/twisted-dropin-cache-%{pybasever} >/dev/null 2>&1 || :


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
%{python26_sitelib}/*
%dir %{_localstatedir}/lib/vigilo
%attr(-,%{name},%{name}) %{_localstatedir}/lib/vigilo/%{module}
%attr(-,%{name},%{name}) %{_localstatedir}/run/%{name}


%changelog
* Mon Feb 08 2010 Aurelien Bompard <aurelien.bompard@c-s.fr> - 1.0-1
- initial package
