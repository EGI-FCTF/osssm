%define _unpackaged_files_terminate_build 0
Summary: APEL/SSM Openstack connector
Name: apel-ssm-openstack
Version: 1.18
Release: 1
Group: Applications/System
Packager: Mattieu Puel
License: GPL2
BuildRoot: %{_builddir}/apel-ssm-openstack
BuildArch: noarch
Requires: apel-ssm, python, python-dirq



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
/etc/init.d/osssm
%defattr(0644,root,root)
/etc/logrotate.d/osssm
/var/lib/osssm/cron
/usr/share/pyshared/osssm.py
%defattr(0755,apel,apel)
/var/log/apel
/var/spool/osssm
%attr(0600,apel,apel)
%config(noreplace) /etc/osssmrc
%doc
/usr/share/man/man5/osssmrc.5.gz




%post
# add the disabled service
chkconfig --add osssm
chkconfig osssm off


%postun
# remove the service
chkconfig --del osssm
true


%changelog
* next
- moved rc script to /etc/init.d for debian systems compatibility
* Fri Mar 15 2013 Mattieu Puel 1.18-1
- corrected returned image id if not available: "unavailable" -> "NULL"
* Thu Mar 14 2013 Mattieu Puel 1.17-1
- BUG: date format difference between Essex and Folsom
- BUG: removed zone_name from required osssmrc parameters
* Mon Mar 4 2013 Mattieu Puel 1.16-2
- modified two wrong field names:
  - Site -> SiteName
  - LocalVMID -> MachineName
* Fri Feb 22 2013 Mattieu Puel 1.16-1
- compatible with SSM v2
- upgrade to usage records v0.2:
  - RecordId renamed VMUUID, contains a proper uuid
  - SiteName renamed Site, same content
  - removed ZoneName
  - remove TimeZone
  - MachineName renamed to LocalVMID
  - SuspendTime move to SuspendDuration (epoch time becomes a duration)
- configuration option ssm_input_path now points to a directory, not a file
* Fri Dec 28 2012 Mattieu Puel 1.15-1
- optimization: do not extract all urs from nova since epoch 
- configuration parameter: spoolfile_path changed to spooldir_path
- store VMs in the spool per id and not vm name, relies on Folsom/Grizzly code
- support for ended/error VMs URs upload
* Mon Dec 17 2012 Mattieu Puel 1.14-1
- support for https nova-api
* Mon Oct 29 2012 Mattieu Puel 1.13-1
- support for https keystone
* Tue Oct 23 2012 Mattieu Puel 1.12-1
- do not forward empty URs to SSM
* Thu Sep 20 2012 Mattieu Puel 1.11-1
- dissociated usage records extraction and forwarding to SSM processes
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
