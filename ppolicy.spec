Summary: Modular Postfix policy server running with Twisted
Name: ppolicy
Version: 1.0
Release: 1
License: GPL
Source: http://kmlinux.fjfi.cvut.cz/~vokac/apps/%{name}-%{version}.tar.gz
Group: Networking/Daemons
BuildRoot: %{_tmppath}/%{name}-buildroot
BuildArchitectures: noarch
Requires: python-twisted >= 1.3, dnspython >= 1.3.3, MySQL-python >= 1.0.0

%description
Modular Postfix policy server is tool for extending postfix checking
capabilities and can reduce mailserver load rejecting icorrect mail
during SMTP connection. It was made with stress to hight reliability
and performance by providing multilevel caching of required data and
results. Because it has modular design it can be easily extended by
custom modules (only one method has to be implemented and everything
else is handled automatically). By default it provide SPF checking,
domain mailhost checking, sender/recipient verification, ... It also
provide configuration mechanism to make logical AND, OR, NOT and
IFwith results of each module.

%prep
%setup

%build
python setup.py build

%install
[ ! -z "$RPM_BUILD_ROOT" -a "$RPM_BUILD_ROOT" != '/' ] && rm -rf "$RPM_BUILD_ROOT"

python setup.py install --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES

install -p -D -m644 ppolicy.conf $RPM_BUILD_ROOT%{_sysconfdir}/postfix/ppolicy.conf
install -p -D -m755 ppolicy.init $RPM_BUILD_ROOT%{_sysconfdir}/init.d/ppolicy
install -p -D -m644 ppolicy.tap $RPM_BUILD_ROOT%{_sbindir}/ppolicy.tap
install -d $RPM_BUILD_ROOT%{_var}/spool/ppolicy

%clean
[ ! -z "$RPM_BUILD_ROOT" -a "$RPM_BUILD_ROOT" != '/' ] && rm -rf "$RPM_BUILD_ROOT"

%post
/sbin/chkconfig --add ppolicy
/sbin/chkconfig --level 35 ppolicy
/etc/init.d/ppolicy start

%preun
/etc/init.d/ppolicy stop
/sbin/chkconfig --del ppolicy

%files -f INSTALLED_FILES
%defattr(-,root,root)
#%doc README INSTALL
%config(noreplace) %{_sysconfdir}/postfix/*
%{_sysconfdir}/init.d/*
%{_sbindir}/*
%attr(-,nobody,mail) %{_var}/spool/ppolicy

%changelog
* Sat Jul 30 2005 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
- initial release
