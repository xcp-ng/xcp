#!/usr/bin/env python3

import sys

from koji_utils.koji_build import main

print("\033[33mwarning: koji_build.py as moved to koji_utils/koji_build.py. "
      "Please update your configuration to use that file.\033[0m", file=sys.stderr)
main()
