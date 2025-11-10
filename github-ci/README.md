# biocontainersci

Package to build/check biocontainers in github or local CI

## requirements

* Docker
* Singularity
  * http://ftp.fr.debian.org/debian/pool/main/s/singularity-container/singularity-container_3.9.5+ds1-3_amd64.deb
  * https://sylabs.io/guides/3.0/user-guide/installation.html

* anchore server
* docker registry

## config

expects /etc/biocontainers-ci/config.yml config file or file defined by env var config.yml

Set ssh config in ~/.ssh/config

    Host github.com
        StrictHostKeyChecking no"
        IdentityFile /etc/biocontainers-ci/id_rsa

## install

As root:

    pip install -r requirements.txt
    pip install .

## run

In repo clone:

    CONFIG=config.yml python src/biocontainers-ci.py

Example

    CONFIG=../../biocontainers-todo/ci/config.yml python ../../biocontainers-todo/ci/src/biocontainers-ci.py --commit 695d77f91e7a18dfc74fba7fad951f6a3aa36466

Local file, launch in repo:

    biocontainers-build --file test-ci/0.0.2/Dockerfile
