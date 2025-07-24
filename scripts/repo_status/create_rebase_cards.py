#!/usr/bin/env python3

import argparse
import logging

# from icecream import ic
from tabulate import tabulate

import repoquery
from lib import collect_data_xcpng, collect_data_xs8, get_xs8_rpm_updates, read_package_status_metadata

parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose', action='count', default=0)
args = parser.parse_args()

loglevel = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}.get(args.verbose, logging.DEBUG)
logging.basicConfig(format='[%(levelname)s] %(message)s', level=loglevel)

PACKAGE_STATUS = read_package_status_metadata()

xcp_set = collect_data_xcpng()
(xs8_srpms_set, xs8_rpms_sources_set) = collect_data_xs8()
srpm_updates = get_xs8_rpm_updates()

res = []
for n in sorted(set(xs8_srpms_set.keys()) | xs8_rpms_sources_set.keys()):
    if n in PACKAGE_STATUS and PACKAGE_STATUS[n].status == 'ignored':
        logging.debug(f"ignoring {n}")
        continue
    xs8_srpms_evr = xs8_srpms_set.get(n)
    xs8_rpms_sources_evr = xs8_rpms_sources_set.get(n)
    if xs8_srpms_evr is not None and xs8_rpms_sources_evr is not None:
        xs8_evr = max(xs8_srpms_evr, xs8_rpms_sources_evr)
    else:
        xs8_evr = xs8_srpms_evr or xs8_rpms_sources_evr
    xcp_evr = xcp_set.get(n)
    xs8_update = srpm_updates.get(f'{n}-{xs8_evr}.xs8', '?')
    # if xcp_evr is not None and xcp_evr < xs8_evr:
    if xcp_evr is None:
        if not repoquery.is_pristine_upstream(str(xs8_evr)):
            res.append((xs8_update, n, xcp_evr, xs8_evr))
    elif xcp_evr < xs8_evr:
        res.append((xs8_update, n, xcp_evr, xs8_evr))
res.sort()
print(tabulate(res, headers=['xs8 update', 'SRPM', 'XCP-ng version', 'XS8 version']))
