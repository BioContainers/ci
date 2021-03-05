#!/bin/bash

# $1 path to container directory
# $2 optional branch to use in bio-tools/content repo

if [ "a$1" == "a" ]; then
  echo "missing containers directorty"
  exit 1
fi

SEARCHDIR=$(realpath $1)
count=0

rm -rf /tmp/biotools-content
for f in $(find $SEARCHDIR -type f -name Dockerfile); do
  ((count=count+1))
  echo "Dockerfile: $f"
  GIT_PYTHON_TRACE=full python ./biotools-patch.py $f $2
  if [ $count -lt 2 ]; then
      echo "sleep, waiting for first PR to be created" 
      sleep 10
  fi
done

