%define module  @SHORT_NAME@

Name:       vigilo-%{module}
Summary:    @SUMMARY@
Version:    @VERSION@
Release:    @RELEASE@%{?dist}
Source0:    %{name}-%{version}.tar.gz
URL:        @URL@
Group:      System/Servers
BuildRoot:  %{_tmppath}/%{name}-%{version}-%{release}-build
License:    GPLv2
Buildarch:  noarch

BuildRequires:   python-distribute
BuildRequires:   python-babel

Requires:   python-distribute
Requires:   vigilo-common
Requires:   vigilo-connector
Requires:   vigilo-pubsub
Requires:   vigilo-models
Requires:   python-lxml
Requires:   python-memcached
Requires:   python-twisted-words
Requires:   python-networkx
Requires:   python-ampoule

# Init
Requires(pre): shadow-utils
Requires(post): chkconfig
Requires(preun): chkconfig
Requires(preun): initscripts
Requires(postun): initscripts

%description
@DESCRIPTION@
This application is part of the Vigilo Project <http://vigilo-project.org>

%prep
%setup -q

%build

%install
rm -rf $RPM_BUILD_ROOT
make install_pkg \
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
%{_libexecdir}/twisted-dropin-cache >/dev/null 2>&1 || :

%preun
if [ $1 = 0 ]; then
    /sbin/service %{name} stop > /dev/null 2>&1 || :
    /sbin/chkconfig --del %{name} || :
fi

%postun
if [ "$1" -ge "1" ] ; then
    /sbin/service %{name} condrestart > /dev/null 2>&1 || :
fi
%{_libexecdir}/twisted-dropin-cache >/dev/null 2>&1 || :


%clean
rm -rf $RPM_BUILD_ROOT

%files -f %{name}.lang
%defattr(644,root,root,755)
%doc COPYING.txt README.txt
%attr(755,root,root) %{_bindir}/%{name}
%attr(744,root,root) %{_initrddir}/%{name}
%dir %{_sysconfdir}/vigilo/
%dir %{_sysconfdir}/vigilo/%{module}
%attr(640,root,%{name}) %config(noreplace) %{_sysconfdir}/vigilo/%{module}/settings.ini
%config(noreplace) %{_sysconfdir}/sysconfig/%{name}
%{python_sitelib}/vigilo*
%{python_sitelib}/twisted*
%dir %{_localstatedir}/lib/vigilo
%attr(-,%{name},%{name}) %{_localstatedir}/lib/vigilo/%{module}
%attr(-,%{name},%{name}) %{_localstatedir}/run/%{name}


%changelog
* Fri Jan 21 2011 Vincent Quéméner <vincent.quemener@c-s.fr> - 1.0-2
- Rebuild for RHEL6.

* Mon Feb 08 2010 Aurelien Bompard <aurelien.bompard@c-s.fr> - 1.0-1
- initial package
