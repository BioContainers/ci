import os
import pathlib
import logging
from yaml import safe_load, dump


class Tool:

    def __init__(self, tool_yaml):
        self.yaml_path = tool_yaml
        self.yaml_data = {}

        with open(tool_yaml, 'r') as f:
            self.data = safe_load(f)

        logging.info('Processing ' + tool_yaml)

    def write_yaml(self, output_dir, dry_run=False, remove_input=False):
        if not self.yaml_data.get('software'):
            logging.error('"software" key not found or empty')
        if len(self.yaml_data.get('software')) > 1:
            logging.error('More than one software in yaml file: this should not happen')
        tool_name = list(self.yaml_data['software'].keys())[0]

        output_path = os.path.join(output_dir, tool_name, '{}.biocontainers.yaml'.format(tool_name))

        logging.info("Moving {} to {}".format(self.yaml_path, output_path))

        if not dry_run:
            pathlib.Path(os.path.join(output_dir, tool_name)).mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                dump(self.yaml_data, f)
            if remove_input:
                logging.info("Removing {}".format(self.yaml_path))
                os.remove(self.yaml_path)
