from jinja2 import Environment, FileSystemLoader
from jinja2 import Template
import yaml
import requests
import json
import logging
import docker
import sys
import os
import subprocess

if len(sys.argv) != 3:
    logging.error('must specify conda package and version')
    sys.exit(1)

CONDA_CONTAINER = sys.argv[1]
CONDA_TAG = sys.argv[2]

def fake(*args):
    return ''

docker_client = docker.from_env()

logging.basicConfig(level=logging.INFO)


regtags = []
try:
    reg = requests.get('http://localhost:30750/v2/biocontainers/%s/tags/list' % CONDA_CONTAINER)
    if reg.status_code == 200:
      regjson = reg.json()
      regtags = regjson['tags']

    logging.info('%s tags: %s' % (CONDA_CONTAINER, str(regtags)))
      
except Exception:
    logging.exception('failed to get tags for container')
    sys.exit(0)

r = requests.get('https://quay.io/api/v1/repository/biocontainers/%s' % CONDA_CONTAINER)
if r.status_code != 200:
    logging.error("[quay.io] Can't access container %s" % (CONDA_CONTAINER))
    sys.exit(0)

rdata = r.json()
tags = rdata['tags']

cli = docker.APIClient(base_url='unix://var/run/docker.sock')
last_update = None
tag = None
for key, t in tags.iteritems():
    if tag['name'] == CONDA_TAG:
        tag = CONDA_TAG
        break
if tag is None:
    logging.error('bioconda container tag not found: %s:%s' % (CONDA_CONTAINER, CONDA_TAG))
    sys.exit(1)

logging.info('bioconda container: %s:%s' % (CONDA_CONTAINER, CONDA_TAG))


pull_ok = False
try:
    logging.info('pull quay.io/biocontainers/%s:%s' % (CONDA_CONTAINER, CONDA_TAG))
    docker_client.images.pull('quay.io/biocontainers/%s:%s' %(CONDA_CONTAINER, CONDA_TAG))
    logging.info('tag image to docker-registry.local:30750') 
    cli.tag('quay.io/biocontainers/%s:%s' % (CONDA_CONTAINER, CONDA_TAG), 'docker-registry.local:30750/biocontainers/%s' % CONDA_CONTAINER, tag=CONDA_TAG)
    pull_ok = True
except Exception as e:
    logging.exception('Failed to pull/tag container %s:%s, %s' % (CONDA_CONTAINER, CONDA_TAG, str(e)))
try:
    if pull_ok:
        logging.info('push image docker-registry.local:30750/biocontainers/%s:%s' % (CONDA_CONTAINER, CONDA_TAG))        
        for line in docker_client.images.push('docker-registry.local:30750/biocontainers/%s' % CONDA_CONTAINER, tag=CONDA_TAG, stream=True):
            logging.debug(str(line))
        logging.info('push ok')
        logging.info('add anchore scan')
        anchore_image = 'quay.io/biocontainers/%s:%s' % (CONDA_CONTAINER, CONDA_TAG)
        cmd = ['anchore-cli', 'image', 'add', anchore_image]
        scan = subprocess.check_output(cmd)
        logging.debug('scan output: ' + str(scan))
except Exception as e:
    logging.error('Failed to push container %s:%s, %s' % (CONDA_CONTAINER, CONDA_TAG, str(e)))
try: 
    logging.debug('cleanup of images') 
    docker_client.images.remove('quay.io/biocontainers/%s:%s' % (CONDA_CONTAINER, CONDA_TAG))
    docker_client.images.remove('docker-registry.local:30750/biocontainers/%s:%s' % (CONDA_CONTAINER, CONDA_TAG))
except Exception:
    logging.warn('failed to delete images for %s:%s' % (CONDA_CONTAINER, CONDA_TAG))


