import sys
import json
import os
import logging
from datetime import datetime
import stomp
import socket
import time
import uuid
from django.db import connection
import django
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
django.setup()
# Modules created by Bioconductor
from bioconductor.config import BIOC_R_MAP
from bioconductor.communication import getNewStompConnection

logging.basicConfig(format='%(levelname)s: %(asctime)s %(filename)s - %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p',
                    level=logging.DEBUG)
logging.getLogger("stomp.py").setLevel(logging.DEBUG)

# set up django environment
path = os.path.abspath(os.path.dirname(sys.argv[0]))
segs = path.split("/")
segs.pop()
path =  "/".join(segs)
sys.path.append(path)
# now you can do stuff like this:
#from spb_history.viewhistory.models import Package
#print Package.objects.count()

from viewhistory.models import Job
from viewhistory.models import Package
from viewhistory.models import Build
from viewhistory.models import Message

def parse_time(time_str):
    """ take a string like 'Tue Nov 29 2011 11:55:40 GMT-0800 (PST)'
        and convert it to a DateTime """
    segs = time_str.split(" GMT")
    return(datetime.strptime(segs[0], "%a %b %d %Y %H:%M:%S"))

def handle_job_start(obj):
    pkg = obj['job_id'].split("_")[0]
    pkg = pkg.strip()
    try:
        logging.info("Checking if package exists")
        existing_pkg = Package.objects.get(name=pkg)
        logging.info("Package already exists")
    except Package.DoesNotExist:
        logging.info("Package did not exist, saving to database")
        existing_pkg = Package(name=pkg)
        existing_pkg.save()
        logging.info("Package saved to database")

    logging.info("Saving job to databse")
    j = Job(package=existing_pkg,
      job_id=obj['job_id'],
      time_started=parse_time(obj['time']),
      pkg_url=obj['svn_url'],
      force=obj['force'],
      client_id=obj['client_id'],
      bioc_version=obj['bioc_version'],
      r_version=BIOC_R_MAP[obj['bioc_version']])
    j.save()
    logging.info("Job saved to database")

def handle_dcf_info(obj, build):
    build.maintainer = obj['maintainer']
    build.version = obj['version']
    build.save()

def handle_first_message(obj, parent_job):
    build = Build(job=parent_job,
      builder_id=obj['builder_id'],
      jid=obj['job_id'],
      maintainer='',
      version='0.0.0',
      preprocessing_result='',
      buildsrc_result='',
      checkinstall_result='',
      checksrc_result='',
      buildbin_result='',
      postprocessing_result='',
      svn_cmd='',
      check_cmd='',
      r_cmd='',
      r_buildbin_cmd='',
      os='',
      arch='',
      r_version='',
      platform='',
      invalid_url=False,
      build_not_required=False,
      build_product='',
      filesize=-1,
      buildsrc_time='',
      buildbin_time='',
      check_time='')
    build.save()
    return(build)

def handle_phase_message(obj):
    if 'sequence' in obj:
        sequence = obj['sequence']
    else:
        sequence = -1

    if 'retcode' in obj:
        retcode = obj['retcode']
    else:
        retcode = -1

    msg = Message(build = get_build_obj(obj),
      build_phase = obj['status'],
      sequence=sequence,
      retcode=retcode,
      body=obj['body'])
    msg.save()

    if 'body' in obj:
        body_str = str(obj['body'])
    else:
        body_str = ""

    logging.info("on message(): builder_id: %s job_id: %s status: %s : %s" % (obj['builder_id'], obj['job_id'], obj['status'], body_str))


def get_build_obj(obj):
    return(Build.objects.get(jid=obj['job_id'], builder_id=obj['builder_id']))


