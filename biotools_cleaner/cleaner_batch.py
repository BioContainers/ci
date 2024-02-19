#!/usr/bin/env python

import argparse
import pathlib

from .tool import Tool

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('rse_repo', type=str, help="Research-software-ecosystem data folder")
    parser.add_argument('--dry-run', action='store_true', help="Dry run")
    parser.add_argument('--cleanup', action='store_true', help="Remove old layout files from repository")
    args = parser.parse_args()

    for path in pathlib.Path(args.rse_repo).rglob("biocontainers.yaml"):
        tool = Tool(path.name)
        tool.write_yaml(args.rse_repo, dry_run=args.dry_run, remove_input=args.cleanup)
