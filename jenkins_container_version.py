from dockerfile_parse import DockerfileParser
import sys
import os
import logging
import re

import dockerparse_arg_fix

docker_file = None
if len(sys.argv) > 1 and sys.argv[1]:
    docker_file = sys.argv[1]

if not docker_file or not os.path.exists(docker_file):
    logging.error("Could not find Dockerfile "+str(docker_file))
    sys.exit(1)

with open(docker_file, 'r') as content_file:
        content = content_file.read()

#First parsing so we can access the ARG instructions
dfp = DockerfileParser()
dfp.content = content

#Applying our fix to load ARGs until DockerfileParser handles them
dfp = dockerparse_arg_fix.reload_arg_to_env(dfp, content)

#Moved here to avoid repeating this step
labels = dfp.labels

software_version = None
if 'TOOL_VERSION' in os.environ:
    labels['software.version'] = os.environ['TOOL_VERSION']
if 'software.version' not in labels or not labels['software.version']:
    print("Failed to found software.version")
    sys.exit(1)
else:
    software_version = labels['software.version']

version = None
if 'CONTAINER_VERSION' in os.environ:
    labels['version'] = os.environ['CONTAINER_VERSION']
if 'version' not in labels or not labels['version']:
    print("Failed to found version")
    sys.exit(1)
else:
    version = labels['version']

print('TOOL_VERSION=' + software_version + '\n')
print('CONTAINER_VERSION=' + version +'\n')
print('CONTAINER_TAG_PREFIX=' + software_version + '_cv' + version + '\n')

with open('/biocontainers/PhenoMeNal_Versions.txt', 'w') as version_file:
        version_file.write('TOOL_VERSION="' + software_version + '"\n')
        version_file.write('CONTAINER_VERSION="' + version +'"\n')
        version_file.write('CONTAINER_TAG_PREFIX=v' + software_version + '_cv' + version + '\n')