def handle_complete(obj, build_obj):

    if obj['retcode'] == 0:
        if "warnings" in obj and obj['warnings'] == True:
            result = "WARNINGS"
        else:
            result = "OK"
    elif obj['retcode'] == -4:
        result = "WARNINGS"
    else:
        result = "ERROR"
    logging.debug("handle_complete() status: %s; result: %s."
                  % (obj['status'], result))

    if (obj['status'] == 'build_complete'):
        build_obj.buildsrc_result = result
        build_obj.buildsrc_time = obj['elapsed_time']
        if result == "ERROR":
            build_obj.checksrc_result = "skipped"
            build_obj.buildbin_result = "skipped"
            build_obj.postprocessing_result = "skipped"
        logging.debug("builder_id: %s Retcode: %s" % (obj['builder_id'], str(obj['retcode'])))
        if obj['retcode'] == -9:
            build_obj.buildsrc_result = "TIMEOUT"
            build_obj.postprocessing_result = "skipped"

    elif (obj['status'] == 'unsupported'):
        build_obj.buildsrc_result = "UNSUPPORTED"
        build_obj.checksrc_result = "skipped"
        build_obj.buildbin_result = "skipped"
        build_obj.postprocessing_result = "skipped"
        logging.debug("builder_id: %s Retcode: %s" % (obj['builder_id'], str(obj['retcode'])))
                     
    elif (obj['status'] == 'check_complete'):
        build_obj.check_time = obj['elapsed_time']
        if result == "ERROR":
            build_obj.buildbin_result = "skipped"
            build_obj.postprocessing_result = "skipped"
        build_obj.checksrc_result = result
        if "Linux" in build_obj.os:
            build_obj.buildbin_result = "skipped"
            build_obj.postprocessing_result = "skipped"
        if obj['retcode'] == -9:
            build_obj.checksrc_result = "TIMEOUT"
            build_obj.postprocessing_result = "skipped"

    elif (obj['status'] == 'buildbin_complete'):
        if result == "ERROR":
            build_obj.postprocessing_result = "skipped"
        build_obj.buildbin_result = result
        build_obj.buildbin_time = obj['elapsed_time']
        logging.debug("builder_id: %s Retcode: %s" % (obj['builder_id'], str(obj['retcode'])))
        if obj['retcode'] == -9:
            build_obj.buildbin_result = "TIMEOUT"
            build_obj.buildsrc_result = "TIMEOUT"
            build_obj.postprocessing_result = "skipped"

    elif (obj['status'] == 'post_processing_complete'):
        build_obj.postprocessing_result = result
    build_obj.save()

