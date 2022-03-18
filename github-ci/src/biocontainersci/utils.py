import logging
import requests

class BiocontainersCIException(Exception):
    pass

def send_github_pr_comment(config, comment):
    if not config['pull_number']:
        logging.info('[github][comment] not a PR, skipping: ' + comment)
        return
    pr_id = config['pull_number']
    logging.warn('[github][comment] send comment to pr '+str(pr_id))
    logging.info('[github][comment] send msg '+str(comment))
    if not config['github']['token'] or not pr_id:
        logging.warn('[github][comment] github not configured or not a PR, not sending comment')
        return
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': 'token ' + config['github']['token']
    }

    github_url = 'https://api.github.com/repos/BioContainers/containers/issues/'  + str(pr_id) + '/comments'
    try:
        requests.post(
            github_url,
            json={
                'body': comment,
            },
            headers=headers
        )
    except Exception as e:
        logging.exception(str(e))

def send_status(config, software, status, msg=None):
    if not config['commit']:
        logging.warn('[github][status] no commit, skipping: ' + str(msg))
        return
    if not config['github']['token']:
        logging.warn('[github][status] github not configured, not sending comment: ' + str(msg))
        return
    repo = 'BioContainers/containers'
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
        'Authorization': 'token ' + config['github']['token']
    }
    try:
        github_url = 'https://api.github.com/repos/%s/statuses/%s' % (repo, config['commit'])
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