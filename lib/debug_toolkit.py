#!/usr/bin/env python3

import json
from functools import wraps
from time import time
import os
import sys
import logging
import fcntl
from datetime import datetime
import signal

delays={}

START_TIME = datetime.now()

TRACE=False
DRYRUN=False
DEBUG=False

# Logging
MAIN_NAME                 = os.path.splitext (os.path.basename(sys.modules['__main__'].__file__))[0]
LOG_SUFFIX = '.log'
if DRYRUN:              LOG_SUFFIX = '_DRYRUN.log'
if DEBUG:               LOG_SUFFIX = '_DEBUG.log'
if DRYRUN and DEBUG:    LOG_SUFFIX = '_DRYDEBUG.log'

LOG_FILE = MAIN_NAME + LOG_SUFFIX

#logging.basicConfig(level=logging.DEBUG, format='%(asctime)s:%(name)s:%(levelname)s:%(message)s')
logger = logging.getLogger(__name__)
# Create handlers
c_handler = logging.StreamHandler()
f_handler = logging.FileHandler(LOG_FILE)
c_handler.setLevel(logging.DEBUG)
f_handler.setLevel(logging.ERROR)
# Create formatters and add it to handlers
c_format = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
f_format = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')
c_handler.setFormatter(c_format)
f_handler.setFormatter(f_format)
# Add handlers to the logger
logger.addHandler(c_handler)
logger.addHandler(f_handler)


class KillHandler:
  kill_now = False
  def __init__(self):
    signal.signal(signal.SIGINT, self.exit_gracefully)
    signal.signal(signal.SIGTERM, self.exit_gracefully)

  def exit_gracefully(self,signum, frame):
    self.kill_now = True


def first(iter):
    return iter[0]

def deflogger(func):
    @wraps(func)    
    def wrapper(*args, **kwargs):
        #if TRACE: print ("[@deflogger] {} (args: {}, kwargs:{})".format (func.__name__, args, kwargs))
        #TRACE = kwargs['TRACE'] if kwargs['TRACE'] else False
        #print (kwargs)
        if TRACE: print ("[@deflogger] {}".format (func.__name__))
        return func(*args, **kwargs)
    return wrapper


def prettyprint_request(req):
    """
    At this point it is completely built and ready
    to be fired; it is "prepared".

    However pay attention at the formatting used in 
    this function because it is programmed to be pretty 
    printed and may differ from the actual request.
    """
    print('{}\n{}\n{}\n\n{}\n{}\n'.format(
        '-----------<prettyprint_request>-----------',
        req.method + ' ' + req.url,
        '\n'.join('{}: {}'.format(k, v) for k, v in req.headers.items()),
        req.body,
        '-----------</prettyprint_request>-----------',

    ))

def dry_request(url, headers, method=None, payload=None):
    print ('[dryrun] would send request:\n', json.dumps({'url':url, 'method': method, 'headers':headers, 'payload':payload}, sort_keys=False, ensure_ascii=False))

def debugtest01():
    print("test ok")

def measure(operation=sum):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            t = time()
            result = func(*args, **kwargs)
            ttr = time() - t
            #delays.append( {'func':func.__name__, 'args': args, 'kwargs':kwargs, 'ttr':ttr})
            key = func.__module__ + "." + func.__name__
            delays[key] = operation((ttr, delays.get(key, 0)))
            if TRACE: print("[@measure({0})] {1} took: {2:.2f} s".format(operation.__name__,key,ttr))
            return result
        return wrapper
    return decorator


fh=0
def run_once(main):
    global fh
    #fh=open(os.path.realpath(__file__),'r')
    fh=open(main,'r')
    try:
        fcntl.flock(fh,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return True
    except:
        #if DEBUG: print(main + " already running, exiting.")
        #os._exit(0)
        return False

def get_uptime():
    return (datetime.now() - START_TIME).total_seconds()

def handle_exception(exc_type, exc_value, exc_traceback):
    # Logging
    # stream = logging.StreamHandler(sys.stderr)
    # stream.setLevel(logging.DEBUG)
    # logger = logging.getLogger()
    # logger.addHandler(stream)

    if issubclass(exc_type, KeyboardInterrupt):
        logger.warn("Interrupted.")
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    logging.info("Terminated.")
    sys.exit(255)

def crash_me():
    print(2 / 0)

