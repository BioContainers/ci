#!/bin/bash

export GITHUB_STATUS_TOKEN=$GITHUB_STATUS_TOKEN
export JENKINS_URL=$JENKINS_URL
cd /home/ubuntu
. ci-proxy/bin/activate
gunicorn --pid /home/ubuntu/ci-proxy.pid -b 0.0.0.0:8080 --access-logfile /home/ubuntu/ci-proxy.log --error-logfile /home/ubuntu/ci-error.log ci-proxy:app

