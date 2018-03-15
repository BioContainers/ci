#!/bin/bash

# export GITHUB_STATUS_TOKEN=
cd /home/ubuntu
. ci-proxy/bin/activate
gunicorn --pid /home/ubuntu/ci-proxy.pid -b 127.0.0.1:8080 --access-logfile /home/ubuntu/ci-proxy.log --error-logfile /home/ubuntu/ci-error.log ci-proxy:app

