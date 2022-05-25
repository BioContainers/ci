# containers backup

Check for biocontainers and bioconda container updates to copy them
to local backup registry and optionally to aws.
Also add security scan

Support full scan update or update from last repo check

## setup

* nodejs
* aws cli and aws credentials set in ~/.aws

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
