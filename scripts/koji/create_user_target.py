#!/usr/bin/env python3
import argparse
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
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {' '.join(command)}", exc_info=True)
        logging.error(e.stderr.strip())
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Create a user tag and the corresponding target in Koji.")
    parser.add_argument("PARENT", help="Parent tag")
    parser.add_argument("TARGET", help="Tag and target name (the same name is used for the tag and the target)")
    args = parser.parse_args()

    setup_logger()

    run_command(["koji", "add-tag", args.TARGET, f"--parent={args.PARENT}", "--arches=x86_64"])
    run_command(["koji", "add-target", args.TARGET, args.TARGET, args.TARGET])

if __name__ == "__main__":
    main()

