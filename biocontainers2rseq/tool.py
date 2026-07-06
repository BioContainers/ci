import os
import re

from copy import deepcopy

from yaml import dump
try:
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Dumper

class Tool:

    def parse_label_string(self, label_body):
        """
        Parse Docker LABEL string into key-value pairs.
        Handles:
          key=value
          key="value"
          key='value'
        """
        kv = {}

        # Split while preserving quoted values
        tokens = re.findall(r'(\S+=".*?"|\S+=\'.*?\'|\S+)', label_body)

        for token in tokens:
            if "=" not in token:
                continue

            key, value = token.split("=", 1)
            key = key.strip()
            value = value.strip()

            # Remove surrounding quotes
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]

            kv[key] = value

        return kv

    def parse_Dockerfile(self, dockerfile_path):
        LABEL_RE = re.compile(r'LABEL\s+(.*)', re.IGNORECASE)
        labels = {}

        with open(dockerfile_path, 'r') as f:
            lines = f.readlines()

        buffer = ""
        collecting = False

        for line in lines:
            line = line.strip()

            # handle continuation lines
            if line.endswith("\\"):
                buffer += " " + line[:-1].strip()
                collecting = True
                continue
            else:
                if collecting:
                    buffer += " " + line
                    full_line = buffer.strip()
                    buffer = ""
                    collecting = False
                else:
                    full_line = line

            match = LABEL_RE.match(full_line)
            if match:
                parsed = self.parse_label_string(match.group(1))
                labels.update(parsed)

        if 'software' not in labels:
            raise Exception("Missing 'software' label in Dockerfile")
        if 'software.version' not in labels:
            raise Exception("Missing 'software.version' label in Dockerfile")
        self.labels = labels

    def __init__(self, dockerfile, output_folder, dry_run=False):
        self.dockerfile = dockerfile
        self.output_folder = os.path.abspath(output_folder)
        self.dry_run = dry_run

        self.parse_Dockerfile(dockerfile)

    def write_yaml(self):
        name = self.labels['software']
        version = self.labels['software.version']

        biotools = None
        if self.labels.get('extra.identifiers.biotools'):
            biotools = self.labels.get('extra.identifiers.biotools').strip()

        all_tmpdir = os.path.join(self.output_folder, "import/biocontainers/")

        files_to_write = [all_tmpdir + '{}.biocontainers.yaml'.format(name)]

        if not os.path.exists(all_tmpdir):
            os.makedirs(all_tmpdir)

        if biotools is not None:
            biotool_tmpdir = self.output_folder + '/data/{}/'.format(biotools)
            if not os.path.exists(biotool_tmpdir):
                os.makedirs(biotool_tmpdir)
            files_to_write.append(biotool_tmpdir + '{}.biocontainers.yaml'.format(name))

        data = {
                'software': name,
                "url": "biocontainers/" + name + ":" + version,
                "version": version,
                "type": "Container file",
                'labels': deepcopy(self.labels)
        }

        softwares = {'softwares': {}}
        softwares["softwares"][name] = data

        for file_path in files_to_write:
                print("Will write content to " + file_path)
                if self.dry_run:
                    continue
                with open(file_path, 'w') as fp:
                    dump(softwares, fp, Dumper=Dumper)
