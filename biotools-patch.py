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
import json
from collections import OrderedDict
import dockerparse_arg_fix
import git
     
def repoSetup(name, version):
    if os.path.exists('/tmp/biotools-content'):
        repo = git.Repo('/tmp/biotools-content')
        return repo
    repo = git.Repo.clone_from("https://github.com/bio-tools/content.git", os.path.join('/tmp', 'biotools-content'), branch='master')
    fork = repo.create_remote('fork', 'git@github.com:biocontainers-bot/content.git')
    mygit = repo.git
    mygit.checkout('HEAD', b='biocontainers-' + name + '-' + version)
    return repo 

def createPR(name, version):
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': 'token ' + str(os.environ['GITHUB_BIOTOOLS_TOKEN'])
    }
    github_url = 'https://api.github.com/repos/%s/pulls' % ("bio-tools/content")
    res = requests.post(
            github_url,
            json={
                'title': "biocontainers new version PR: %s:%s" % (name, containerVersion),
                'head': "biocontainers-bot:biocontainers-%s-%s" % (name, version),
                "base": "master"
            },
            headers=headers
        )
    logging.info("Res %d: %s", res.status_code, res.text)


docker_file = None
if len(sys.argv) > 1 and sys.argv[1]:
    docker_file = sys.argv[1]

if not docker_file or not os.path.exists(docker_file):
    logging.error("Could not find Dockerfile "+str(docker_file))
    sys.exit(1)

with open(docker_file, 'r') as content_file:
        content = content_file.read()

dfp = DockerfileParser()
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

repo = None
if biotools is not None:
    repo = repoSetup(biotools, containerVersion)
else:
    repo = repoSetup(name, containerVersion)

#bioFile = None
#if biotools is not None:
#    bioFile = '/tmp/biotools-content/data/' + biotools + '/' + biotools + '.json'

dirname = '/tmp/biotools-content/data/' + name 
bioContainersFile = '/tmp/biotools-content/data/' + name + '/biocontainers.json'
if biotools is not None:
    dirname = '/tmp/biotools-content/data/' + biotools
    bioContainersFile = '/tmp/biotools-content/data/' + biotools + '/biocontainers.json'

if not os.path.exists(dirname):
    os.makedirs(dirname)

#if not os.path.exists(bioFile):
#    logging.error("Did not found biotools metadata file %s" % (bioFile))
#    sys.exit(1)


data = {
        'software': name,
        'labels': labels,
        'versions': []
        }
softwares = {'softwares': {}}
softwares["softwares"][name] = data
if os.path.exists(bioContainersFile):
    with open(bioContainersFile) as fp:
        softwares = json.load(fp, object_pairs_hook=OrderedDict)

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
        "labels": labels
    }
    softwares["softwares"][name]["versions"].append(newDownload)

    with open(bioContainersFile, 'w') as fp:
        json.dump(softwares, fp, indent=4, separators=(', ', ': '), ensure_ascii=False)

    repo.index.add([bioContainersFile])
    repo.index.commit("Add version for %s:%s" % (name, containerVersion))
    repo.git.push('-u', 'fork', 'biocontainers-%s-%s' % (name, containerVersion))
        
    if biotools is not None:
        createPR(biotools, containerVersion)
    else:
        createPR(name, containerVersion)


