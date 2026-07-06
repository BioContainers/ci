#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
from collections import defaultdict
from git import Repo

from tool import Tool


def find_dockerfiles(root_dir):
    root = Path(root_dir).resolve()
    dockerfiles = []

    for dirpath, _, filenames in os.walk(root):
        current = Path(dirpath)

        for f in filenames:
            if f == "Dockerfile":
                dockerfiles.append(current / f)

    return root, dockerfiles

def get_tool_name(path, root):
    rel = path.relative_to(root)
    return rel.parts[0] if len(rel.parts) > 1 else "unknown"


def get_last_commit_time(repo, file_path):
    """
    Returns last commit timestamp affecting the file.
    """
    commits = list(repo.iter_commits(paths=file_path, max_count=1))
    if not commits:
        return 0
    return commits[0].committed_date


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('biocontainers_repo', type=str, help="Biocontainers reposity")
    parser.add_argument('rse_repo', type=str, help="Research-software-ecosystem repository")
    parser.add_argument('--dry-run', action='store_true', help="Dry run")

    args = parser.parse_args()

    repo_path = Path(args.biocontainers_repo).resolve()
    repo = Repo(repo_path)
    root, dockerfiles = find_dockerfiles(str(repo_path))

    grouped = defaultdict(list)

    for df in dockerfiles:
        tool = get_tool_name(df, root)
        grouped[tool].append(df)

    selected = {}

    for tool, files in grouped.items():
        print(f"\nProcessing tool: {tool}")

        versions = []

        best_file = None
        best_ts = -1

        for f in files:
            versions.append(str(f.relative_to(root)))

            rel = str(f.relative_to(root))
            ts = get_last_commit_time(repo, rel)

            if ts > best_ts:
                best_file = f
                best_ts = ts

        if best_file:
            selected[tool] = best_file
            print(best_file)
            print(f"  SELECTED: {best_file.relative_to(root)} among {versions}")

            tool = Tool(best_file, args.rse_repo, args.dry_run)
            tool.write_yaml()

        else:
            raise Exception("Error on tool " + tool)