def handle_builder_event(obj):
    phases = ["building", "checking", "buildingbin", "preprocessing",
      "post_processing"]
    parent_job = None
    job_id = None
    if ('job_id' in obj):
        job_id = obj['job_id']
        try:
            logging.debug("Checking if job exists")
            parent_job = Job.objects.get(job_id=job_id)
            logging.debug("Job already exists")
        except Job.DoesNotExist:
            logging.warning("No parent job for %s; ignoring message." % job_id)
            return()
        except Job.MultipleObjectsReturned:
            logging.warning("Multiple objects returned!")
            return()
    else:
        logging.warning("Malformed message, ignoring it.")
        return
    build_obj = None
    if('first_message' in obj and obj['first_message'] == True):
        logging.debug("handle_builder_event() Handling first message.")
        build_obj = handle_first_message(obj, parent_job)
    if ('status' in obj):
        status = obj['status']
        sys.stdout.flush()
        try:
            build_obj = get_build_obj(obj)
        except Exception as e:
            logging.warning("handle_builder_event() Exception: %s." % e)
            return
        if (status == 'dcf_info'):
            handle_dcf_info(obj, build_obj)
        elif (status in phases):
            if obj['status'] == 'post_processing':
                if 'build_product' in obj:
                    build_obj.build_product = obj['build_product']
                    build_obj.save()
                if 'filesize' in obj:
                    build_obj.filesize = obj['filesize']
                    build_obj.save()
                    return()
            handle_phase_message(obj)
        elif (status == 'svn_cmd'):
            build_obj.svn_cmd = obj['body']
            build_obj.save()
        elif (status == 'check_cmd'):
            build_obj.check_cmd = obj['body']
            build_obj.save()
        elif (status=='r_cmd'):
            build_obj.r_cmd = obj['body']
            build_obj.save()
        elif (status=='r_buildbin_cmd'):
            build_obj.r_buildbin_cmd = obj['body']
            build_obj.save()
        elif (status=='skip_buildbin'):
            build_obj.buildbin_result = 'skipped'
            build_obj.save()
        elif (status in ['build_complete', 'check_complete',
          'unsupported',
          'buildbin_complete', 'post_processing_complete']):
            handle_complete(obj, build_obj)
        elif (status == 'node_info'):
            bioc_version = obj['bioc_version']
            build_obj.r_version = BIOC_R_MAP[bioc_version]
            build_obj.os = obj['os']
            build_obj.arch = obj['arch']
            build_obj.platform = obj['platform']
            build_obj.save()
        elif (status == 'invalid_url'):
            build_obj.invalid_url = True
            build_obj.buildsrc_result = 'skipped'
            build_obj.checksrc_result = 'skipped'
            build_obj.buildbin_result = 'skipped'
            build_obj.postprocessing_result = 'skipped'
            build_obj.save()
            #job = build_obj.job
            #pkg = job.package
            #pkg.delete()
            #job.delete()
            #build_obj.delete()
            return(1)
        elif (status == 'build_not_required'):
            build_obj.build_not_required = True
            build_obj.buildsrc_result = 'skipped'
            build_obj.checksrc_result = 'skipped'
            build_obj.buildbin_result = 'skipped'
            build_obj.postprocessing_result = 'skipped'
            build_obj.preprocessing_message = "Build not required, versions identical in source and repository, and force not specified."
            build_obj.save()
        elif (status == 'build_failed'):
            build_obj.buildsrc_result = 'ERROR'
            build_obj.checksrc_result = 'skipped'
            build_obj.buildbin_result = 'skipped'
            build_obj.postprocessing_result = 'skipped'
            build_obj.save()
        elif (status in ['git_cmd', 'git_result','starting_check',
                         'Builder has been started', 'chmod_retcode',
                         'starting_buildbin','normal_end','clear_check_console',
                         'write_gitclone','r_check','bioc_check']):
            # temporarily manage 'status' messages not dealt with above
            # to avoid below info with whole object printed
            # TODO: consider specialized handling
            logging.info("on message(): builder_id: %s status: %s received" % (obj['builder_id'], status))
        elif (status == 'Got Build Request'):
            logging.info("on message(): builder_id: %s Build Request Received" % obj['builder_id'])
        elif (status == 'autoexit'):
            logging.info("on message(): Done")
        else:
            logging.info("handle_builder_event() Ignoring message: %s." % obj)
    else:
        logging.warning("handle_builder_event() No 'status' key: %s." % obj)
        # svn_result,
        # clear_check_console, starting_check,
        # starting_buildbin, svn_info,
        # chmod_retcode*,
        # normal_end

def is_connection_usable():
    try:
        connection.connection.ping()
    except:
        return False
    else:
        return True


