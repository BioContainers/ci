import docker
import os
import logging
import re
import subprocess

import requests
import json
import boto3
# import botocore.vendored.requests.packages.urllib3 as urllib3


from biocontainersci.utils import send_github_pr_comment, send_status, BiocontainersCIException
from biocontainersci.biotools import Biotools

class CI:
    '''
    Class to manage build/check of containers
    '''

    def __init__(self, config):
        self.config = config
        self.docker_client = docker.DockerClient(base_url='unix://var/run/docker.sock')
        # urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def name(self, f):
        '''
        Container name, not local version suffix
        '''
        return 'biocontainers/' + f['container'] + ':' + f['version']

    def dockerhub_name(self, f):
        '''
        Docker registry name
        '''
        return 'biocontainers/' + f['container'] + ':' + f['tag']

    def local_name(self, f):
        '''
        Local registry name
        '''
        if not self.config['registry']['url']:
            return None
        return self.config['registry']['url'] + '/biocontainers/' + f['container'] + ':' + f['tag']

    def run_test(self, f:dict, test: str):
        '''
        Execute a test against container
        '''
        logging.info("[ci][test] run test: " + test)
        base_container_name = self.name(f)
        volumes={}
        volumes[self.workdir()] = {'bind': '/biocontainers', 'mode': 'ro'}
        logs = self.docker_client.containers.run(
            base_container_name,
            command=test,
            auto_remove=True,
            volumes=volumes
        )
        logging.info('[ci][test] logs: ' + str(logs))
        return True

    def run_tests(self, f):
        '''
        Run test-cmds.txt commands against container
        '''
        base_container_name = self.name(f)
        logging.info("[ci][test] " + base_container_name)
        tests_file = os.path.join(self.workdir(), f['container'], f['version'], 'test-cmds.txt')
        if not os.path.exists(tests_file):
            send_github_pr_comment(self.config, "No test-cmds.txt (test file) present, skipping tests")
            return
        tests = []
        with open(tests_file, 'r') as ft:
            tests = ft.readlines()
        status = True
        errors = []
        for test in tests:
            test_status = self.run_test(f, test)
            if not test_status:
                errors.append(test)
                status = False
        if not status:
            send_status(self.config, f['container'], False, "tests failed! " + ';'.join(errors))
            raise BiocontainersCIException('tests failed')
        send_status(self.config, f['container'], True, "All tests successful!")

    def docker_logs(self, build_logs):
        '''
        Show docker logs
        '''
        for chunk in build_logs:
            if 'stream' in chunk:
                for line in chunk['stream'].splitlines():
                    logging.info(line)


    def docker_push(self, repo, auth_config=None):
        '''
        Push to registry
        '''
        logging.info('[ci][push]' + repo)
        if self.config['dry']:
            logging.info('[ci] dry mode, do not push')
            return
        for line in self.docker_client.images.push(repo, stream=True, decode=True, auth_config=auth_config):
            logging.info(line)

    def biotools(self, f, labels):
        '''
        Check for biotools repo and create a PR to add new download
        '''
        if self.config['dry']:
            logging.info('[ci][biotools] dry mode, do not create PR')
            return
        if not self.config['biotools']['ssh_key'] or not os.path.exists(self.config['biotools']['ssh_key']):
            logging.info('[ci][biotools] no ssh key, skipping')
            return
        if not self.config['biotools']['token']:
            logging.info('[ci][biotools] no github token, skipping')
            return
        bt = Biotools(self.config)
        bt.run(f, labels)
        '''
        fpath = os.path.join(self.workdir(), f['container'], f['version'], 'Dockerfile')
        cpath = '/opt/biocontainers/' + f['container'] + '/' + f['version'] + '/Dockerfile'
        volumes={
            self.config['biotools']['ssh_key']: {'bind': '/root/.ssh/id_rsa', 'mode': 'ro'},
            fpath: {'bind': cpath, 'mode': 'ro'}
        }
        logs = self.docker_client.containers.run(
            image='biocontainers/biotools-pr',
            command=cpath,
            environment=[
                "GITHUB_BIOTOOLS_TOKEN=" + self.config['biotools']['token'],
                "BIOTOOLS_ID=" + f['biotools']
            ],
            volumes=volumes,
            auto_remove=True
        )
        '''


    def anchore(self, f):
        '''
        Add image to anchore security scan
        '''
        if not self.config['anchore']['url']:
            logging.warning('[ci][anchore] not configured, skipping')
            return
        try:
            logs = self.docker_client.containers.run(
                image='biocontainers/anchore-cli',
                command='image add docker.io/' + self.dockerhub_name(f),
                environment=["ANCHORE_CLI_URL=" + self.config['anchore']['url'], "ANCHORE_CLI_USER=" + self.config['anchore']['username'], "ANCHORE_CLI_PASS=" + self.config['anchore']['password']],
                auto_remove=True
            )
            logging.info('[ci][anchore] logs: ' + str(logs))
        except Exception as e:
            logging.exception('anchore failed, that is fine, an other process will take care of that: ' + str(e))

    def singularity(self, f):
        '''
        Convert to singularity and upload to s3
        '''
        sing_image = os.path.join(self.config.get('workdir', '/tmp'), 'singimage.sif')

        my_env = os.environ.copy()
        my_env['SINGULARITY_CACHEDIR'] = self.config['singularity']['tmp']
        my_env['SINGULARITY_TMPDIR'] = self.config['singularity']['tmp']
        try:
            convert_logs = subprocess.check_output(['singularity', 'build', sing_image, 'docker://' + self.dockerhub_name(f)], cwd=self.workdir(), env=my_env)
            logging.info('[ci][singularity] ' + str(convert_logs))
            '''
            volumes = {
                sing_image: {'bind': '/convertdir', 'mode': 'rw'}
            }
            logs = self.docker_client.containers.run(
                image='raynooo/docker-to-singularity',
                command='image add docker.io/' + self.dockerhub_name(f),
                environment=["IMAGE_REPO=biocontainers/" + f['container'], "IMAGE_TAG=" + f['tag'], "SOFTWARE_NAME=" + f['container']],
                auto_remove=True,
                volumes=volumes,
                privileged=True
            )
            logging.info('[ci][singularity] logs: ' + str(logs))
            '''
        except Exception as e:
            logging.exception('[ci][singularity] convert failed: ' + str(e))
            raise BiocontainersCIException('singularity conversion failed')


        if self.config['dry']:
            logging.info('[ci][singularity] dry mode, do not push image')
            return
        try:
            s3_client = boto3.client(service_name="s3", region_name=self.config['s3']['region'],
                            endpoint_url=self.config['s3']['endpoint'],
                            verify=False,
                            aws_access_key_id = self.config['s3']['access_key'],
                            aws_secret_access_key=self.config['s3']['secret_access_key'])
            s3_client.upload_file(sing_image, self.config['s3']['bucket'], 'SingImgsRepo/'+f['container'] + '/' + f['tag'] + '/' + f['container'] + '_' + f['tag'] + '.sif')
        except Exception as e:
            os.unlink(sing_image)
            raise BiocontainersCIException('singularity s3 upload failed')
        # need to be root...
        os.unlink(sing_image)
        #s3 = boto3.resource('s3')
        #data = open('/tmp/singimage', 'rb')
        #s3.Bucket(self.config['s3']['bucket']).put_object(Key='SingImgsRepo/'+f['container'] + '/' + f['tag'] + '/' + f['container'] + '_' + f['tag'] + '.img', Body=data)


    def workdir(self):
        return os.environ.get('GITHUB_WORKSPACE', os.getcwd())

    '''
    Execute CI workflow

    * build container
    * check labels
    TODO
    '''
    def workflow(self, f):
        base_container_name = self.name(f)
        logging.info('[ci][build] ' + base_container_name)

        # check for dockerfile
        with open(os.path.join(self.workdir(), f['container'], f['version'], 'Dockerfile'), 'r') as d:
            lines = d.readlines()
            for l in lines:
                if '.aws' in l:
                    logging.error('[ci] private biocontainers-ci directory access in dockerfile forbiden')
                    send_github_pr_comment(self.config, 'Forbiden access to biocontainers-ci private files in Dockerfile')
                    raise BiocontainersCIException('private biocontainers-ci directory access in dockerfile forbiden')
                if 'etc/biocontainers-ci' in l:
                    logging.error('[ci] private biocontainers-ci directory access in dockerfile forbiden')
                    send_github_pr_comment(self.config, 'Forbiden access to biocontainers-ci directory in Dockerfile')
                    raise BiocontainersCIException('private biocontainers-ci directory access in dockerfile forbiden')

        build_logs = []
        try:
            (docker_image, build_logs) = self.docker_client.images.build(
                path=os.path.join(self.workdir(), f['container'], f['version']),
                tag=base_container_name,
                squash=False,
                nocache=True,
                rm=True
            )
            self.docker_logs(build_logs)
        except Exception as e:
            self.docker_logs(build_logs)
            logging.exception('[ci][build] error ' + str(e))
            raise BiocontainersCIException('failed to build')
        status = False
        try:
            labels = docker_image.labels
            logging.info('[ci][build][labels] ' + json.dumps(labels))
            status = self.check_labels(f, labels)
            if not status:
                raise BiocontainersCIException('[ci][build][labels] failed')
            logging.info('[ci][build] ' + json.dumps(f))

            self.run_tests(f)

            if self.config['pull_number']:
                logging.info("[ci][build] pull request checks over")
                return True

            # tag for docker and local registry
            logging.info("tag for dockerhub")
            self.docker_client.images.build(
                path=os.path.join(self.workdir(), f['container'], f['version']),
                tag=self.dockerhub_name(f),
                squash=False,
                nocache=False,
                rm=True

            )
            if self.local_name(f):
                logging.info("tag for local registry")
                self.docker_client.images.build(
                    path=os.path.join(self.workdir(), f['container'], f['version']),
                    tag=self.local_name(f),
                    squash=False,
                    nocache=False,
                    rm=True
                )

            # push
            if self.config['dockerhub']['username']:
                self.docker_push(self.dockerhub_name(f), auth_config={
                    'username': self.config['dockerhub']['username'],
                    'password': self.config['dockerhub']['password']
                })
            else:
                logging.info('no dockerhub credentials, skipping')
            if self.local_name(f):
                self.docker_push(self.local_name(f))
            else:
                logging.info('no local registry, skipping')

            self.anchore(f)

            # bio-tools PR
            self.biotools(f, labels)

            # singularity
            self.singularity(f)

            status = True
        except Exception as e:
            logging.exception('[ci][workflow] error: ' + str(e))
            status = False
        
        try:
            self.docker_client.images.remove(image=self.name(f), force=True)
        except Exception:
            pass
        try:
            self.docker_client.images.remove(image=self.dockerhub_name(f), force=True)
        except Exception:
            pass
        try:
            self.docker_client.images.remove(image=self.local_name(f), force=True)
        except Exception:
            pass
        self.docker_client.images.prune()
        self.docker_client.containers.prune()
        return status
        


    '''
    Check labels in docker image
    '''
    def check_labels(self, f:dict, labels:dict):
        label_errors = []
        if 'software' not in labels or not labels['software']:
            label_errors.append('software label not present')
            status = False
        else:
            software =  labels['software']
            #labels['software'].strip()
            pattern=re.compile("^([a-z0-9_-])+$")
            if pattern.match(labels['software']) is None:
                logging.warning('[ci][labels] ' + software + " has invalid name, using directory name")
                software =  f['container']
                labels['container'] = f['container']

        if 'base_image' not in labels or not labels['base_image']:
            status = False
            label_errors.append('base_image is missing in labels')

        version = f['version']
        status = True
        if 'software.version' not in labels or not labels['software.version']:
            status = False
            label_errors.append('software.version label not present (Upstream code version)')
        elif version != labels['software.version'].strip():
            status = False
            label_errors.append('software.version label not matching directory version name')
        else:
            version = labels['software.version'].strip()

        if 'version' not in labels or not labels['version']:
            status = False
            label_errors.append('version label not present (Dockerfile version)')

        if 'about.summary' not in labels or not labels['about.summary'] or len(labels['about.summary']) < 20:
            status = False
            label_errors.append('about.summary label not present or too short')

        if 'about.home' not in labels or not labels['about.home']:
            status = False
            label_errors.append('about.home label not present')

        if 'about.license' not in labels or not labels['about.license']:
            status = False
            label_errors.append('about.license label not present')

        if 'version' in labels and labels['version']:
            version = version + '_cv' + labels['version'].strip()
        else:
            version = version + '_cv1'
        f['tag'] = version

        send_status(self.config, software, status, label_errors)

        # Warnings only
        try:
            if 'about.summary' in labels and len(labels['about.summary']) > 200:
                send_github_pr_comment(self.config, 'about.summary is quite long, please keep it short < 200 chars.')

            # license checks
            spdx = requests.get('https://raw.githubusercontent.com/sindresorhus/spdx-license-list/master/spdx.json')
            licenses = spdx.json()
            if labels['about.license'].startswith('http'):
                send_github_pr_comment(self.config, 'about.license field is a URL. license should be the license identifier (GPL-3.0 for example).')
            if 'about.license_file' not in labels:
                send_github_pr_comment(self.config, 'please specify in about.license_file the location of the license file in the container, or a url to license for this release of the software.')
            elif labels['about.license'] != "Custom License" and labels['about.license'].replace('SPDX:', '').replace('spdx:', '') not in licenses:
                send_github_pr_comment(self.config, 'about.license field is not in spdx list: https://spdx.org/licenses/, if it is a typo error, please fix it. If this is not a standard license, please specify *Custom License* and use *about.license_file* label to specify license location (in container or url).')

            # biotools check
            biotools_label = 'extra.identifiers.biotools'
            biotools = None
            if biotools_label in labels:
                biotools = labels[biotools_label].strip()

            else:
                bio = requests.get('https://bio.tools/api/tool/' + str(software) + '/?format=json')
                if bio.status_code != 404:
                    send_github_pr_comment(self.config, 'Found a biotools entry matching the software name (https://bio.tools/' + labels['software']+ '), if this is the same software, please add the extra.identifiers.biotools label to your Dockerfile')
                else:
                    send_github_pr_comment(self.config, 'No biotools label defined, please check if tool is not already defined in biotools (https://bio.tools) and add extra.identifiers.biotools label if it exists. If it is not defined, you can ignore this comment.')

            if biotools:
                entry = biotools
                if biotools.startswith('https://'):
                    entry = biotools.split('/')[-1]
                bio = requests.get('https://bio.tools/api/tool/' + str(entry) + '/?format=json')
                if bio.status_code == 404:
                    send_github_pr_comment(self.config, 'Could not find the defined biotools entry, please check its name on biotools')
                else:
                    logging.info("biotools entry is ok")

            # Check if exists in conda
            conda_url = 'https://bioconda.github.io/recipes/' + labels['software']+'/README.html'
            conda = requests.get(conda_url)
            if conda.status_code == 200:
                send_github_pr_comment(self.config, 'Found an existing bioconda package for this software (' + conda_url + '), is this the same, then you should update the recipe in bioconda to avoid duplicates.')

        except Exception as e:
            logging.warn('[ci][labels] error: ' + str(e))

        return status