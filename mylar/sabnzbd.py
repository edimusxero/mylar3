#!/usr/bin/python
#  This file is part of Mylar.
#
#  Mylar is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Mylar is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Mylar.  If not, see <http://www.gnu.org/licenses/>.

import urllib.request, urllib.parse, urllib.error
import requests
import ntpath
import os
import sys
import re
import time
from . import logger
import mylar

class SABnzbd(object):
    def __init__(self, params):
        self.sab_url = mylar.CONFIG.SAB_HOST + '/api'
        self.params = params

    def sender(self, chkstatus=False):
        try:
            from requests.packages.urllib3 import disable_warnings
            disable_warnings()
        except:
            logger.info('Unable to disable https warnings. Expect some spam if using https nzb providers.')

        try:
            if chkstatus is True:
                sendit = requests.get(self.sab_url, params=self.params, verify=False)
            else:
                logger.fdebug('parameters set to %s' % self.params)
                logger.fdebug('sending now to %s' % self.sab_url)
                sendit = requests.post(self.sab_url, data=self.params, verify=False)
        except Exception as e:
            logger.info('Failed to send to client. Error returned: %s' % e)
            return {'status': False}
        else:
            sendresponse = sendit.json()
            if chkstatus is True:
                queueinfo = sendresponse['queue']
                if str(queueinfo['status']).lower() == 'paused':
                    #logger.info('queue IS paused')
                    return {'status': True}
                else:
                    #logger.info('queue NOT paused')
                    return {'status': False}

            logger.info(sendresponse)
            if sendresponse['status'] is True:
                queue_params = {'status': True,
                                'nzo_id': ''.join(sendresponse['nzo_ids']),
                                'queue':  {'mode':   'queue',
                                           'search':  ''.join(sendresponse['nzo_ids']),
                                           'output':  'json',
                                           'apikey':  mylar.CONFIG.SAB_APIKEY}}

            else:
                queue_params = {'status': False}

            return queue_params

    def processor(self):
        sendresponse = self.params['nzo_id']
        try:
            logger.info('sending now to %s' % self.sab_url)
            logger.info('parameters set to %s' % self.params)
            time.sleep(5)   #pause 5 seconds before monitoring just so it hits the queue
            h = requests.get(self.sab_url, params=self.params['queue'], verify=False)
        except Exception as e:
            logger.info('uh-oh: %s' % e)
            return self.historycheck(self.params)
        else:
            queueresponse = h.json()
            logger.info('successfully queried the queue for status')
            try:
                queueinfo = queueresponse['queue']
                #logger.fdebug('queue: %s' % queueinfo)
                logger.fdebug('Queue status : %s' % queueinfo['status'])
                logger.fdebug('Queue mbleft : %s' % queueinfo['mbleft'])

                if str(queueinfo['status']) == 'Paused':
                    logger.warn('[WARNING] SABnzbd has the active queue Paused. CDH will not work in this state.')
                    return {'status': 'queue_paused', 'failed': False}
                while any([str(queueinfo['status']) == 'Downloading', str(queueinfo['status']) == 'Idle']) and float(queueinfo['mbleft']) > 0:
                    #if 'comicrn' in queueinfo['script'].lower():
                    #    logger.warn('ComicRN has been detected as being active for this category & download. Completed Download Handling will NOT be performed due to this.')
                    #    logger.warn('Either disable Completed Download Handling for SABnzbd within Mylar, or remove ComicRN from your category script in SABnzbd.')
                    #    return {'status': 'double-pp', 'failed': False}

                    #logger.fdebug('queue_params: %s' % self.params['queue'])
                    queue_resp = requests.get(self.sab_url, params=self.params['queue'], verify=False)
                    queueresp = queue_resp.json()
                    queueinfo = queueresp['queue']
                    logger.fdebug('status: %s' % queueinfo['status'])
                    logger.fdebug('mbleft: %s' % queueinfo['mbleft'])
                    logger.fdebug('timeleft: %s' % queueinfo['timeleft'])
                    logger.fdebug('eta: %s' % queueinfo['eta'])
                    time.sleep(5)
            except Exception as e:
                logger.warn('error: %s' % e)

            logger.info('File has now downloaded!')
            return self.historycheck(self.params)

    def historycheck(self, nzbinfo, roundtwo=False):
        sendresponse = nzbinfo['nzo_id']
        hist_params = {'mode':      'history',
                       'category':  mylar.CONFIG.SAB_CATEGORY,
                       'failed':    0,
                       'output':    'json',
                       'apikey':    mylar.CONFIG.SAB_APIKEY}
        hist = requests.get(self.sab_url, params=hist_params, verify=False)
        historyresponse = hist.json()
        #logger.info(historyresponse)
        histqueue = historyresponse['history']
        found = {'status': False}
        nzo_exists = False

        try:
            for hq in histqueue['slots']:
                logger.info('nzo_id: %s --- %s [%s]' % (hq['nzo_id'], sendresponse, hq['status']))
                if hq['nzo_id'] == sendresponse and any([hq['status'] == 'Completed', hq['status'] == 'Running', 'comicrn' in hq['script'].lower()]):
                    nzo_exists = True
                    logger.info('found matching completed item in history. Job has a status of %s' % hq['status'])
                    if 'comicrn' in hq['script'].lower():
                        logger.warn('ComicRN has been detected as being active for this category & download. Completed Download Handling will NOT be performed due to this.')
                        logger.warn('Either disable Completed Download Handling for SABnzbd within Mylar, or remove ComicRN from your category script in SABnzbd.')
                        return {'status': 'double-pp', 'failed': False}

                    if os.path.isfile(hq['storage']):
                        logger.info('location found @ %s' % hq['storage'])
                        found = {'status':   True,
                                 'name':     ntpath.basename(hq['storage']), #os.pathre.sub('.nzb', '', hq['nzb_name']).strip(),
                                 'location': os.path.abspath(os.path.join(hq['storage'], os.pardir)),
                                 'failed':   False,
                                 'issueid':  nzbinfo['issueid'],
                                 'comicid':  nzbinfo['comicid'],
                                 'apicall':  True,
                                 'ddl':      False}
                        break
                    else:
                        logger.info('no file found where it should be @ %s - is there another script that moves things after completion ?' % hq['storage'])
                        return {'status': 'file not found', 'failed': False}

                elif hq['nzo_id'] == sendresponse and hq['status'] == 'Failed':
                    nzo_exists = True
                    #get the stage / error message and see what we can do
                    stage = hq['stage_log']
                    logger.fdebug('stage: %s' % (stage,))
                    for x in stage:
                        if 'Failed' in x['actions'] and any([x['name'] == 'Unpack', x['name'] == 'Repair']):
                            if 'moving' in x['actions']:
                                logger.warn('There was a failure in SABnzbd during the unpack/repair phase that caused a failure: %s' % x['actions'])
                            else:
                                logger.warn('Failure occured during the Unpack/Repair phase of SABnzbd. This is probably a bad file: %s' % x['actions'])
                                if mylar.FAILED_DOWNLOAD_HANDLING is True:
                                    found = {'status':   True,
                                             'name':     re.sub('.nzb', '', hq['nzb_name']).strip(),
                                             'location': os.path.abspath(os.path.join(hq['storage'], os.pardir)),
                                             'failed':   True,
                                             'issueid':  sendresponse['issueid'],
                                             'comicid':  sendresponse['comicid'],
                                             'apicall':  True,
                                             'ddl':      False}
                            break
                    if found['status'] is False:
                        return {'status': 'failed_in_sab', 'failed': False}
                    else:
                        break
                elif hq['nzo_id'] == sendresponse:
                    nzo_exists = True
                    logger.fdebug('nzo_id: %s found while processing queue in an unhandled status: %s' % (hq['nzo_id'], hq['status']))
                    if hq['status'] == 'Queued' and roundtwo is False:
                        time.sleep(4)
                        return self.historycheck(nzbinfo, roundtwo=True)
                    else:
                        return {'failed': False, 'status': 'unhandled status of: %s' %( hq['status'])}

            if not nzo_exists:
                logger.info('Cannot find nzb %s in the queue.  Was it removed?' % sendresponse)
                time.sleep(5)
                if roundtwo is False:
                    return self.historycheck(nzbinfo, roundtwo=True)
                else:
                    return {'status': 'nzb removed', 'failed': False}
        except Exception as e:
            logger.warn('error %s' % e)
            return {'status': False, 'failed': False}

        return found