# TODO: Name the callback for it's functionality, not usage.  This
# seems like it's as useful as 'myFunction' or 'myMethod'.  Why not
# describe capability provided ?
class   MyListener(stomp.ConnectionListener):
    def on_connecting(self, host_and_port):
        logging.debug('on_connecting() %s %s.' % host_and_port)

    def on_connected(self, frame):
        logging.debug('on_connected() %s %s.' % (frame.headers, frame.body))

    def on_disconnected(self):
        logging.debug('on_disconnected().')

    def on_heartbeat_timeout(self):
        logging.debug('on_heartbeat_timeout().')

    def on_before_message(self, frame):
        logging.debug('on_before_message() %s .' % frame)
        return frame

    def on_receipt(self, frame):
        logging.debug('on_receipt() %s %s.' % (frame.headers, frame.body))

    def on_send(self, frame):
        logging.debug('on_send() %s %s %s.' %
                      (frame.cmd, frame.headers, frame.body))

    def on_heartbeat(self):
        logging.info('on_heartbeat(): Waiting to do work.')

    def on_error(self, frame):
        logging.debug('on_error(): "%s".' % frame.message)

    def on_message(self, frame):
        headers = frame.headers
        body = frame.body
        # FIXME, don't hardcode keepalive topic name:
        if headers['destination'] == '/topic/keepalive':
            logging.debug('got keepalive message')
            response = {"host": socket.gethostname(),
            "script": os.path.basename(__file__)}
            stomp.send(body=json.dumps(response),
                destination="/topic/keepalive_response")
            return()

        debug_msg = {"script": os.path.basename(__file__),
            "host": socket.gethostname(), "timestamp":
            datetime.now().isoformat()}


        # clean this log message up
        #logging.info("Received stomp message with body: {message}".format(message=body))
        dic = json.loads(body)
        msg = ''
        if 'builder_id' in dic:
            msg = msg + "builder_id: " + dic['builder_id'] + " "
            debug_msg['builder'] = dic['builder_id']
        if 'job_id' in dic:
            msg = msg + "job_id: " + dic['job_id'] + " "
        if 'status' in dic:
            msg = msg + "status: " + dic['status'] + " "
            debug_msg['status'] = dic['status']
        if 'sequence' in dic:
            msg = msg + "sequence: " + str(dic['sequence']) + " "
        if 'elapsed_time' in dic:
            msg = msg + "elapsed_time: " + str(dic['elapsed_time']) + " "
        if 'retcode' in dic:
            msg = msg + "retcode: " + str(dic['retcode']) + " "
        if 'client_id' in dic:
            debug_msg['issue'] = dic['client_id']
        logging.info("Incoming message(): " + msg)

        stomp.send(body=json.dumps(debug_msg),
            destination="/topic/keepalive_response")

        destination = headers.get('destination')
        logging.debug("Message is intended for destination: {dst}".format(dst = destination))
        received_obj = None
        if not is_connection_usable():
            logging.debug("on_message() Closing connection.")
            connection.close()
        try:
            logging.debug("on_message() Parsing JSON.")
            received_obj = json.loads(body)
            logging.debug("on_message() Successfully parsed JSON")
        except ValueError as e:
            logging.error("on_message() JSON is invalid: %s." % e)
            return

        if ('job_id' in list(received_obj.keys())):
            if (destination == '/topic/buildjobs'):
                handle_job_start(received_obj)
            elif (destination == '/topic/builderevents'):
                handle_builder_event(received_obj)
            logging.debug("on_message() Destination handled.")
        else:
            logging.warning("on_message() Invalid json (no job_id key).")

        # Acknowledge that the message has been processed
        self.message_received = True


logging.info("main() Waiting for messages.")


try:
    logging.debug("Attempting to connect using new communication module")
    stomp = getNewStompConnection('', MyListener())
    logging.info("Connection established using new communication module")
    stomp.subscribe(destination="/topic/buildjobs", id=uuid.uuid4().hex, ack='client')
    logging.info("Subscribed to  %s" % "/topic/buildjobs")
    stomp.subscribe(destination="/topic/builderevents", id=uuid.uuid4().hex, ack='client')
    logging.info("Subscribed to  %s" % "/topic/builderevents")
    stomp.subscribe(destination="/topic/keepalive", id=uuid.uuid4().hex,
                    ack='auto')
    logging.info("Subscribed to  %s" % "/topic/keepalive")
except:
    logging.error("Cannot connect to Stomp")
    raise

logging.info("Waiting to do work. ")
while True:
        time.sleep(15)

logging.info("Done.")
