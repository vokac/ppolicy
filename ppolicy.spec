%{!?pyver: %define pyver %(%{__python} -c 'import sys;print(sys.version[0:3])')}
%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}
%{!?pydir: %define pydir %(%{__python} -c "from distutils.sysconfig import get_config_vars; print get_config_vars()['LIBDEST']")}

Summary: Modular Python Postfix Policy Server
Name: ppolicy
Version: 2.4.2
Release: 7
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
for file in ppolicy/tools/*.dat ppolicy/tools/*.cf; do
  install -m 0644 $file $RPM_BUILD_ROOT%{python_sitelib}/ppolicy/tools
done

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
%doc NEWS README MODULES TODO ppolicy.sql ppolicy.conf
%config(noreplace) %{_sysconfdir}/postfix/*
%{_sysconfdir}/init.d/*
%{_sbindir}/*
%{python_sitelib}/ppolicy/tools/*.cf
%{python_sitelib}/ppolicy/tools/*.dat
%attr(-,nobody,mail) %{_var}/spool/ppolicy


%changelog
* Fri May 5 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.5.0-1
- resEx returned from check method can be complex structure
  (used by List*, Greylist, SPF, ...)
- format resouce usage string, add to data hash (can be stored in db)
- case-insensitive search in List, hashArg updates

* Sat Apr 29 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.4.2-7
- fixed bug: data was not handled in separate thread in previous version
  (poor performance in case of many simultaneous connections)
- case-insensitive search for Greylist, create db index
- case-insensitive search for ListDyn
- stress test on 100k mails passed wihout any warning or error
- added more debugging to trace performance bottleneck
- thread-safe calling dns.resolver.query (because of internal hash cache)
- fixed bug in result cache expiration
- changed handling of incomming request to own Thread class
  (because of resource leaking reactor.callInThread)
- added ListMailDomain module

* Fri Apr 28 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.3.1-1
- changed method for searching MAX(`id`) in `dump` table for DumpDataDB
  (MAX is performance problem, use separate table with sequence)
  caution - new method is not thread safe, but it is only used to store
  data for further analysis - so I don't care...
- using modules stop() method should be safe
- changed check method (added required "data" argument)
- result are now by default appended to data hash (you can disable it
  using Base class parameter saveResults)
- disabled in memory chaching for ListDyn
  (needs carefull code inspection before enabling)
- create indexes on "value" columns for ListDyn table
- updated examples

* Sun Apr 9 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.2.2-2
- fixed SQL escaping
- Verification return CHECK_FAILED in case of DNS error
- added module that return spamassassin blacklist score
- fixes in dnsbl module
- DnsblScore module that use spamassassin dnsbl score
  for client ip and sender domain
- DnsblDynamic module try to identify clients on dynamic IP range
- updated documentation
- catch DNS exception in Resolve module
- unified lower/upper case of some values (e.g. sender, ...) for cached records
- fixed exception when using *args in check method (Base.hashArg method)

* Thu Apr 4 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.2.1-1
- added testing only mailhost and only tcp connection in Verification module
- escape strings that are inserted into DB
- DNS functions throws exception in case of DNS error
- added parameter to getDomainMailhost to exclude icorrect (local) addresses
- implemented Dnsbl to check client_address in selected blacklist
- SPF result should be now more reasonable (-1 - deny, 0 - unknown, 1 - pass)
- Greylist DNS error handling

* Tue Apr 4 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.1.1-1
- in memory cache for modules result (cachePositive, cacheUnknown, cacheNegative)
- changed check method parameters (custom parameters can be defined)
- ListDyn updates - changes in constructor parameters
- Verification use ListDyn for persistent cache
- names of some parameters was changed (tableName -> table, ...)
- python 2.3 compatibility fixes

* Tue Mar 28 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.0.1-1
- added ListDyn module
- bugfixes

* Mon Mar 27 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.0-2
- make logging compatible with python 2.3
- support for older MySQLdb that doesn't support autocommit(false)

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
