'''
Copyright (c) 2010 Brookhaven National Laboratory
All rights reserved. Use is subject to license terms and conditions.

Created on Apr 1, 2011

@author: shroffk

CFUpdateIOC provides a command like client to update channelfinder
with a list of process variables (usually the output of the dbl command).
'''

from __future__ import print_function

import os
import re
from optparse import OptionParser
from getpass import getpass
from glob import glob
import time

from channelfinder import ChannelFinderClient
from channelfinder._conf import basecfg


def getArgsFromFilename(completeFilePath):
    fileName = os.path.split(os.path.normpath(completeFilePath))[1]
    pattern4Hostname = '(\S+?)\.\S+'
    match = re.search(pattern4Hostname, fileName)
    if match:
        hostName = match.group(1)
    else:
        hostName = None
    pattern4Iocname = '\S+?\.(\S+?)\.\S+'
    match = re.search(pattern4Iocname, fileName)
    if match:
        iocName = match.group(1)
    else:
        iocName = None
    return hostName, iocName


def getPVNames(completeFilePath, pattern=None):
    try:
        f = open(completeFilePath)
        pvNames = f.read().splitlines()
        pvNames = map(lambda x: x.strip(), pvNames)
        pvNames = filter(lambda x: len(x)>0, pvNames)
        if pattern:
            pvNames = [re.match(pattern, pvName).group() for pvName in pvNames if re.match(pattern, pvName)]
        return list(pvNames)
    except IOError:
        return None
    finally:
        if f:
            f.close()


def updateChannelFinder(pvNames, hostName, iocName, time, owner,
                        service=None, username=None, password=None, pvStatus=u'Unknown'):
    '''
    pvNames = list of pvNames 
    ([] permitted will effectively remove the hostname, iocname from all channels)
    hostName = pv hostName (None not permitted)
    iocName = pv iocName (None not permitted)
    owner = the owner of the channels and properties being added, this can be different from the user
    e.g. user = abc might create a channel with owner = group-abc
    time = the time at which these channels are being created/modified
    [optional] if not specified the default values are used by the 
    channelfinderapi lib
    service = channelfinder service URL
    username = channelfinder username
    password = channelfinder password
    '''
    if iocName == None:
        raise RuntimeError('missing iocName')
    if not hostName or hostName.lower() == "unknown":
        hostName = getHostName([iocName], service).get(iocName, "Unknown")
    channels = []
    try:
        client = ChannelFinderClient(BaseURL=service, username=username, password=password)
    except:
        raise RuntimeError('Unable to create a valid webResourceClient')
    checkPropertiesExist(client, owner)
    previousChannelsList = client.findByArgs([(u'hostName', hostName), (u'iocName', iocName)])
    if previousChannelsList != None:
        for ch in previousChannelsList:
            if pvNames != None and ch['name'] in pvNames:
                ''''''
                if not isChannelEqual(ch, updateChannel(ch,
                                                       owner=owner,
                                                       hostName=hostName,
                                                       iocName=iocName,
                                                       pvStatus=pvStatus,
                                                       time=time)):

                    channels.append(updateChannel(ch,
                                                  owner=owner,
                                                  hostName=hostName,
                                                  iocName=iocName,
                                                  pvStatus=pvStatus,
                                                  time=time))
                pvNames.remove(ch['name'])
            elif pvNames == None or ch['name'] not in pvNames:
                '''Orphan the channel : mark as obsolete, keep the old hostName and iocName'''
                oldHostName = [prop[u'value'] for prop in ch[u'properties'] if prop[u'name'] == u'hostName'][0]
                oldIocName = [prop[u'value'] for prop in ch[u'properties'] if prop[u'name'] == u'iocName'][0]
                channels.append(updateChannel(ch,
                                              owner=owner,
                                              hostName=oldHostName,
                                              iocName=oldIocName,
                                              pvStatus=u'Obsolete',
                                              time=time))
    # now pvNames contains a list of pv's new on this host/ioc
    for pv in pvNames:
        ch = client.findByArgs([('~name',pv)])
        if not ch:
            '''New channel'''
            channels.append(createChannel(pv,
                                          chOwner=owner,
                                          hostName=hostName,
                                          iocName=iocName,
                                          pvStatus=pvStatus,
                                          time=time))
        elif ch[0] != None:
            '''update existing channel: exists but with a different hostName and/or iocName'''
            channels.append(updateChannel(ch[0],
                                          owner=owner,
                                          hostName=hostName,
                                          iocName=iocName,
                                          pvStatus=pvStatus,
                                          time=time))
    if channels:
        client.set(channels=channels)


