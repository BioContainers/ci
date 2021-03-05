from flask import Flask
from flask import request
import json
import copy
import logging
import os

import arrow
import requests

app = Flask(__name__)

# jenkins_url = 'http://localhost:8080/job/'
# may need auth: http://user:apikey@local....'
# need to deactivare cross site forgery security in jenkins
jenkins_url = 'http://cluster.local:30752/jenkins/job/'

if 'JENKINS_URL' in os.environ and os.environ['JENKINS_URL']:
    jenkins_url = os.environ['JENKINS_URL']

if 'DEBUG' in os.environ and os.environ['DEBUG'] == '1':
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)

if 'GITHUB_STATUS_TOKEN' not in os.environ or not os.environ['GITHUB_STATUS_TOKEN']:
    logging.debug('no github token, proxy will not notify errors to github')


def send_github_pr_comment(pr_id, comment):
    logging.warn('send comment to pr '+str(pr_id))
    if 'GITHUB_STATUS_TOKEN' not in os.environ or not os.environ['GITHUB_STATUS_TOKEN']:
        return
    logging.warn('send msg '+str(comment))
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': 'token ' + str(os.environ['GITHUB_STATUS_TOKEN'])
    }

    github_url = 'https://api.github.com/repos/BioContainers/containers/issues/'  + str(pr_id) + '/comments'

    res = requests.post(
                        github_url,
                        json={
                            'body': comment,
                        },
                        headers=headers
    )

@app.route('/ci-proxy', methods=['GET'])
def ping():
    return "pong"

@app.route('/ci-proxy/hook', methods=['POST'])
def payload():
        # print(request.content_type)
        # print(str(request.form))
        # logging.error(request.form)
        try:
            payload = json.loads(request.form.get('payload'))
            if 'zen' in payload:
                logging.debug('test url , accept and quit')
                return 'test ok'

            commits = []
            if 'commits' in payload:
                commits = payload['commits']
            elif 'pull_request' in payload:
                logging.debug('pull request action: ' + payload['action'])
                res = requests.get(
                    payload['pull_request']['url'] + '/files',
                    headers={'Accept': 'application/vnd.github.v3+json'}
                )
                files = res.json()
                containers = []
                for pull_file in files:
                    filenames = pull_file['filename'].split('/')
                    # container_path = '/'.join(pull_file['filename'].split('/')[:-1])
                    container_path = '/'.join([filenames[0], filenames[1]])
                    if container_path not in containers:
                        containers.append(container_path)
                if len(containers) > 1 or len(containers) == 0:
                    logging.error("ko, can't modify multiple containers in a same pull request")
                    send_github_pr_comment(payload['number'], "can't modify multiple containers in a same pull request")
                    return "ko, can't modify multiple containers in a same pull request"
                container_dir = containers[0].split('/')
                if len(container_dir) != 2:
                    comment = "Invalid structure, Dockerfile must be in directory softwarename/softwareversion/Dockerfile"
                    send_github_pr_comment(payload['number'], comment)
                    return comment
                #r = requests.post(jenkins_url + 'container-testci-pr/buildWithParameters?FORCE_CONTAINER='+container_dir[0]+'&FORCE_TOOL_VERSION='+container_dir[1]+'&PULL_REQUEST_ID='+str(payload['number']) + '&FORCE_SHA1=' + payload['pull_request']['head']['sha'])
                params = {
                    'FORCE_CONTAINER': container_dir[0],
                    'FORCE_TOOL_VERSION': container_dir[1],
                    'PULL_REQUEST_ID': str(payload['number']),
                    'FORCE_SHA1': payload['pull_request']['head']['sha']
                }
                r = requests.post(jenkins_url + 'container-testci-pr/buildWithParameters', params=params)
                return "ok"

            new_commits = {}
            for commit in commits:
                modified_container = []
                modified_commits = []
                updated = False
                if 'added' not in commit:
                    commit['added'] = []
                for modified in commit['added']:
                    if len(modified.split('/')) == 2:
                        modified = os.path.join(modified, 'Dockerfile')
                    container_path = '/'.join(modified.split('/')[:-1])
                    if container_path and container_path not in modified_container:
                        modified_container.append(container_path + '/Dockerfile')
                        updated = True
                if 'modified' not in commit:
                    commit['modified'] = []
                for modified in commit['modified']:
                    container_path = '/'.join(modified.split('/')[:-1])
                    if container_path and container_path not in modified_container:
                        modified_container.append(container_path + '/Dockerfile')
                        updated = True
                if updated:
                    modified_commits.append(commit['id'])
                for modif in modified_container:
                    commit['added'] = []
                    commit['modified'] = [modif]
                    commit['removed'] = []
                    container_dir = '/'.join(modif.split('/')[:-1])
                    commit['message'] = container_dir + ':' + commit['message']
                    commit_dict = copy.deepcopy(payload)
                    commit_dict['commits'] = [commit]
                    commit_dict['head_commit'] = commit
                    commit_dict['added'] = []
                    commit_dict['removed'] = []
                    commit_dict['modified'] = [modif]
                    if container_dir not in new_commits:
                        new_commits[container_dir] = {'date': arrow.get(commit['timestamp']).datetime, 'payload': commit_dict}
                    else:
                        if new_commits[container_dir]['date'] > arrow.get(commit['timestamp']).datetime:
                            new_commits[container_dir] = {'date': arrow.get(commit['timestamp']).datetime, 'payload': commit_dict}
            event = request.headers['X-GitHub-Event']
            if not new_commits and 'GITHUB_STATUS_TOKEN' in os.environ:
                    headers = {
                        'Accept': 'application/vnd.github.v3+json',
                        'Authorization': 'token ' + str(os.environ['GITHUB_STATUS_TOKEN'])
                    }
                    if 'pull_request' in payload:
                        github_url = payload['pull_request']['url'] + '/comments'
                    else:
                        github_url = payload['head_commit']['url'] + '/comments'

                    res = requests.post(
                        github_url,
                        json={
                            'body': 'no file modified, skipping request',
                        },
                        headers=headers
                    )
                    logging.warn('No commit to dispatch')

            for d in new_commits:
                logging.debug('headers: '+str(request.headers))
                logging.debug('data: '+json.dumps(new_commits[d]['payload']))
                container_dir = d.split('/')
                logging.debug('Call:' + jenkins_url + 'container-testci/buildWithParameters?FORCE_CONTAINER='+container_dir[0]+'&FORCE_TOOL_VERSION='+container_dir[1]+'&FORCE_SHA1='+new_commits[d]['payload']['head_commit']['id'])
                params = {
                    'FORCE_CONTAINER': container_dir[0],
                    'FORCE_TOOL_VERSION': container_dir[1],
                    'FORCE_SHA1': new_commits[d]['payload']['head_commit']['id']
                }
                #r = requests.get(jenkins_url + 'container-testci/buildWithParameters?FORCE_CONTAINER='+container_dir[0]+'&FORCE_TOOL_VERSION='+container_dir[1]+'&FORCE_SHA1='+new_commits[d]['payload']['head_commit']['id'])
                r = requests.get(jenkins_url + 'container-testci/buildWithParameters', params=params)
                logging.debug('post result '+str(r.status_code))
                logging.debug(str(r.text))
                # print(json.dumps(new_commits[d]['payload']))
        except Exception as e:
            logging.exception(str(e))
        return "ok"


if __name__ == '__main__':
          app.run(host='0.0.0.0', port=8080)
