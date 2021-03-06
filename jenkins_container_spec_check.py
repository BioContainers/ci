from dockerfile_parse import DockerfileParser
import requests
import sys
import os
import logging
import re

import dockerparse_arg_fix

def send_comment(comment):
    if 'GITHUB_STATUS_TOKEN' not in os.environ:
        logging.info(str({
            'comment': str(comment),
        }))
        return
    logging.warn('Send comment: %s' % (str(comment)))
    repo = 'BioContainers/containers'
    commit = os.environ['COMMIT_SHA1']
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': 'token ' + str(os.environ['GITHUB_STATUS_TOKEN'])
    }
    try:
        if 'PULL_REQUEST_ID' in os.environ and os.environ['PULL_REQUEST_ID']:
            headers = {
                'Accept': 'application/vnd.github.v3.raw+json',
                'Authorization': 'token ' + str(os.environ['GITHUB_STATUS_TOKEN'])
            }

            github_url = 'https://api.github.com/repos/%s/issues/%s/comments' % (repo, os.environ['PULL_REQUEST_ID'])
        else:
            github_url = 'https://api.github.com/repos/%s/commits/%s/comments' % (repo, commit)
        res = requests.post(
            github_url,
            json={
                'body': comment,
            },
            headers=headers
        )
        logging.warn('Send comment info at %s: %s' % (github_url, str(res.status_code)))
        if res.status_code != 201:
            logging.warn(res.text)
            logging.warn('Auth token need repo public access')
    except Exception as e:
        logging.exception(str(e))

def send_status(software, status, msg=None):
    if 'GITHUB_STATUS_TOKEN' not in os.environ:
        logging.info(str({
            'software': str(software),
            'status': str(status),
            'msg': str(msg)
        }))
        return
    repo = 'BioContainers/containers'
    commit = os.environ['COMMIT_SHA1']
    info = 'Checking recipe metadata'
    if msg:
        info = ', '.join(msg)
    is_success = 'success'
    if status is None:
        is_success = 'pending'
    if status is False:
        is_success = 'failure'
        logging.error('Found some errors: %s' % (info))
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': 'token ' + str(os.environ['GITHUB_STATUS_TOKEN'])
    }
    try:
        github_url = 'https://api.github.com/repos/%s/statuses/%s' % (repo, commit)
        res = requests.post(
            github_url,
            json={
                'description': info,
                'state': is_success,
                'context': 'biocontainers/status/check/' + str(software)
            },
            headers=headers
        )
        logging.warn('Send status info at %s: %s' % (github_url, str(res.status_code)))
    except Exception as e:
        logging.exception(str(e))

docker_file = None
if len(sys.argv) > 1 and sys.argv[1]:
    docker_file = sys.argv[1]

if not docker_file or not os.path.exists(docker_file):
    logging.error("Could not find Dockerfile "+str(docker_file))
    send_status('',False, 'could not find any Dockerfile')
    sys.exit(1)

with open(docker_file, 'r') as content_file:
        content = content_file.read()

dfp = DockerfileParser()
dfp.content = content

#Need to double check on ARGs here
dfp = dockerparse_arg_fix.reload_arg_to_env(dfp, content)

labels = dfp.labels
status = True
msg = []
if 'software' not in labels or not labels['software']:
    status = False
    msg.append('software label not present')

software = labels['software'].strip()

pattern=re.compile("^([a-z0-9_-])+$")
if pattern.match(software) is None:
    logging.error(software + " has invalid name" )
    if 'container' in labels:
        if pattern.match(labels['container']) is None:
            status = False
            msg.append('software name is invalid for a container, it does not match expected regexp [a-z0-9_-], please fix label or use the *container* label to specify a software name compatible with container naming rules.')
    else:
        status = False
        msg.append('software name is invalid for a container, it does not match expected regexp [a-z0-9_-], please fix label or use the *container* label to specify a software name compatible with container naming rules.')

if 'base_image' not in labels or not labels['base_image']:
    status = False
    msg.append('base_image is missing in labels')

if 'software.version' not in labels or not labels['software.version']:
    status = False
    msg.append('software.version label not present (Upstream code version)')

if 'version' not in labels or not labels['version']:
    status = False
    msg.append('version label not present (Dockerfile version)')

if 'about.summary' not in labels or not labels['about.summary'] or len(labels['about.summary']) < 20:
    status = False
    msg.append('about.summary label not present or too short')

if 'about.home' not in labels or not labels['about.home']:
    status = False
    msg.append('about.home label not present')

if 'about.license' not in labels or not labels['about.license']:
    status = False
    msg.append('about.license label not present')

version = labels['software.version'].strip()
if 'version' in labels and labels['version']:
    version = version + '-' + labels['version'].strip()

send_status(software, status, msg)

try:
    if 'about.summary' in labels and len(labels['about.summary']) > 200:
        send_comment('about.summary is quite long, please keep it short < 200 chars.')

    # license checks
    spdx = requests.get('https://raw.githubusercontent.com/sindresorhus/spdx-license-list/master/spdx.json')
    licenses = spdx.json()
    if labels['about.license'].startswith('http'):
        send_comment('about.license field is a URL. license should be the license identifier (GPL-3.0 for example).')
    if 'about.license_file' not in labels:
        send_comment('please specify in about.license_file the location of the license file in the container, or a url to license for this release of the software.')
    elif labels['about.license'] != "Custom License" and labels['about.license'].replace('SPDX:', '').replace('spdx:', '') not in licenses:
        send_comment('about.license field is not in spdx list: https://spdx.org/licenses/, if it is a typo error, please fix it. If this is not a standard license, please specify *Custom License* and use *about.license_file* label to specify license location (in container or url).')

    # biotools check
    biotools_label = 'extra.identifiers.biotools'
    biotools = None
    if biotools_label in labels:
        biotools = labels[biotools_label].strip()

    else:
        bio = requests.get('https://bio.tools/api/tool/' + str(software) + '/?format=json')
        if bio.status_code != 404:
            send_comment('Found a biotools entry matching the software name (https://bio.tools/' + labels['software']+ '), if this is the same software, please add the extra.identifiers.biotools label to your Dockerfile')
        else:
            send_comment('No biotools label defined, please check if tool is not already defined in biotools (https://bio.tools) and add extra.identifiers.biotools label if it exists. If it is not defined, you can ignore this comment.')

    if biotools:
        entry = biotools
        if biotools.startswith('https://'):
            entry = biotools.split('/')[-1]
        bio = requests.get('https://bio.tools/api/tool/' + str(entry) + '/?format=json')
        if bio.status_code == 404:
            send_comment('Could not find the defined biotools entry, please check its name on biotools')
        else:
            logging.info("biotools entry is ok")

    # Check if exists in conda
    conda_url = 'https://bioconda.github.io/recipes/' + labels['software']+'/README.html'
    conda = requests.get(conda_url)
    if conda.status_code == 200:
        send_comment('Found an existing bioconda package for this software (' + conda_url + '), is this the same, then you should update the recipe in bioconda to avoid duplicates.')

except Exception as e:
    logging.warn(str(e))

if not status:
    sys.exit(1)
