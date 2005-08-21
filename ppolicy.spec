Summary: Modular Python Postfix Policy Server
Name: ppolicy
Version: 1.1
Release: 1
License: GPL
Source: http://kmlinux.fjfi.cvut.cz/~vokac/activities/%{name}/%{name}-%{version}.tar.gz
Group: Networking/Daemons
BuildRoot: %{_tmppath}/%{name}-buildroot
BuildArch: noarch
Requires: python-twisted >= 1.3, dnspython >= 1.3.3, MySQL-python >= 1.0.0

%description
Modular Python Postfix Policy Server is tool for extending postfix
checking capabilities and can reduce mailserver load rejecting
icorrect mail during SMTP connection. It was made with stress to hight
reliability and performance by providing multilevel caching of
required data and results.


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
#exec &>/dev/null
# Adding postfix config
if [ $1 = 2 ]; then # upgrade
  # restart ppolicy
  /etc/init.d/ppolicy restart || true
else # install
  if [ -x /sbin/chkconfig ]; then
    /sbin/chkconfig --add ppolicy
    #/sbin/chkconfig --level 35 ppolicy
  fi
  # start ppolicy
  /etc/init.d/ppolicy start || true
  cat << EOF
* change configuration /etc/postfix/ppolicy.conf
* update /etc/postfix/main.cf:
    smtpd_recipient_restrictions =
        ...
        reject_unauth_destination
        check_policy_service inet:127.0.0.1:1030
        ...
    127.0.0.1:1030_time_limit = 3600

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
  cat /etc/postfix/main.cf.tmp | grep -v 'check_policy_service inet:127.0.0.1:1030' > /etc/postfix/main.cf
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
* Wed Aug 17 2005 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
- caching rewritten

* Sun Aug  7 2005 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
- first public release 1.0

* Sat Jul 30 2005 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz>
- initial release
