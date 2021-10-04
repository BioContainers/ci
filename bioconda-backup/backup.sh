#!/bin/bash

#WORKDIR=/home/ubuntu/conda-backup
WORKDIR=$1

date

if [ -e $WORKDIR/LOCK ]; then
    echo "in progress, skipping"
    exit 1
fi

touch $WORKDIR/LOCK

cd $WORKDIR

. ./venv/bin/activate
. ./env.sh

LAST_SHA=
if [ ! -e bioconda-recipes ]; then
    echo "new clone"
    git clone https://github.com/bioconda/bioconda-recipes.git
    cd bioconda-recipes
else
    cd bioconda-recipes
    if [ -z "$FORCE" ]; then
        LAST_SHA=`git show HEAD | sed -n 1p | cut -d " " -f 2`
        echo "Last sha: $LAST_SHA"
    else
        echo "Force scan of all repo"
    fi
fi
git pull origin master

if [ "a$LAST_SHA" == "a" ]; then
    find . -name "meta.yaml" > /tmp/recipes.txt
else
    NEW_SHA=`git show HEAD | sed -n 1p | cut -d " " -f 2`
    echo "New sha: $NEW_SHA"
    git diff --name-only $LAST_SHA $NEW_SHA | grep "meta.yaml" > /tmp/recipes.txt
fi

while read p; do
    echo "backup $p"
    python $WORKDIR/backup.py $p
done </tmp/recipes.txt

rm /tmp/recipes.txt

rm $WORKDIR/LOCK
echo "backup done"