def getHostName(iocs, serviceURL):
    try:
        client = ChannelFinderClient(BaseURL=serviceURL)
    except:
        raise RuntimeError('Unable to create a valid webResourceClient')
    ioc_hostname_dict = dict()
    for ioc in iocs:
        hostname = "Unknown"
        ch = client.find(property=[("iocName", ioc)], size=1)
        if ch:
            for prop in ch[0].get("properties", []):
                if prop.get("name", "") == "hostName":
                    hostname = prop.get("value")
            ioc_hostname_dict[ioc] = hostname

    return ioc_hostname_dict


def updateChannel(channel, owner, hostName=None, iocName=None, pvStatus='Inactive', time=None):
    '''
    Helper to update a channel object so as to not affect the existing properties
    '''
    
    # properties list devoid of hostName and iocName properties
    if channel[u'properties']:
        properties = [property for property in channel[u'properties']
                    if property[u'name'] != u'hostName' and property[u'name'] != u'iocName' and property[u'name'] != u'pvStatus']
    else:
        properties = []
    if hostName != None:
        properties.append({u'name' : u'hostName', u'owner':owner, u'value' : hostName})
    if iocName != None:
        properties.append({u'name' : u'iocName', u'owner':owner, u'value' : iocName})
    if pvStatus:
        properties.append({u'name' : u'pvStatus', u'owner':owner, u'value' : pvStatus})
    if time:
        properties.append({u'name' : u'time', u'owner':owner, u'value' : time}) 
    channel[u'properties'] = properties
    return channel


def updateChannelStatus(iocName, owner, time, status=u'Unknown', service=None, username=None, password=None):
    try:
        client = ChannelFinderClient(BaseURL=service, username=username, password=password)
    except:
        raise RuntimeError('Unable to create a valid webResourceClient')

    if status.lower() == "up":
        status = u"Active"
    elif status.lower() == "down":
        status = u"Inactive"

    channelsList = client.findByArgs([(u'iocName', iocName)])
    if len(channelsList) > 0:
        client.update(property={'name': "pvStatus", 'owner': owner, 'value': status},
                      channelNames=[ch['name'] for ch in channelsList])
        client.update(property={'name': "time", 'owner': owner, 'value': time},
                      channelNames=[ch['name'] for ch in channelsList])
        return True
    else:
        return False


def updateChannelHostname(iocName, owner, hostName=u'Unknown', service=None, username=None, password=None):
    try:
        client = ChannelFinderClient(BaseURL=service, username=username, password=password)
    except:
        raise RuntimeError('Unable to create a valid webResourceClient')

    if hostName == "":
        hostName = u'Unknown'
    channelsList = client.findByArgs([(u'iocName', iocName)])
    if len(channelsList) > 0:
        client.update(property={'name': "hostName", 'owner': owner, 'value': hostName},
                      channelNames=[ch['name'] for ch in channelsList])
        return True
    else:
        return False


def createChannel(chName, chOwner, hostName=None, iocName=None, pvStatus=u'Inactive', time=None):
    '''
    Helper to create a channel object with the required properties
    '''
    ch = {u'name' : chName, u'owner' : chOwner, u'properties' : []}
    if hostName != None:
        ch[u'properties'].append({u'name' : u'hostName', u'owner':chOwner, u'value' : hostName})
    if iocName != None:
        ch[u'properties'].append({u'name' : u'iocName', u'owner':chOwner, u'value' : iocName})
    if pvStatus:
        ch[u'properties'].append({u'name' : u'pvStatus', u'owner':chOwner, u'value' : pvStatus})
    if time:
        ch[u'properties'].append({u'name' : u'time', u'owner':chOwner, u'value' : time}) 
    return ch


def checkPropertiesExist(client, propOwner):
    '''
    Checks if the properties used by dbUpdate are present if not it creates them
    '''
    requiredProperties = [u'hostName', u'iocName', u'pvStatus', u'time']
    for propName in requiredProperties:
        if client.findProperty(propName) == None:
            try:
                client.set(property={u'name' : propName, u'owner' : propOwner})
            except Exception as e:
                print('Failed to create the property',propName)
                print('CAUSE:', e)


def ifNoneReturnDefault(object, default):
    '''
    if the object is None or empty string then this function returns the default value
    '''
    if object == None and object != '':
        return default
    else:
        return object


