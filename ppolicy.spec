Summary: Modular Python Postfix Policy Server
Name: ppolicy
Version: 2.0
Release: 2
License: GPL
Source: http://kmlinux.fjfi.cvut.cz/~vokac/activities/%{name}/%{name}-%{version}.tar.gz
Group: Networking/Daemons
BuildRoot: %{_tmppath}/%{name}-buildroot
BuildArch: noarch
Requires: python-twisted >= 1.3, dnspython >= 1.3.3, MySQL-python >= 1.0.0

%description
Modular Python Postfix Policy Server is tool for extending Postfix
checking capabilities. It uses Postfix access policy delegation
(http://www.postfix.org/SMTPD_POLICY_README.html) to check incomming
SMTP request and accept or reject it according provided data. It can
reduce mailserver load with rejecting incorrect mail during SMTP
connection. It was made with stress to hight reliability and performance
by providing multilevel caching of required data and results.


%prep
%setup


%build
python setup.py build


%install
[ ! -z "$RPM_BUILD_ROOT" -a "$RPM_BUILD_ROOT" != '/' ] && rm -rf "$RPM_BUILD_ROOT"

python setup.py install --optimize=2 --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES

install -p -D -m644 ppolicy.conf $RPM_BUILD_ROOT%{_sysconfdir}/postfix/ppolicy.conf
install -p -D -m755 ppolicy.init $RPM_BUILD_ROOT%{_sysconfdir}/init.d/ppolicy
install -p -D -m644 ppolicy.tap $RPM_BUILD_ROOT%{_sbindir}/ppolicy.tap
install -d $RPM_BUILD_ROOT%{_var}/spool/ppolicy


%clean
[ ! -z "$RPM_BUILD_ROOT" -a "$RPM_BUILD_ROOT" != '/' ] && rm -rf "$RPM_BUILD_ROOT"


%post
#exec &>/dev/null
# Adding postfix config
if [ $1 = 2 ]; then # upgrade
  # restart ppolicy
  /etc/init.d/ppolicy restart || true
else # install
  if [ -x /sbin/chkconfig ]; then
    /sbin/chkconfig --add ppolicy
    #/sbin/chkconfig --level 2345 ppolicy
  fi
  # start ppolicy
  /etc/init.d/ppolicy start || true
  cat << EOF
* change configuration /etc/postfix/ppolicy.conf
* update /etc/postfix/main.cf:
    smtpd_recipient_restrictions =
        ...
        reject_unauth_destination
        check_policy_service inet:127.0.0.1:10030
        ...
    127.0.0.1:10030_time_limit = 3600

EOF
fi

%preun
#exec &>/dev/null
if [ $1 = 0 ]; then # uninstall
  if [ -x /sbin/chkconfig ]; then
    /etc/init.d/ppolicy stop
    /sbin/chkconfig --del ppolicy
  fi
  # Removing postfix config
  mv /etc/postfix/main.cf /etc/postfix/main.cf.tmp
  cat /etc/postfix/main.cf.tmp | grep -v 'check_policy_service inet:127.0.0.1:10030' > /etc/postfix/main.cf
  /etc/init.d/postfix reload || true
fi


%files -f INSTALLED_FILES
%defattr(-,root,root)
#%doc README INSTALL
%config(noreplace) %{_sysconfdir}/postfix/*
%{_sysconfdir}/init.d/*
%{_sbindir}/*
%attr(-,nobody,mail) %{_var}/spool/ppolicy


%changelog
* Mon Mar 27 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.0-2
- make logging compatible with python 2.3

* Sun Mar 26 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.0-1
- checking framework rewritten
- each module in separate file
- checking flow defined in ppolicy.conf using python code
- modules passed basic tests

* Sat Aug 26 2005 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 1.3-1
- update 1.3
- added DosCheck module
- added TrapCheck module
- added DnsblCheck module (with dummy dnsbl class)
- splitted tools package
- DbCache can optionaly throw exception in case of Db error
- disable graylisting if DbCache throw exception
- added timeout parameter to modules using SMTP
- disabled caching for logic modules (can be enabled in config file)
- changed caching for And, Or, ... checks (using lowest values of all checks)
- changed logging to default python logging class and twistedHandler

* Mon Aug 22 2005 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 1.2-1
- added GreylistCheck module
- module testing
- finished DomainVerificationCheck and UserVerificationCheck module
- finished database/mem caching

* Wed Aug 17 2005 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 1.1-1
- caching rewritten

* Sun Aug  7 2005 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 1.0-1
- first public release 1.0

* Sat Jul 30 2005 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
- initial release
