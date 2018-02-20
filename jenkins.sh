#!/bin/bash

set -e

# Allow parameterized builds, if data already specified, skip this step
if [ "a$FORCE_CONTAINER" != "a" ]
then
    if [ "a$FORCE_TOOL_VERSION" != "a" ]
    then
        echo "Parameterized build, skip this step and build $CONTAINER $TOOL_VERSION"
        echo "CONTAINER=$FORCE_CONTAINER" > BIOCONTAINERS_ENV
        echo "TOOL_VERSION=$FORCE_TOOL_VERSION" >> BIOCONTAINERS_ENV
        echo "JenkinsBuild: $FORCE_CONTAINER/$FORCE_TOOL_VERSION"
        exit 0
    fi
fi


echo "Check modified files"
git show --name-status $GIT_COMMIT | grep '^[MA]\s'  | sed -e 's/^[MA]\s*//g' | while read i; do echo $i ; done > /tmp/out
cat /tmp/out
rm -f BIOCONTAINERS_ENV
IS_DOCKER_FILE=0
MULTIPLE_CONTAINERS=0
while read p
do
    echo "Check $p"
    curfile=`basename $p`
    arrIN=(${p//\// })
    containerDir=${arrIN[0]}
    if [ "$CONTAINER" == "" ]
    then
        echo "manage container $containerDir"
    else
        if [ "$CONTAINER" != "$containerDir" ]
        then
            echo "commit manage multiple containers, ERROR!"
            exit 1
        fi
    fi
    containerVersion=${arrIN[1]}
    dockerFile=$containerDir/$containerVersion/Dockerfile
    echo "Check docker file exists: $dockerFile"
    if [ -e $dockerFile ];
    then
        echo "ok, found a Dockerfile"
        IS_DOCKER_FILE=1
    fi
    software=`sed -n 's/.*\ssoftware="\(.*\)"\s*\\\*/\1/p' $p | tr -d '[:space:]'`
    container=`sed -n 's/.*\scontainer="\(.*\)"\s*\\\*/\1/p' $p | tr -d '[:space:]'`
    if [ "$container" == "" ]
    then
        echo "no container name, use software name"
    else
        software=$container
    fi
    echo "DOCKERFILE=$p" > BIOCONTAINERS_ENV
    echo "LABEL_CONTAINER=$software" >> BIOCONTAINERS_ENV
    echo "CONTAINER=$containerDir" >> BIOCONTAINERS_ENV
    echo "TOOL_VERSION=$containerVersion" >> BIOCONTAINERS_ENV
done < /tmp/out

echo "JenkinsBuild: $FORCE_CONTAINER/$FORCE_TOOL_VERSION"

if [ $IS_DOCKER_FILE == 0 ]
then
    echo "No Dockerfile found"
    exit 1
fi

rm -f /tmp/out
cat BIOCONTAINERS_ENV