def mainRun(opts, args):
    '''
    the main is broken so that the unit test can use mock opt objects for testing
    '''
    for filename in args:
        if('*' in filename or '?' in filename):
            matchingFiles = glob(filename)
            for eachMatchingFile in matchingFiles:
                completeFilePath = os.path.abspath(eachMatchingFile)
                fHostName, fIocName = getArgsFromFilename(completeFilePath)
                ftime = os.path.getctime(completeFilePath)
                pattern = __getDefaultConfig('pattern', opts.pattern)
                updateChannelFinder(getPVNames(completeFilePath, pattern=pattern),
                            ifNoneReturnDefault(opts.hostName, fHostName),
                            ifNoneReturnDefault(opts.iocName, fIocName),
                            ifNoneReturnDefault(opts.time, ftime),
                            ifNoneReturnDefault(opts.owner,__getDefaultConfig('username', opts.username)),
                            service=__getDefaultConfig('BaseURL',opts.serviceURL),
                            username=__getDefaultConfig('username',opts.username),
                            password=__getDefaultConfig('password',opts.password))
        else:
            completeFilePath = os.path.abspath(filename)
            fHostName, fIocName = getArgsFromFilename(completeFilePath)
            ftime = os.path.getctime(completeFilePath)
            pattern = __getDefaultConfig('pattern', opts.pattern)
            updateChannelFinder(getPVNames(completeFilePath, pattern=pattern),
                            ifNoneReturnDefault(opts.hostName, fHostName),
                            ifNoneReturnDefault(opts.iocName, fIocName),
                            ifNoneReturnDefault(opts.time, ftime),
                            ifNoneReturnDefault(opts.owner,__getDefaultConfig('username', opts.username)),
                            service=__getDefaultConfig('BaseURL',opts.serviceURL),
                            username=__getDefaultConfig('username',opts.username),
                            password=__getDefaultConfig('password',opts.password))
            

def __getDefaultConfig(arg, value):
        if value is None:
            try:
                return basecfg.get('DEFAULT', arg)
            except:
                return None
        else:
            return value


def main():
    usage = "usage: %prog [options] filename"
    parser = OptionParser(usage=usage)
    parser.add_option('-H', '--hostname',
                      action='store', type='string', dest='hostName',
                      help='the hostname')
    parser.add_option('-i', '--iocname',
                      action='store', type='string', dest='iocName',
                      help='the iocname')
    parser.add_option('-s', '--service',
                      action='store', type='string', dest='serviceURL',
                      help='the service URL')
    parser.add_option('-o', '--owner',
                      action='store', type='string', dest='owner',
                      help='owner if not specified username will default as owner')
    parser.add_option('-r', '--pattern',
                      action='store', type='string', dest='pattern',
                      help='pattern to match valid channel names')
    parser.add_option('-u', '--username',
                      action='store', type='string', dest='username',
                      help='username')
    parser.add_option('-t', '--time',
                      action='store', type='string', dest='time',
                      help='time')
    parser.add_option('-p', '--password',
                      action='callback', callback=getPassword,
                      dest='password',
                      help='prompt user for password')
    opts, args = parser.parse_args()
    if len(args) == 0 or args == None:
        parser.error('Please specify a file')
    mainRun(opts, args)


def getPassword(option, opt_str, value, parser):
    '''
    Simple method to prompt user for password
    TODO do not show the password.
    '''
    parser.values.password = getpass()        


def isChannelEqual(ch1, ch2):
    '''

    :param ch1:
    :param ch2:
    :return:
    '''
    pFlag = False
    if ch1["name"] == ch2["name"]:
        if len(ch1.get("properties", [])) == 0 and len(ch2.get("properties",[])) == 0:
            pFlag = True
        else:
            if len(ch1["properties"]) == len(ch2["properties"]):
                p1_dict = dict([(p["name"], p["value"]) for p in ch1["properties"]])
                p2_dict = dict([(p["name"], p["value"]) for p in ch2["properties"]])
                if p1_dict == p2_dict:
                    pFlag = True

        if pFlag:
            if len(ch1.get("tags", [])) == 0 and len(ch2.get("tags", [])) == 0:
                return True
            else:
                if len(ch1["tags"]) == len(ch2["tags"]):
                    t1_set = set([t["name"] for t in ch1["tags"]])
                    t2_set = set([t["name"] for t in ch2["tags"]])
                    if t1_set == t2_set:
                        return True
    return False


def isTimeFormat(input):
    try:
        time.strptime(input, "%Y-%m-%d_%H:%M:%S")
        return True
    except ValueError:
        return False


if __name__ == '__main__':
    main()
    pass
