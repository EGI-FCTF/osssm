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


# translate openstack statuses to EGI FCTF WG4 ones
openstack_vm_statuses = {
    'unknown':     'started',
    'active':      'started',
    'saving':      'started',
    'paused':      'paused',
    'suspended':   'suspended',
    'error':       'error',
    'deleted':     'completed',
    'shutoff':     'completed',
    'terminated' : 'completed',
}
nullValue = 'NULL'
orderedFields = [ 'RecordId', 'SiteName', 'ZoneName', 'MachineName', 'LocalUserId', 'LocalGroupId', 'GlobalUserName', 'FQAN', 'Status', 'StartTime', 'EndTime', 'SuspendTime', 'TimeZone', 'WallDuration', 'CpuDuration', 'CpuCount', 'NetworkType', 'NetworkInbound', 'NetworkOutbound', 'Memory', 'Disk', 'StorageRecordId', 'ImageId', 'CloudType' ]
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
    conn = httplib.HTTPConnection( url )

    # request for a token
    request = "%s/%s" % (url_path,"tokens")
    logging.debug('get_access_details(%s, %s, %s, %s)' % (keystone_api_url, username, dummy, tenant))
    conn.request("POST", request, params, {"Content-type": "application/json"} )
    response = (conn.getresponse()).read()
    respjson = json.loads(response)

    # list services endpoints beware, { a: b for i in } invalid in python v2.6
    services = {}
    for s in respjson['access']['serviceCatalog']:
        services[s['name']] = s['endpoints'][0]['publicURL']
    logging.debug('services found in the catalog: %s' % services)
    try:
        nova_api_url = services['nova']
        token = respjson['access']['token']['id']
        tenant_id = respjson['access']['token']['tenant']['id']
    except:
        logging.error("could not get a valid token for that user/pwd/tenant, check configuration file")
        return (None, None, None)

    logging.debug("get_access_details returns <nova_api_url=%s, token=%s, tenant_id=%s>" % (nova_api_url, token, tenant_id) )
    return ( nova_api_url, token, tenant_id )


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
                images[imid] = "unavailable"
                

    logging.debug( "available images: %s" + str(images) )
    return images



# process json entries and returns what has to be output to SSM
def compute_extract( usages, details, config, images, tenant, spooled_urs ):
    extract = {}
    now = datetime.datetime.now()

    logging.debug('extracting data from "extras/usage" query')
    for instance in usages['tenant_usage']['server_usages']:
        logging.debug('extracting data for instance %s usage: %s' % (instance['name'], instance))

        # skip already accounted ended VMs
        if instance['ended_at'] != None and spooled_urs.has_key(instance['name']) and spooled_urs[instance['name']]['Endtime'] != None:
            logging.debug('skip ended VM <%s>' % instance['name'])
            continue

        started = datetime.datetime.strptime( instance['started_at'], "%Y-%m-%d %H:%M:%S" )
        delta = now - started
        extract[instance['name']] = {
                'RecordId':           nullValue,
                'SiteName':           config['gocdb_sitename'],
                'ZoneName':           config['zone_name'],
                'MachineName':        instance['name'], 
                'LocalUserId':        nullValue,
                'LocalGroupId':       nullValue,
                'GlobalUserName':     nullValue,
                'FQAN':               nullValue,
                'StartTime':          started.strftime("%s"),
                'EndTime':            nullValue, 
                'SuspendTime':        nullValue,
                'TimeZone':           time.tzname[1] if time.daylight != 0 else time.tzname[0],
                'WallDuration':       delta.seconds + delta.days * 24 * 3600,
                'CpuDuration':        int(instance['hours']),
                'CpuCount':           instance['vcpus'],
                'NetworkType':        nullValue,
                'NetworkInbound':     nullValue,
                'NetworkOutbound':    nullValue,
                'Memory':             instance['memory_mb'],
                'Disk':               instance['local_gb'],
                'StorageRecordId':    nullValue,
                'ImageId':            nullValue,
                'CloudType':          config['cloud_type'],
                }
        try:
            extract[instance['name']]['Status'] = openstack_vm_statuses[instance['state']]
        except:
            logging.error( "unknown state <%s>" % instance['state'] )
            extract[instance['name']]['Status'] = 'unknown'

    logging.debug('extracting data from "servers/detail" query')
    for instance in details['servers']:
        logging.debug('extracting data for instance %s server detail: %s' % (instance['name'], instance))
        try:
            extract[instance['name']]['RecordId'] = time.strftime("%Y-%m-%d %H:%M:%S%z") + ' ' + config['gocdb_sitename'] + ' ' + instance['name']
            extract[instance['name']]['LocalUserId'] = instance['user_id']
            extract[instance['name']]['LocalGroupId'] = tenant
        except:
            logging.info("instance <%s> has no usage records available" % instance['name'] )
            if extract.has_key(instance['name']):
                del extract[instance['name']]
            continue
        try:
            imid = str(instance['image']['id'])
            extract[instance['name']]['ImageId'] = images[imid]
        except:
            logging.debug( "image id=%s not available in glance anymore" % imid )
            extract[instance['name']]['ImageId'] = imid

    # delete dummy records
    for instance in extract.keys():
        if extract[instance]['RecordId'] == nullValue or extract[instance]['SiteName'] == nullValue or extract[instance]['MachineName'] == nullValue:
            logging.warning('filtered instance <%s> because of bad RecordId=<%s>, Sitename=<%s>, MachineName=<%s>' % (instance,  extract[instance]['RecordId'],  extract[instance]['SiteName'],  extract[instance]['MachineName']))
            del extract[instance]

    return extract


def write_to_ssm( extract, config ):
    """forwards usage records to SSM"""
    
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
        f = open( config['ssm_input_path'], 'w' )
        f.write(output)
        f.close()
    else:
        logging.debug('no usage records, skip forwarding to SSM')


def write_to_spool( extract, config ):
    """write extracted usage records to the spool file"""

    # move URs to json format
    data = json.dumps(extract)
    logging.debug("dumping extract to json format: <%s>" % data)

    # write to file
    outfile = os.path.expanduser(config['spoolfile_path'])
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
        infile = os.path.expanduser(config['spoolfile_path'])
        f = open( infile, 'r' )
        data = f.read()
        f.close()
        spooled_ur = json.loads(data)
        logging.debug("spooled URs have been read successfully")
    except:
        logging.error("an error occured while reading the spool file")
    if spooled_ur == None:
        spooled_ur = {}
    
    return spooled_ur


def merge_records( new_urs, config ):
    """merge the extracted records with the ones spooled"""
    
    spooled_urs = get_spooled_urs( config )

    # update existing urs
    spooled_urs.update( new_urs )
    
    return spooled_urs
