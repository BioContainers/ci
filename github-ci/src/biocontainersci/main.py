import json
import copy
import logging
import os
import re
import subprocess
import sys
import click

import requests
import yaml
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

from biocontainersci.ci import CI
from biocontainersci.utils import send_github_pr_comment, send_status

class BiocontainersException(Exception):
    pass



def git_modified_files(config, commit):
    files = []
    workdir = os.environ.get('GITHUB_WORKSPACE', os.getcwd())
    modified_files = subprocess.check_output(['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', commit], cwd=workdir)
    if not modified_files:
        return []
    for f in modified_files.decode('UTF-8').split('\n'):
        logging.info('[ci][github][commit] ' + f)
        if f.endswith('Dockerfile') and os.path.exists(f):
            dockerfile = f.split('/')
            files.append({
                'container': dockerfile[0],
                'version': dockerfile[1],
            })
    return files

def github_pull_request_files(config):
    repo = os.environ['GITHUB_REPOSITORY']
    # refs/pull/<pr_number>/merge
    url = f"/repos/{repo}/pulls/{config['pull_number']}/files"
    gh_url = os.environ['GITHUB_API_URL']

    res = requests.get(
        gh_url + url,
        headers={'Accept': 'application/vnd.github.v3+json'}
    )
    files = res.json()
    containers = []
    for pull_file in files:
        if '.github' in pull_file['filename']:
            msg = 'Cannot modify github CI files....'
            logging.error(msg)
            send_github_pr_comment(config, msg) 
            raise BiocontainersException(msg)
        logging.info('[ci][github][pull request] ' + pull_file['filename'])
        filenames = pull_file['filename'].split('/')
        if len(filenames) < 2:
            msg = "You're trying to update a file not related to a container: " + str(pull_file['filename']) + ", this is forbidden"
            logging.error(msg)
            send_github_pr_comment(config, msg) 
            raise BiocontainersException(msg)
        container_path = '/'.join([filenames[0], filenames[1]])
        if container_path not in containers:
            containers.append(container_path)

    if len(containers) > 1 or len(containers) == 0:
        msg = "can't modify multiple containers in a same pull request"
        logging.error(msg)
        send_github_pr_comment(config, msg)
        raise BiocontainersException(msg)

    container_dir = containers[0].split('/')
    if len(container_dir) != 2:
        msg = "Invalid structure, Dockerfile must be in directory softwarename/softwareversion/Dockerfile"
        logging.error(msg)
        send_github_pr_comment(config, msg)
        raise BiocontainersException(msg)

    params = [{
        'container': container_dir[0],
        'version': container_dir[1],
    }]
    return params


def github(config):

    files = []
    if config['pull_number']:
        logging.info('Pull request')
        files = github_pull_request_files(config)
        # /repos/{owner}/{repo}/pulls/{pull_number}/files
    elif config['commit']:
        files = git_modified_files(config, config['commit'])
    return files


def bioworkflow(config, f):
    ci = CI(config)
    return ci.workflow(f)

@click.command()
@click.option('--file', help='Dockerfile')
@click.option('--commit', help='Commit SHA')
@click.option('--dry/--no-dry', default=False, help="dry run mode")
def run(file, commit, dry):
    logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
    config = None
    with open(os.environ.get('CONFIG', '/etc/biocontainers-ci/config.yml')) as f:
        config = yaml.load(f, Loader=yaml.Loader)

    files = []
    config['commit'] = None
    config['dry'] = dry
    config['pull_number'] = None
    try:
        if file:
            if not os.path.exists(file):
                raise BiocontainersException('file not found')
            elts = file.split('/')
            files = [{
                'container': elts[len(elts)-3],
                'version': elts[len(elts)-2],
            }]
        else:
            if commit:
                logging.info('Commit ' + commit)
                config['commit'] = commit

            if os.environ.get('GITHUB_SHA', None):
                commit = os.environ['GITHUB_SHA']
                logging.info('Commit ' + commit)
                config['commit'] = commit

            if os.environ.get('GITHUB_REF', None):
                ref = os.environ['GITHUB_REF']
                m = re.search('refs/pull/(\d+)/merge', ref)
                if m:
                    pull_number = m.group(1)
                    config['pull_number'] = pull_number
                    logging.info('[ci] pull request ' + str(pull_number))

            files = github(config)
    except Exception as e:
        logging.error('Something went wrong: ' + str(e))
        sys.exit(1)

    if not files:
        send_status(config, '',False, 'could not find any Dockerfile')
        sys.exit(1)

    for f in files:
        status = bioworkflow(config, f)
        if not status:
            sys.exit(1)

if __name__ == '__main__':
    run()
