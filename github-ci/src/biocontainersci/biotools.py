# install requires dockerfile_parse requests gitpython
# expect Dockerfile path as argv 1
# expect env var GITHUB_BIOTOOLS_TOKEN (to create PR)
# ssh rsa key must be mounted in container if any

import shutil
import requests
import sys
import os
import logging
import re
import git
import datetime
from copy import deepcopy
from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

from biocontainersci.utils import BiocontainersCIException

class Biotools:

    GIT_REPO = 'git@github.com:bio-tools/content.git'
    BOT_LABEL = 'biocontainers-bot-import'

    def __init__(self, config):
        self.config = config
        self.REPO = os.path.join(config.get('tmpdir', '/tmp'), 'biotools-content')

    def repo_setup(self, branch):
        repo = None
        if os.path.exists(self.REPO):
            repo = git.Repo(self.REPO)
            mygit = repo.git
            mygit.fetch('origin', 'master')
            mygit.checkout('master')
            if branch is not None:
                logging.info("Use existing repo, checkout to %s" % branch)
                mygit.config('--local', 'user.name', 'Biocontainers bot')
                mygit.checkout(branch)
                return (repo, branch)

        else:
            repo = git.Repo.clone_from(self.GIT_REPO, self.REPO, branch='master')

        mygit = repo.git
        mygit.config('--local', 'user.name', 'Biocontainers bot')

        if branch is None:
            branch = 'biocontainers-bot-import-%d' % datetime.datetime.now().timestamp()
            mygit.checkout('HEAD', b=branch)
        else:
            mygit.fetch('origin', branch)
            mygit.checkout(branch)
        logging.info("[biotools] Init repo, use branch %s" % branch)
        return (repo, branch)

    def get_pr_branch(self, id):
        github_url = 'https://api.github.com/repos/bio-tools/content/pulls/%s' % id
        res = requests.get(github_url)
        pr = res.json()
        pr_branch = pr['head']['ref']
        logging.info("[biotools] PR %d branch = %s" % (id, pr_branch))
        return pr_branch

    def has_pr(self):
        github_url = 'https://api.github.com/search/issues'
        res = requests.get(github_url, params={
            'q': 'is:pr state:open label:%s repo:bio-tools/content' % self.BOT_LABEL
        })
        # ?q=is:pr%20state:open%20label:%20repo:bio-tools/content'
        if res.status_code not in [200]:
            return None
        issues = res.json()
        for issue in issues['items']:
            # Take first found
            logging.info("[biotools] Found existing PR %d" % issue['number'])
            branch = self.get_pr_branch(issue['number'])
            return branch
        logging.info("[biotools] No existing PR found")
        return None

    def create_pr(self, branch):
        logging.info("[biotools] Create new PR for branch %s" % branch)
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'Authorization': 'token ' + self.config['biotools']['token']
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
            logging.error("[biotools] Failed to create pull request: %s", res.text)
            return False
        pr = res.json()
        issue = pr['number']
        logging.info("[biotools] PR %d created" % issue)
        github_url = 'https://api.github.com/repos/%s/issues/%d' % ("bio-tools/content", issue)

        res = requests.post(
                github_url,
                json={
                    'labels': [self.BOT_LABEL],
                },
                headers=headers
        )
        if not res.status_code in [200]:
            logging.error("Failed to add issue label: %d" % res.status_code)

        logging.info("Tagged issue: %d" % issue)
        return True

    def run(self, f, labels, branch=None):
        # use an existing branch ?
        has_pr_open = False
        if branch is not None:
            logging.info("[biotools] Branch %s requested" % branch)
            has_pr_open = True

        # biotools check
        biotools_label = 'extra.identifiers.biotools'
        biotools = None
        if biotools_label not in labels:
            logging.warning("[biotools] No biotools label")
        else:
            biotools = labels[biotools_label].strip()
            logging.info("[biotools] biotools label " + biotools)

        name = f['container']
        container_version = f['tag']

        if branch is None:
            # no branch specified, look for an existing PR
            branch = self.has_pr()
            if branch is not None:
                has_pr_open = True

        error = False
        try:
            (repo, branch) = self.repo_setup(branch)

            tmpdir =  self.REPO + '/data/'
            dirname = tmpdir + name 
            biocontainers_file = tmpdir + name + '/biocontainers.yaml'
            if biotools is not None:
                dirname = tmpdir + biotools
                biocontainers_file = tmpdir + biotools + '/biocontainers.yaml'

            if not os.path.exists(dirname):
                os.makedirs(dirname)

            clabels = {}
            for k, v in labels.items():
                clabels[k] = v

            data = {
                    'software': name,
                    'labels': deepcopy(clabels),
                    'versions': []
                    }
            softwares = {'softwares': {}}
            softwares["softwares"][name] = data
            if os.path.exists(biocontainers_file):
                with open(biocontainers_file) as fp:
                    softwares = load(fp, Loader=Loader)

            if name not in softwares["softwares"]:
                softwares["softwares"][name] = data

            exists = False
            for download in softwares["softwares"][name]["versions"]:
                if download["version"] == container_version:
                    exists = True
                    break

            if not exists:
                new_download = {
                    "url": "biocontainers/" + name + ":" + container_version,
                    "version": container_version,
                    "type": "Container file",
                    "labels": deepcopy(clabels)
                }
                softwares["softwares"][name]["versions"].append(new_download)

                with open(biocontainers_file, 'w') as fp:
                    dump(softwares, fp, Dumper=Dumper)

                repo.index.add([biocontainers_file])
                if biotools is not None:
                    repo.index.commit("Add version for %s:%s" % (biotools, container_version))
                else:
                    repo.index.commit("Add version for %s:%s" % (name, container_version))
                try:
                    logging.info("[biotools] Push to branch %s" % branch)

                    if not has_pr_open:
                        repo.git.push('-u', 'origin', branch)
                        self.create_pr(branch)
                    else:
                        repo.git.push()
                except Exception as e:
                    logging.exception('[biotools] failed to push fork: ' + str(e))
                    raise BiocontainersCIException('biotools PR creation failed')
            else:
                logging.info('[biotools] nothing to do')

        except Exception as e:
            logging.exception('[biotools] error: ' + str(e))
            error = True

        if error:
            try:
                shutil.rmtree(self.REPO)
            except Exception:
                pass
            raise BiocontainersCIException('something went wrong')
