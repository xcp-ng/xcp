#!/usr/bin/env python3

import argparse
import tomllib
from pathlib import Path

parser = argparse.ArgumentParser(description="Convert the dependencies from pyproject.toml in requirements.txt files")
args = parser.parse_args()

PROJECT_DIR = Path(__file__).parent.parent
HEADER = "# generated with update_requirements.py, do not edit manually"

with open(f'{PROJECT_DIR}/pyproject.toml', 'rb') as f:
    pyproject = tomllib.load(f)


main_deps = pyproject['project']['dependencies']
with open(f'{PROJECT_DIR}/requirements/base.txt', 'w') as f:
    print(HEADER, file=f)
    for dep in main_deps:
        print(dep, file=f)

dev_deps = pyproject['dependency-groups']['dev']
with open(f'{PROJECT_DIR}/requirements/dev.txt', 'w') as f:
    print(HEADER, file=f)
    for dep in dev_deps:
        print(dep, file=f)
    print('-r base.txt', file=f)
