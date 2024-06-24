#!/usr/bin/env python

import argparse
import pathlib
import logging

from tool import Tool

logging.basicConfig()
# logging.root.setLevel(logging.INFO)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('rse_repo', type=str, help="Research-software-ecosystem data folder")
    parser.add_argument('--dry-run', action='store_true', help="Dry run")
    parser.add_argument('--cleanup', action='store_true', help="Remove old layout files from repository")
    parser.add_argument('--add-label', action='store_true', help="Make sure all tools in a specific file have the same biotool label")

    args = parser.parse_args()

    for path in pathlib.Path(args.rse_repo).rglob("biocontainers.yaml"):
        tool = Tool(str(path.resolve()))
        tool.write_yaml(args.rse_repo, dry_run=args.dry_run, remove_input=args.cleanup, add_biotool=args.add_label)
