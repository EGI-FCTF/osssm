"""
author:    mpuel@in2p3.fr
date:      lundi 23 avril 2012, 13:17:15 (UTC+0200)
copyright: Copyright (c) by IN2P3 computing centre, Villeurbanne (Lyon), France


"""

import base64
import urllib
import httplib
import json
import os
import ConfigParser
import logging
import time
import datetime
import urlparse
import pprint
import copy
import os.path
from dirq.QueueSimple import QueueSimple
from dateutil import parser

# translate openstack statuses to EGI FCTF WG4 ones
# extract from file api/openstack/common.py (_STATE_MAP)

openstack_vm_statuses = {
    'active':            'started',
    'build':             'started',
    'confirming_resize': 'started',
    'deleted':           'completed', 
    'error':             'error',
    'hard_reboot':       'started',
    'migrating':         'started',
    'password':          'started',
    'paused':            'paused',
    'reboot':            'started',
    'rebuild':           'started',
    'rescue':            'started',
    'resize':            'started',
    'revert_resize':     'started',
    'verify_resize':     'started',
    'shutoff':           'completed',
    'suspended':         'suspended',
    'terminated' :       'completed',
    'stopped':           'stopped',
    'saving':            'started',
    'unknown':           'unknown',
}
nullValue = 'NULL'
orderedFields = [ 'VMUUID', 'SiteName', 'MachineName', 'LocalUserId', 'LocalGroupId', 'GlobalUserName', 'FQAN', 'Status', 'StartTime', 'EndTime', 'SuspendDuration', 'WallDuration', 'CpuDuration', 'CpuCount', 'NetworkType', 'NetworkInbound', 'NetworkOutbound', 'Memory', 'Disk', 'StorageRecordId', 'ImageId', 'CloudType' ]
stu_date_format = '%Y-%m-%d %H:%M:%S.0'

dummy = '##########'


def get_access_details( keystone_api_url, username, password, tenant ):
    """Authenticate to keystone
1- get a valid token authenticating with user/pass
2- retrieves Nova API URL for subsequent accesses
3- retrieves the tenant id
    """
    urlparsed = urlparse.urlparse( keystone_api_url )
    url = urlparsed[1]
    url_path = urlparsed[2]

    params = '{ "auth": { "passwordCredentials":{"username":"%s", "password":"%s"}, "tenantName": "%s"}}' % (username, password, tenant)
    if urlparsed[0] == "https":
        conn = httplib.HTTPSConnection( url )
    else:
        conn = httplib.HTTPConnection( url )

    # request for a token
    request = "%s/%s" % (url_path, "tokens")
    logging.debug('get_access_details(%s, %s, %s, %s)' % (keystone_api_url, username, dummy, tenant))
    conn.request("POST", request, params, {"Content-type": "application/json"} )
    response = (conn.getresponse()).read()
    respjson = json.loads(response)

    # list services endpoints beware, { a: b for i in } invalid in python v2.6
    services = {}
    logging.debug(respjson)
    for s in respjson['access']['serviceCatalog']:
        services[s['name']] = {}
        for type in ( 'publicURL', 'adminURL' ):
            services[s['name']][type] = s['endpoints'][0][type]
    logging.debug('services found in the catalog: %s' % services)
    try:
        nova_api_url = services['nova']['publicURL']
        keystone_adminapi_url = services['keystone']['adminURL']
        token = respjson['access']['token']['id']
        tenant_id = respjson['access']['token']['tenant']['id']
    except:
        logging.error("could not get a valid token for that user/pwd/tenant, check configuration file")
        return (None, None, None)

    logging.debug("get_access_details returns <nova_api_url=%s, token=%s, tenant_id=%s>" % (nova_api_url, token, tenant_id) )
    return ( nova_api_url, keystone_adminapi_url, token, tenant_id )


def get_json_response( conn, request, params, headers ):
    """process a request to nova API and returns the result as a json structure
    """

    if params != {}:
        request += "?" + urllib.urlencode( params )
    logging.debug("sending request <GET %s>" % request)
    conn.request("GET", request, urllib.urlencode({}), headers )
    
    response = conn.getresponse()
    logging.debug('response received')
    data = response.read()
    logging.debug(data)

    # return json structure
    return json.loads( data )


# returns a dict of available images to user of id userid
# { 'image_id' => 'image_name', ... }
def get_images_ids( conn, userid, instances, headers, url_path ):
    images = {}
    logging.debug("retrieving available images ids")

    for image in get_json_response( conn, "%s/images" % url_path, {}, headers )['images']:
        logging.debug("found image <name=%s, id=%s>" % ( image['name'], image['id']) )
        images[image['id']] = image['name']

    # check for instances images ids (may be some deleted)
    # this should be possible in previous request according to api documentation but does not work
    for instance in instances['servers']:
        imid = str(instance['image']['id'])
        if not images.has_key( instance['image']['id'] ):
            logging.debug("image is no more available, request detailed information")
            try:
                imname = get_json_response( conn, "%s/images/%s" % ( url_path, imid ), {}, headers )['image']['name']
                images[imid] = imname
                logging.debug("found image <name=%s, id=%s>" % ( imname, imid ) )
            except:
                logging.debug("no available information for instance image, skip")
                images[imid] = nullValue
                

    logging.debug( "available images: %s" + str(images) )
    return images


