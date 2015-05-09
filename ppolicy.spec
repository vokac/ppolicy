%{!?pyver: %define pyver %(%{__python} -c 'import sys;print(sys.version[0:3])')}
%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}
%{!?pydir: %define pydir %(%{__python} -c "from distutils.sysconfig import get_config_vars; print get_config_vars()['LIBDEST']")}

Summary: Modular Python Postfix Policy Server
Name: ppolicy
Version: 2.7.0
Release: 0beta19
License: GPL
URL: https://github.com/vokac/ppolicy
Source: %{name}-%{version}.tar.gz
Group: Networking/Daemons
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root
BuildArch: noarch
BuildRequires: python
#Requires: python-zope-interface >= 3.0
#removed because it is required only by some modules and not ppolicy core
#Requires: dnspython >= 1.3.3, MySQL-python >= 1.0.0, python-netaddr
Requires(pre):  /usr/bin/getent, /usr/sbin/groupadd, /usr/sbin/useradd, /usr/sbin/usermod
%if 0%{?rhel} >= 7 || 0%{?fedora} >= 18
Requires: python-twisted-core
Requires(post): systemd
Requires(preun): systemd
Requires(postun): systemd
BuildRequires: systemd
%else
Requires: python-twisted >= 1.3
Requires(post): /sbin/chkconfig
Requires(post): /sbin/service
Requires(preun): /sbin/chkconfig, initscripts
Requires(postun): initscripts
%endif

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
%{__python} setup.py build


%install
[ ! -z "$RPM_BUILD_ROOT" -a "$RPM_BUILD_ROOT" != '/' ] && rm -rf "$RPM_BUILD_ROOT"

