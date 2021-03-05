# install requires dockerfile_parse requests gitpython
# expect Dockerfile path as argv 1
# expect env var GITHUB_BIOTOOLS_TOKEN (to create PR)
# ssh rsa key must be mounted in container if any

from dockerfile_parse import DockerfileParser
import requests
import sys
import os
import logging
import re
# import json
# from collections import OrderedDict
import dockerparse_arg_fix
import git
import datetime
from copy import deepcopy
from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

logging.basicConfig(level=logging.INFO)
BOT_LABEL = 'biocontainers-bot-import'
GIT_REPO = 'git@github.com:bio-tools/content.git'
# GIT_REPO = 'git@github.com:biocontainers-bot/content.git'

def repoSetup(branch):
    repo = None
    if os.path.exists('/tmp/biotools-content'):
        repo = git.Repo('/tmp/biotools-content')
        if branch is not None:
            logging.info("Use existing repo, checkout to %s" % branch)
            mygit = repo.git
            mygit.config('--local', 'user.name', 'Biocontainers bot')
            mygit.checkout(branch)
            return (repo, branch)

    else:
        repo = git.Repo.clone_from(GIT_REPO, os.path.join('/tmp', 'biotools-content'), branch='master')
    # fork = repo.create_remote('fork', 'git@github.com:biocontainers-bot/content.git')
    mygit = repo.git
    mygit.config('--local', 'user.name', 'Biocontainers bot')

    if branch is None:
        branch = 'biocontainers-bot-import-%d' % datetime.datetime.now().timestamp()
        mygit.checkout('HEAD', b=branch)
    else:
        mygit.fetch('origin', branch)
        mygit.checkout(branch)
    logging.info("Init repo, use branch %s" % branch)
    return (repo, branch)

def getPRBranch(id):
    github_url = 'https://api.github.com/repos/bio-tools/content/pulls/%s' % id
    res = requests.get(github_url)
    pr = res.json()
    pr_branch = pr['head']['ref']
    logging.info("PR %d branch = %s" % (id, pr_branch))
    return pr_branch

def hasPR():
    github_url = 'https://api.github.com/search/issues'
    res = requests.get(github_url, params={
        'q': 'is:pr state:open label:%s repo:bio-tools/content' % BOT_LABEL
    })
    # ?q=is:pr%20state:open%20label:%20repo:bio-tools/content'
    if res.status_code not in [200]:
        return None
    issues = res.json()
    for issue in issues['items']:
        # Take first found
        logging.info("Found existing PR %d" % issue['number'])
        branch = getPRBranch(issue['number'])
        return branch
    logging.info("No existing PR found")
    return None

def createPR(branch):
    logging.info("Create new PR for branch %s" % branch)
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': 'token ' + str(os.environ['GITHUB_BIOTOOLS_TOKEN'])
    }
    github_url = 'https://api.github.com/repos/%s/pulls' % ("bio-tools/content")
    res = requests.post(
            github_url,
            json={
                'title': "biocontainers-bot metadata import PR",
                'head': branch,
                "base": "master"
            },
            headers=headers
    )
    if not res.status_code in [200, 201]:
        logging.error("Failed to create pull request: %s", res.text)
        return False
    pr = res.json()
    issue = pr['number']
    logging.info("PR %d created" % issue)
    github_url = 'https://api.github.com/repos/%s/issues/%d' % ("bio-tools/content", issue)

    res = requests.post(
            github_url,
            json={
                'labels': [BOT_LABEL],
            },
            headers=headers
    )
    if not res.status_code in [200]:
        logging.error("Failed to add issue label: %d" % res.status_code)

    logging.info("Tagged issue: %d" % issue)
    return True


docker_file = None
if len(sys.argv) > 1 and sys.argv[1]:
    docker_file = sys.argv[1]
else:
    logging.error("no Dockerfile specified")
    sys.exit(1)

# use an existing branch ?
branch = None
hasPROpen = False
if len(sys.argv) > 2 and sys.argv[2]:
    # if branch specified, we suppose there is an existing PR for this branch
    branch = sys.argv[2]
    logging.info("Branch %s requested" % branch)
    hasPROpen = True

if not docker_file or not os.path.exists(docker_file):
    logging.error("Could not find Dockerfile "+str(docker_file))
    sys.exit(1)

with open(docker_file, 'r') as content_file:
        content = content_file.read()

dfp = DockerfileParser(path='/tmp')
dfp.content = content

#Need to double check on ARGs here
dfp = dockerparse_arg_fix.reload_arg_to_env(dfp, content)

labels = dfp.labels

# biotools check
biotools_label = 'extra.identifiers.biotools'
biotools = None
if biotools_label not in labels:
    logging.error("No biotools label")
    # sys.exit(0)
else:
    biotools = labels[biotools_label].strip()

version = labels["software.version"]
versionExtra = labels["version"]
name = labels["software"]
if 'container' in labels:
    name = labels['container']
containerVersion = version + "-" + versionExtra

if branch is None:
    # no branch specified, look for an existing PR
    branch = hasPR()
    if branch is not None:
        hasPROpen = True

(repo, branch) = repoSetup(branch)

dirname = '/tmp/biotools-content/data/' + name 
bioContainersFile = '/tmp/biotools-content/data/' + name + '/biocontainers.yaml'
if biotools is not None:
    dirname = '/tmp/biotools-content/data/' + biotools
    bioContainersFile = '/tmp/biotools-content/data/' + biotools + '/biocontainers.yaml'

if not os.path.exists(dirname):
    os.makedirs(dirname)

cLabels = {}
for k, v in labels.items():
    cLabels[k] = v

data = {
        'software': name,
        'labels': deepcopy(cLabels),
        'versions': []
        }
softwares = {'softwares': {}}
softwares["softwares"][name] = data
if os.path.exists(bioContainersFile):
    with open(bioContainersFile) as fp:
        # softwares = json.load(fp, object_pairs_hook=OrderedDict)
        softwares = load(fp, Loader=Loader)

if name not in softwares["softwares"]:
    softwares["softwares"][name] = data

exists = False
for download in softwares["softwares"][name]["versions"]:
    if download["version"] == containerVersion:
        exists = True
        break

if not exists:
    newDownload = {
        "url": "biocontainers/" + name + ":" + containerVersion,
        "version": containerVersion,
        "type": "Container file",
        "labels": deepcopy(cLabels)
    }
    softwares["softwares"][name]["versions"].append(newDownload)

    with open(bioContainersFile, 'w') as fp:
        # json.dump(softwares, fp, indent=4, separators=(', ', ': '), ensure_ascii=False)
        dump(softwares, fp, Dumper=Dumper)

    repo.index.add([bioContainersFile])
    if biotools is not None:
        repo.index.commit("Add version for %s:%s" % (biotools, containerVersion))
    else:
        repo.index.commit("Add version for %s:%s" % (name, containerVersion))
    try:
        logging.info("Push to branch %s" % branch)

        if not hasPROpen:
            repo.git.push('-u', 'origin', branch)
            createPR(branch)
        else:
            repo.git.push()
    except Exception as e:
        logging.exception('failed to push fork: ' + str(e))
        sys.exit(0)