# returns a dict of user id/names in the form:
# { 'id' => 'name', ... }
def get_user_names( keystone_admin_url, token ):

    urlp = urlparse.urlparse( keystone_admin_url )
    url = urlp[1]
    url_path = urlp[2]
    conn = httplib.HTTPSConnection( url )

    conn.request("GET", "%s/users" % url_path, urllib.urlencode({}), { "X-Auth-Token": token, "Content-type":"application/json" } )
    response = (conn.getresponse()).read()
    respjson = json.loads(response)

    # no inline construct for hashes in python 2.6...
    names = {}
    for u in respjson['users']:
        names[u['id']] = u['name']
    return names


def compute_extract( usages, details, config, images, users, vo, tenant, spool ):

    # spool new URs (those related to new VMs)
    logging.debug('extracting data from "details" query')
    for instance in details['servers']:
        if not spool.has_key(instance['id']):

            logging.debug('adding new record to spool for instance id <%s>' % instance['id'])
            spool[instance['id']] = {
                'VMUUID':             instance['id'],
                'SiteName':           config['gocdb_sitename'],
                'MachineName':        instance['name'], 
                'LocalUserId':        instance['user_id'],
                'LocalGroupId':       instance['tenant_id'],
                'FQAN':               nullValue,
                'Status':             nullValue,
                'StartTime':          nullValue,
                'EndTime':            nullValue, 
                'SuspendDuration':    nullValue,
                'WallDuration':       nullValue,
                'CpuDuration':        nullValue,
                'CpuCount':           nullValue,
                'NetworkType':        nullValue,
                'NetworkInbound':     nullValue,
                'NetworkOutbound':    nullValue,
                'Memory':             nullValue,
                'Disk':               nullValue,
                'StorageRecordId':    nullValue,
                'ImageId':            nullValue,
                'CloudType':          config['cloud_type'],
                'VO':                 vo,
                'VOGroup':            nullValue,
                'VORole':             nullValue,
                }

            try:
                logging.debug('trying to find out image id (depends on afterward deletion)')
                imid = str(instance['image']['id'])
                spool[instance['id']]['ImageId'] = images[imid]
            except:
                logging.debug( "image id=%s not available in glance anymore" % imid )
                spool[instance['id']]['ImageId'] = imid

            try:
                logging.debug('trying to find out user name (depends on afterward deletion)')
                spool[instance['id']]['GlobalUserName'] = str(users[instance['user_id']])
            except:
                logging.debug( "user with id=%s is not available in keystone anymore" % instance['user_id'] )
                spool[instance['id']]['GlobalUserName'] = instance['user_id']
        else:
            logging.debug('VM <%s> status has changed' % instance['id'])

    logging.debug('extracting data from "os-simple-usage" query')
    now = datetime.datetime.now()
    if usages['tenant_usage'].has_key('server_usages'):
        for instance in usages['tenant_usage']['server_usages']:
            logging.debug('extracting data for instance %s usage: %s' % (instance['name'], instance))

            if not spool.has_key(instance['instance_id']):
                logging.debug('skipping VM <%s> for which nothing is accounted' % instance['instance_id'])
                continue

            started = parser.parse( instance['started_at'] )
            delta = now - started
            spool[instance['instance_id']]['StartTime']     = started.strftime("%s")
            spool[instance['instance_id']]['WallDuration']  = delta.seconds + delta.days * 24 * 3600
            spool[instance['instance_id']]['CpuDuration']   = int(instance['hours'])
            spool[instance['instance_id']]['CpuCount']      = instance['vcpus']
            spool[instance['instance_id']]['Memory']        = instance['memory_mb']
            spool[instance['instance_id']]['Disk']          = instance['local_gb']
            if instance['ended_at'] != None:
                ended = parser.parse( instance['ended_at'] )
                spool[instance['instance_id']]['EndTime']   = ended.strftime("%s")
        
            try:
                spool[instance['instance_id']]['Status'] = openstack_vm_statuses[instance['state']]
            except:
                logging.error( "unknown state <%s>" % instance['state'] )
                spool[instance['instance_id']]['Status'] = 'unknown'



