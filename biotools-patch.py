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
                'title': "biocontainers new download PR: %s:%s" % (name, containerVersion),
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
    sys.exit(0)
biotools = labels[biotools_label].strip()

version = labels["software.version"]
versionExtra = labels["version"]
name = labels["software"]
containerVersion = version + "-" + versionExtra

repo = repoSetup(biotools, containerVersion)

bioFile = '/tmp/biotools-content/data/' + biotools + '/' + biotools + '.json'
if not os.path.exists(bioFile):
    logging.error("Did not found biotools metadata file %s" % (bioFile))
    sys.exit(1)

data = {}
with open(bioFile) as fp:
    data = json.load(fp, object_pairs_hook=OrderedDict)

exists = False
for download in data["download"]:
    if download["version"] == containerVersion:
        exists = True
        break

if not exists:
    newDownload = {
        "url": "biocontainers/" + name + ":" + containerVersion,
        "version": containerVersion,
        "type": "Container file"
    }
    data["download"].append(newDownload)

    with open(bioFile, 'w') as fp:
        json.dump(data, fp, indent=4, separators=(', ', ': '), ensure_ascii=False)

    repo.index.add([bioFile])
    repo.index.commit("Add download for %s:%s" % (biotools, containerVersion))
    repo.git.push('-u', 'fork', 'biocontainers-%s-%s' % (biotools, containerVersion))
        

    createPR(biotools, containerVersion)


