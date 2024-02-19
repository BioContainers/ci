#!/usr/bin/env python

import argparse

from .tool import Tool


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=str, help="Path to yaml file")
    parser.add_argument('output', type=str, help="Output dir (ie, Research-software-ecosystem repository)")
    parser.add_argument('--dry-run', action='store_true', help="Dry run")
    parser.add_argument('--cleanup', action='store_true', help="Remove old layout files from repository")
    args = parser.parse_args()

    tool = Tool(args.input)
    tool.write_yaml(args.output, dry_run=args.dry_run, remove_input=args.cleanup)
