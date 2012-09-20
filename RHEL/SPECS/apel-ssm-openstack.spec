Summary: APEL/SSM Openstack connector
Name: apel-ssm-openstack
Version: 1.11
Release: 1
Group: Applications/System
Packager: Mattieu Puel
License: GPL2
BuildRoot: %{_builddir}/apel-ssm-openstack
BuildArch: noarch
Requires: ssm, python



%description
APEL/SSM Openstack connector for EGI cloud accounting system



%install
rsync --exclude .svn -av %{_sourcedir}/ $RPM_BUILD_ROOT/




%clean 
[ "$RPM_BUILD_ROOT" != "/" ] && rm -rf $RPM_BUILD_ROOT




%files
%defattr(0755,root,root)
/usr/bin/osssm.extract
/usr/bin/osssm.push
/etc/rc.d/init.d/osssm
%defattr(0644,root,root)
/etc/logrotate.d/osssm
/var/lib/osssm/cron
/usr/lib/python2.6/site-packages/osssm.py
/usr/lib/python2.6/site-packages/osssm.pyc
%defattr(0755,apel,apel)
/var/log/apel
/var/spool/osssm
%attr(0600,apel,apel)
%config(noreplace) /etc/osssmrc
%doc
/usr/share/man/man5/osssmrc.5.gz




%post
useradd -c "openstack accounting user" -M -d /var/empty -s /sbin/nologin osssm
install -m 644 -o osssm -g osssm /dev/null /var/log/osssm.log

# add the disabled service
chkconfig --add osssm
chkconfig osssm off


%postun
userdel osssm
# remove the service
chkconfig --del osssm
true


%changelog
* Thu Sep 20 2012 Mattieu Puel 1.11-1
- dissociated usage records extraction and forwarding to SSM processes
- added support for ended VMs status upload
- added log rotation
* Thu Sep 20 2012 Mattieu Puel 1.10-1
- no more API token, use safer user/password (obsoletes token configuration option)
- added configurations options "user" and "password"
- nova api URL is now requested to keystone catalog (obsoletes nova_api_url configuration option)
* Mon Sep 10 2012 Mattieu Puel 1.9-1
- logging of nova API verion and date
- corrected failure when instanciated image is not available anymore in glance
* Fri Jul 27 2012 Mattieu Puel 1.8-1
- filter SSM forbidden records (null recordid, site cocgdb name or vmname)
- support for new VM statuses: paused, error
- properly handle unknown statuses
* Fri Jul 27 2012 Mattieu Puel 1.7-1
- conform to accounting records format for RecordId: date + site + vmname
- Do not log clear tokens in the logfile in debug mode
- Increased robustness to some bad VM statuses
* Mon Jun 18 2012 Mattieu Puel 1.6
- Fix: properly handles deleted images
* Fri Jun 15 2012 Mattieu Puel 1.5
- fixed an issue with whitespaces in tenant names
* Wed Jun 13 2012 Mattieu Puel 1.4
- corrected logging destination
- fixes for cron mode running as apel user
* Tue Jun 12 2012 Mattieu Puel 1.3
- fix a bug of ssm input file format
- reordered usage record fields
* Sun Jun 10 2012 Mattieu Puel 1.2
- support for Essex release
* Fri Apr 27 2012 Mattieu Puel 1.1
- first release