def write_to_ssm( extract, config ):
    """forwards usage records to SSM"""

    # ensure outgoing directory existence
    ssm_input_path = os.path.expanduser(config['ssm_input_path'])
    if not os.access(ssm_input_path, os.F_OK):
        os.makedirs(ssm_input_path, 0755)
    
    # only write non void URs file
    if len(extract) > 0:
        output = config['ssm_input_header'] + "\n"

        # itterate over VMs
        for vmname in extract.keys():
            logging.debug("generating ssm input file for VM %s" % vmname)
            for item in orderedFields:
                logging.debug("generating record %s: %s" % (item, extract[vmname][item]) )
                output += "%s: %s\n" % ( item, extract[vmname][item] )
            output += config['ssm_input_sep'] + "\n"

        # write file
        try:
            dirq = QueueSimple(ssm_input_path)
            dirq.add(output)
        except:
            logging.error('unable to push message in apel-ssm queue <%s>' % ssm_input_path)
    else:
        logging.debug('no usage records, skip forwarding to SSM')


def write_to_spool( extract, config ):
    """write extracted usage records to the spool file"""

    # move URs to json format
    data = json.dumps(extract)
    logging.debug("dumping extract to json format: <%s>" % data)

    # write to file    
    outfile = os.path.expanduser(config['spooldir_path'] + '/servers')
    try:        
        f = open( outfile, 'w' )
        f.write(data)
        f.close()
    except:
        logging.error("an error occured while dumping usage records to spool file <%s>" % outfile)
    logging.debug("usage records successfully dumped to spool file <%s>" % outfile)



def get_spooled_urs( config ):
    """read spooled usage records"""

    spooled_ur = None
    try:
        infile = os.path.expanduser(config['spooldir_path'] + '/servers')
        f = open( infile, 'r' )
        data = f.read()
        f.close()
        spooled_ur = json.loads(data)
        logging.debug("spooled URs have been read successfully: %s" % spooled_ur)
    except:
        logging.error("an error occured while reading the spool file <%s>" % infile)
    if spooled_ur == None:
        spooled_ur = {}
    
    return spooled_ur


def merge_records( new_urs, config ):
    """merge the extracted records with the ones spooled"""
    
    spooled_urs = get_spooled_urs( config )

    # update existing urs
    spooled_urs.update( new_urs )
    
    return spooled_urs


def timestamp_lastrun( config ):
    """touch timestamp in the spool directory"""

    timestamp = os.path.expanduser(config['spooldir_path'] + '/timestamp')
    try:
        open(timestamp, "w").close()
        logging.debug("touched timestamp <%s>" % timestamp)
    except:
        logging.error("unable to touch timestamp file <%s>" % timestamp)


def last_run( config ):
    """returns timestamp of the last extract pass, now if non-existent (stu_date_format)"""

    timestamp = os.path.expanduser(config['spooldir_path'] + '/timestamp')

    if os.path.exists(timestamp):        
        date = os.path.getmtime(timestamp)
    else:
        logging.debug("no timestamped loged run, return *now*")
        date = None

    lastrun = time.strftime( stu_date_format, time.gmtime(date) )
    logging.debug("last loged run at <%s>" % lastrun)
    return lastrun


def oldest_vm_start( config, spooled_servers, lastrun ):
    """returns the oldest accounted VM creation time (stu_date_format)"""

    # get creation dates for spooled VMs records
    spooled_creations = []
    for vm in spooled_servers.keys():
        start = spooled_servers[vm]['StartTime']
        if start != nullValue:
            spooled_creations += [ int(start) ]
    spooled_creations.sort()

    # if no spooled VM, test current VMs
    if spooled_creations == None or len(spooled_creations) == 0:
        logging.debug("no spooled VMs, return last run")
        oldest = lastrun
    else:
        oldest = time.strftime( stu_date_format, time.gmtime(spooled_creations[0]) )
    logging.debug("oldest_vm_start -> %s" % oldest)
    return oldest
        


def unspool_terminated_vms( spool ):
    """remove terminated VMs from the spool. This should occur only when VM usage record
       has been successfully forwarded to SSM"""

    for vmid in spool.keys():
        if spool[vmid]['Status'] == 'completed' or spool[vmid]['Status'] == 'error':
            del spool[vmid]

def get_tenants_mapping( config ):
    """read spooled usage records"""

    voms_json = None
    voms_tenants = {}
    try:
        infile = os.path.expanduser(config['voms_tenants_mapping'])
        f = open( infile, 'r' )
        data = f.read()
        f.close()
        voms_json = json.loads(data)
        logging.debug("voms tenants mappings have been read successfully: %s" % voms_json)
    except:
        logging.error("an error occured while reading the voms tenants mapping file <%s>" % infile)
    if voms_json == None:
        voms_json = {}

    for vo in voms_json.keys():
        try:
            voms_tenants[voms_json[vo]['tenant']] = vo
            logging.debug('VO <%s> is mapped to tenant <%s>' % (vo, voms_json[vo]['tenant']))
        except:
            pass

    return voms_tenants
