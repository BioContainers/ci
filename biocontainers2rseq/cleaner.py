#!/usr/bin/env python

import argparse
import logging

from tool import Tool

logging.basicConfig()
logging.root.setLevel(logging.INFO)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=str, help="Path to a Dockerfile")
    parser.add_argument('output', type=str, help="Output dir (ie, Research-software-ecosystem repository)")
    parser.add_argument('--dry-run', action='store_true', help="Dry run")
    args = parser.parse_args()

    tool = Tool(args.input, args.output, args.dry_run)
    tool.write_yaml()
