%define module  @SHORT_NAME@

Name:       vigilo-%{module}
Summary:    @SUMMARY@
Version:    @VERSION@
Release:    @RELEASE@%{?dist}
Source0:    %{name}-%{version}.tar.gz
URL:        @URL@
Group:      Applications/System
BuildRoot:  %{_tmppath}/%{name}-%{version}-%{release}-build
License:    GPLv2
Buildarch:  noarch

BuildRequires:   systemd
BuildRequires:   python-distribute
BuildRequires:   python-babel

Requires:   python-distribute
Requires:   vigilo-common
Requires:   vigilo-connector
Requires:   vigilo-models
Requires:   python-memcached

# Init
Requires(pre): shadow-utils

%description
@DESCRIPTION@
This application is part of the Vigilo Project <http://vigilo-project.org>

%prep
%setup -q

%build

%install
rm -rf $RPM_BUILD_ROOT
make install_pkg_systemd \
    DESTDIR=$RPM_BUILD_ROOT \
    PREFIX=%{_prefix} \
    SYSCONFDIR=%{_sysconfdir} \
    LOCALSTATEDIR=%{_localstatedir} \
    SYSTEMDDIR=%{_unitdir} \
    PYTHON=%{__python}
mkdir -p $RPM_BUILD_ROOT/%{_tmpfilesdir}
install -m 644 pkg/%{name}.conf $RPM_BUILD_ROOT/%{_tmpfilesdir}

%find_lang %{name}


%pre
getent group %{name} >/dev/null || groupadd -r %{name}
getent passwd %{name} >/dev/null || useradd -r -g %{name} -d %{_localstatedir}/lib/vigilo/%{module} -s /bin/false %{name}
exit 0

%post
%systemd_post %{name}.service
%{_libexecdir}/twisted-dropin-cache >/dev/null 2>&1 || :
%tmpfiles_create %{_tmpfilesdir}/%{name}.conf

%preun
%systemd_preun %{name}.service

%postun
%systemd_postun_with_restart %{name}.service
%{_libexecdir}/twisted-dropin-cache >/dev/null 2>&1 || :

%clean
rm -rf $RPM_BUILD_ROOT

%files -f %{name}.lang
%defattr(644,root,root,755)
%doc COPYING.txt README.txt
%attr(755,root,root) %{_bindir}/%{name}
%dir %{_sysconfdir}/vigilo/
%dir %{_sysconfdir}/vigilo/%{module}
%dir %{_sysconfdir}/vigilo/%{module}/conf.d
%attr(640,root,%{name}) %config(noreplace) %{_sysconfdir}/vigilo/%{module}/settings.ini
%dir %{_sysconfdir}/vigilo/%{module}/plugins
%{python_sitelib}/vigilo*
%{python_sitelib}/twisted*
%dir %{_localstatedir}/lib/vigilo
%attr(-,%{name},%{name}) %{_localstatedir}/lib/vigilo/%{module}
%dir %{_localstatedir}/log/vigilo
%attr(-,%{name},%{name}) %{_localstatedir}/log/vigilo/%{module}
%attr(644,root,root) %{_tmpfilesdir}/%{name}.conf
%attr(644,root,root) %{_unitdir}/%{name}.service
%attr(644,root,root) %{_unitdir}/%{name}@.service

%changelog
* Tue Jun 27 2017 François Poirotte <francois.poirotte@c-s.fr>
- Add support for systemd

* Thu Mar 16 2017 Yves Ouattara <yves.ouattara@c-s.fr>
- Rebuild for RHEL7.

* Fri Jan 21 2011 Vincent Quéméner <vincent.quemener@c-s.fr>
- Rebuild for RHEL6.

* Mon Feb 08 2010 Aurelien Bompard <aurelien.bompard@c-s.fr>
- initial package
