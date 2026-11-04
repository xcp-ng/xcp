#!/usr/bin/env python3
import argparse
import json
import logging
import subprocess
import sys


def setup_logger():
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=logging.INFO
    )

def run_command(command):
    logging.info(f"Executing: {' '.join(command)}")
    try:
        result = subprocess.run(command, check=True, text=True, capture_output=True)
        logging.info(result.stdout.strip())
        return result.stdout
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {' '.join(command)}", exc_info=True)
        logging.error(e.stderr.strip())
        sys.exit(1)

def parent_arches(parent):
    """The arches of the parent tag, which user tags must build for (x86_64 for 8.x, x86_64_v2 for 9.0)."""
    tag = json.loads(run_command(["koji", "call", "--json-output", "getTag", parent]))
    if not tag:
        logging.error(f"No such tag: {parent}")
        sys.exit(1)
    if not tag["arches"]:
        logging.error(f"Parent tag {parent} has no arches")
        sys.exit(1)
    return tag["arches"]

def main():
    parser = argparse.ArgumentParser(description="Create a user tag and the corresponding target in Koji.")
    parser.add_argument("PARENT", help="Parent tag")
    parser.add_argument("TARGET", help="Tag and target name (the same name is used for the tag and the target)")
    args = parser.parse_args()

    setup_logger()

    # --perm=build: without a permission, any Koji account could tag builds into the user tag
    run_command(["koji", "add-tag", args.TARGET, f"--parent={args.PARENT}",
                 f"--arches={parent_arches(args.PARENT)}", "--perm=build"])
    run_command(["koji", "add-target", args.TARGET, args.TARGET, args.TARGET])

if __name__ == "__main__":
    main()