python setup.py install --optimize=2 --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES
for file in ppolicy/tools/*.dat; do
  install -m 0644 $file $RPM_BUILD_ROOT%{python_sitelib}/ppolicy/tools
done

install -p -D -m644 ppolicy.conf $RPM_BUILD_ROOT%{_sysconfdir}/postfix/ppolicy.conf
install -p -D -m644 ppolicy.state $RPM_BUILD_ROOT%{_sysconfdir}/postfix/ppolicy.state
%if 0%{?rhel} >= 7 || 0%{?fedora} >= 18
%{__install} -D -m0644 ppolicy.service %{buildroot}%{_unitdir}/ppolicy.service
%else
install -p -D -m755 ppolicy.init $RPM_BUILD_ROOT%{_sysconfdir}/init.d/ppolicy
install -p -D -m644 ppolicy.sysconfig $RPM_BUILD_ROOT%{_sysconfdir}/sysconfig/ppolicy
%endif
#install -p -D -m644 ppolicy.logrotate $RPM_BUILD_ROOT%{_sysconfdir}/logrotate.d/ppolicy
install -p -D -m644 ppolicy.tap $RPM_BUILD_ROOT%{_sbindir}/ppolicy.tap
install -d -m0750 $RPM_BUILD_ROOT%{_var}/log/ppolicy
install -d -m0750 $RPM_BUILD_ROOT%{_localstatedir}/run/ppolicy

install -p -d %{buildroot}%{_sysconfdir}/tmpfiles.d
cat > %{buildroot}%{_sysconfdir}/tmpfiles.d/%{name}.conf <<'EOF'
D %{_localstatedir}/run/%{name} 0750 %{name} %{name} -
EOF


%clean
[ ! -z "$RPM_BUILD_ROOT" -a "$RPM_BUILD_ROOT" != '/' ] && rm -rf "$RPM_BUILD_ROOT"


%pre
/usr/bin/getent group ppolicy >/dev/null || /usr/sbin/groupadd -r ppolicy
/usr/bin/getent passwd ppolicy >/dev/null || \
/usr/sbin/useradd -r -g ppolicy -d %{_localstatedir}/run/ppolicy \
                  -s /sbin/nologin -c "Postfix policy" ppolicy
# Fix homedir for upgrades
/usr/sbin/usermod --home %{_localstatedir}/run/ppolicy ppolicy &>/dev/null

%post
%if 0%{?rhel} >= 7 || 0%{?fedora} >= 18
%systemd_post ppolicy.service
%else
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
* some modules require additional packages
   dnspython >= 1.3.3
   MySQL-python >= 1.0.0
* create database
   mysql < %{_defaultdocdir}/%{name}-%{version}/ppolicy.sql
EOF
fi
%endif

%preun
%if 0%{?rhel} >= 7 || 0%{?fedora} >= 18
%systemd_preun ppolicy.service
%else
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
%endif

%postun
%if 0%{?rhel} >= 7 || 0%{?fedora} >= 18
%systemd_postun_with_restart ppolicy.service
%else
%{_initrddir}/ppolicy condrestart &>/dev/null || :
%endif


%files -f INSTALLED_FILES
%defattr(-,root,root)
%doc NEWS README MODULES TODO TESTS ppolicy.sql ppolicy.conf
%config(noreplace) %{_sysconfdir}/postfix/ppolicy.conf
%config(noreplace) %attr(-,ppolicy,-) %{_sysconfdir}/postfix/ppolicy.state
%if 0%{?rhel} >= 7 || 0%{?fedora} >= 18
%{_unitdir}/ppolicy.service
%else
%config(noreplace) %{_sysconfdir}/sysconfig/*
#%config(noreplace) %{_sysconfdir}/logrotate.d/*
%{_sysconfdir}/init.d/*
%endif
%config(noreplace) %{_sysconfdir}/tmpfiles.d/%{name}.conf
%{_sbindir}/*
%{python_sitelib}/ppolicy/tools/*.dat
%dir %attr(-,ppolicy,ppolicy) %{_var}/log/ppolicy
%dir %attr(-,ppolicy,ppolicy) %{_localstatedir}/run/ppolicy


%changelog
* Fri Jan 30 2015 Petr Vokac <vokac@fjfi.cvut.cz> 2.7.0-beta19
- support for systemd

* Mon Jun 13 2011 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.7.0-beta10
- allow installation to custom directory
- correct ldap filter escaping
- fixed p0f data packing/unpacking (allow different versions)
- fixed IPv4 and IPv6 regex
- fixed caching all records from DB table
- fixed DB data escaping
- config file option to disable psyco
- perRecipient/perMessage DOS checking
- added simple mechanism for loading/saving module state

* Wed Sep 12 2007 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.7.0-beta1
- added LookupDB module
- code cleanup in List, ListBW, ListDyn, ListMailDomain
- case-(in)sensitive DB search depends on DB definition
  (removed explicit DB case-insensitive search using LOWER,
  because it can hurt DB performance)
- checked and fixed SQL query escaping
- checked and added indexes when creating new DB tables
- fixed possible race condition in PPolicyRequest

* Fri Aug 10 2007 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.6.5-0
- cleanup in connection threading using deferred
- switched to python twisted 2.4 (1.3 should still work)
- better handling of clients that don't wait for results
- commit database transactions
- support for twisted 2.5 (twisted Interface replaced with ZopeInterface)
- support for building RPM packages on Mandriva
- get rid of dependencies in RPM that are required only by some modules
- cleanup in getting/releasing connections from DB connection pool
- race condition in deferred checking (see Ticket #1)

* Mon Sep 18 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.6.5-4
- fixed handlint < and > in sender/recipient address
- added LookupLDAP module
- changed transport output to unbuffered(?),
  because of python-twisted 2.x compatibility
- scoring DNS blacklist rewritten


* Sun Jun 25 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.6.4-4
- changed log dir to /var/log/ppolicy
- added support to reload ppolicy.conf on SIGHUP
  (right now only simple changes in check method are safe)
- added P0f module
- added Whois module (dummy skeleton)
- changed return code for SPF module
- cleanup for IPv6 support
- ListMailDomain should work now

* Mon Jun 19 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.6.3-10
- better performance logging with DEBUG log level
- fixed bug in spf in case of splitted TXT record in DNS
- disabled spf internal DNS cache (not thread safe, out of control)
- DB_ENGINE constant to specify mysql database type
- ppolicy can listen on more ports for conncetion from postfix
  with different configuration
- added GeoIP/Country module
- fixed bug in greylist expiration
- updated dynamic patterns
- updated and patched pyspf from http://sourceforge.net/projects/pymilter
- changed log dir to /var/log/ppolicy
  
* Fri May 26 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.6.1-1
- increased mem cache expiration for modules using DNS and DB
- cache all records from List and ListMailDomain in memory
- added ListBW to search data in blacklist/whitelist
- added simple debug interface listening at command port
- changed threadsafe caching of DNS answers
- improved performance of DumpDataDB insert
- added name->mx check to Resolve module
- changed DNS timeouts, info about slow resolver in dnspython >= 1.3.4
- logging gc status only when loglevel < DEBUG (consume lot of resources)
- minor SQL query optimization
- List now support array of parameters and columns
- fixed bug in searching domain mailhost IP addresses

* Sat May 13 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.5.3-1
- resEx returned from check method can be complex structure
  (used by List*, Greylist, SPF, ...)
- format resouce usage string, add to data hash (can be stored in db)
- case-insensitive search in List, hashArg updates
- use psyco if available to improve performance
- DnsblScore caching improved
- all db connection are now in try/except block to release connections
- fixed bug in ListMailDomain, added expiration time for mem cache
- cache size can be set in config file

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

* Tue Apr 4 2006 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 2.2.1-1
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

* Fri Aug 26 2005 Petr Vokac <vokac@kmlinux.fjfi.cvut.cz> 1.3-1
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
