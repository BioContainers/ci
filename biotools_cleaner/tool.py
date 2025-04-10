from collections import defaultdict
import os
import pathlib
import logging
from yaml import safe_load, dump


class Tool:

    def __init__(self, tool_yaml):
        self.yaml_path = tool_yaml
        self.yaml_data = {}

        with open(tool_yaml, 'r') as f:
            self.yaml_data = safe_load(f)

        logging.info('Processing ' + tool_yaml)

    def write_yaml(self, output_dir, dry_run=False, remove_input=False, add_biotool=False):
        to_merge = {}
        if not self.yaml_data.get('softwares'):
            logging.error('"softwares" key not found or empty')
            return False
        if len(self.yaml_data.get('softwares')) > 1:
            biotool = set()
            non_biotool_label = set()
            for key, soft in self.yaml_data['softwares'].items():
                biotool.add(soft['labels'].get('extra.identifiers.biotools', ''))
                if not soft['labels'].get('extra.identifiers.biotools'):
                    non_biotool_label.add(key)
            if len(biotool) > 1:
                if len(biotool) == 2 and '' in biotool:
                    logging.warn("Both empty and non-empty biotool id in {}. Assuming they are the same".format(self.yaml_path))
                    assumed_biotool = [x for x in biotool if x][0]
                    logging.warn("Adding {} to biotool {}".format(non_biotool_label, assumed_biotool))
                    for nbl in non_biotool_label:
                        to_merge[nbl] = assumed_biotool
                else:
                    logging.error("Multiple distinct biotools in {}: stopping".format(self.yaml_path))
                    return False

        data = defaultdict(list)

        for key, values in self.yaml_data['softwares'].items():
            tool_name = key
            biotool_id = values['labels']['extra.identifiers.biotools'] if 'extra.identifiers.biotools' in values['labels'] else key

            if tool_name in to_merge:
                biotool_id = to_merge[tool_name]
                logging.warn("Assuming {} biotool id is {}".format(tool_name, biotool_id))
                if add_biotool:
                    logging.warn("Adding biotool label")
                    values['labels']['extra.identifiers.biotools'] = biotool_id

            data[biotool_id].append({"tool": tool_name, "value": values})

        for key, values in data.items():
            for val in values:
                output_path = os.path.join(output_dir, key, '{}.biocontainers.yaml'.format(val['tool']))

                if len(values) == 1:
                    logging.info("Moving {} to {}".format(self.yaml_path, output_path))

                else:
                    logging.info("Splitting {} to {}".format(self.yaml_path, output_path))

                if not dry_run:
                    pathlib.Path(os.path.join(output_dir, key)).mkdir(parents=True, exist_ok=True)
                    yaml_content = {"softwares": {}}
                    yaml_content['softwares'][val['tool']] = val['value']

                    with open(output_path, 'w') as f:
                        dump(self.yaml_data, f)
        if remove_input:
            logging.info("Removing {}".format(self.yaml_path))
            os.remove(self.yaml_path)
        return True
