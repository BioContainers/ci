# containers backup

Check for biocontainers and bioconda container updates to copy them
to local backup registry and optionally to aws.
Also add security scan

Support full scan update or update from last repo check

## requirements

* nodejs >= 12 (tested 16)
* aws cli and aws credentials set in ~/.aws

## setup

    ls ~/.aws
    config  credentials
    
    # config
    [default]
    region = us-east-1

    # credentials
    [default]
    aws_access_key_id =
    aws_secret_access_key =

## run

node index.js --help

## CI

github CI will execute at regular interval. Script will check in workdir (see config.yml) for git repo clone.

* if not present, will clone repo and scan for all containers
* if present, will look *record* last commit, pull data, and look at modified files (so containers) to check only related containers (if they need a backup)

GitHub stops jobs after 24 hours, which can occur for very large updates. In this case, script is killed and a lock file will be left, preventing further cron jobs to run.
Lock file is to precent running multiple jobs at the same time. If this occurs (**wokrdir**/sync.lock already present), simply delete the lock file and run
manually the failed job (better in background...):

    # workdir = /mnt/data/sync
    # look at json file related to date failure
    ls -l /mnt/data/sync
    drwxr-xr-x   7 ubuntu ubuntu    4096 Jul 22 23:09 bioconda
    drwxr-xr-x 902 ubuntu ubuntu   36864 Jul 23 00:40 biocontainers
    -rw-r--r--   1 ubuntu ubuntu 1103453 Jul 20 23:49 biocontainers_1689894554195.json
    -rw-rw-r--   1 ubuntu ubuntu       0 Jul 23 07:10 sync.lock
    # example
    node index.js --backup --aws --conda --file /mnt/data/sync/biocontainers_1689894554195.json

json files are created at container lookup step, and deleted on success. In case of job failure, json file will be present and ease replay.
final solution is to delete **workdir**/bioconda|biocontainer and run without the --updated option to check for **all** containers (very long job....)

## example

### backup conda containers to registry AND aws

backup conda (quay.io) containers to aws since last run

node index.js --aws --conda --updated

### backup github dockerfile containers to registry AND aws

backup conda (quay.io) containers to aws since last run

node index.js --aws --docker --updated
