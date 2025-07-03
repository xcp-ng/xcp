#!/usr/bin/env python3

import argparse
import csv
import logging
import tempfile
from collections import namedtuple
from typing import Iterable, Iterator

import rpm  # type: ignore

import repoquery

ARCH = "x86_64"
XCP_VERSION = "8.3"

class EVR:
    def __init__(self, e: str, v: str, r: str):
        self._evr = (e, v, r)

    def __eq__(self, other):
        if isinstance(other, EVR):
            return self._evr == other._evr
        else:
            return self._evr == other

    def __gt__(self, other):
        if isinstance(other, EVR):
            return rpm.labelCompare(self._evr, other._evr) > 0  # type: ignore
        else:
            return self._evr > other

    def __lt__(self, other):
        return other > self

    def __str__(self):
        if self._evr[0] != '0':
            return f'{self._evr[0]}:{self._evr[1]}.{self._evr[2]}'
        else:
            return f'{self._evr[1]}.{self._evr[2]}'

# Filters an iterator of (n, e, v, r) for newest evr of each `n`.
# Older versions are allowed to appear before the newer ones.
def filter_best_evr(nevrs: Iterable[tuple[str, str, str, str]]) -> Iterator[tuple[str, str, str, str]]:
    best: dict[str, tuple[str, str, str]] = {}
    for (n, e, v, r) in nevrs:
        if n not in best or rpm.labelCompare(best[n], (e, v, r)) < 0:  # type: ignore
            best[n] = (e, v, r)
            yield (n, e, v, r)
        # else (e, v, r) is older than a previously-seen version, drop

def collect_data_xcpng() -> dict[str, EVR]:
    with (tempfile.NamedTemporaryFile() as dnfconf,
          tempfile.TemporaryDirectory() as yumrepod):
        repoquery.setup_xcpng_yum_repos(yum_repo_d=yumrepod,
                                        sections=['base', 'updates'],
                                        bin_arch=None,
                                        version=XCP_VERSION)
        repoquery.dnf_setup(dnf_conf=dnfconf.name, yum_repo_d=yumrepod)

        xcp_nevr = {
            n: EVR(e, v, r)
            for (n, e, v, r)
            in filter_best_evr(repoquery.rpm_parse_nevr(nevr, f".xcpng{XCP_VERSION}")
                               for nevr in repoquery.all_srpms())}

    return xcp_nevr

def collect_data_xs8():
    with (tempfile.NamedTemporaryFile() as dnfconf,
          tempfile.TemporaryDirectory() as yumrepod):

        repoquery.setup_xs8_yum_repos(yum_repo_d=yumrepod,
                                      sections=['base', 'normal'],
                                      )
        repoquery.dnf_setup(dnf_conf=dnfconf.name, yum_repo_d=yumrepod)
        logging.debug("fill cache with XS info")
        repoquery.fill_srpm_binrpms_cache()

        logging.debug("get all XS SRPMs")
        xs8_srpms = {nevr for nevr in repoquery.all_srpms()}
        xs8_rpms_sources = {nevr for nevr in repoquery.SRPM_BINRPMS_CACHE}

        xs8_srpms_set = {n: EVR(e, v, r)
                         for (n, e, v, r)
                         in filter_best_evr(repoquery.rpm_parse_nevr(nevr, ".xs8")
                                            for nevr in xs8_srpms)}
        xs8_rpms_sources_set = {n: EVR(e, v, r)
                                for (n, e, v, r)
                                in filter_best_evr(repoquery.rpm_parse_nevr(nevr, ".xs8")
                                                   for nevr in xs8_rpms_sources)}

    return (xs8_srpms_set, xs8_rpms_sources_set)

def read_package_status_metadata():
    with open('package_status.csv', newline='') as csvfile:
        csvreader = csv.reader(csvfile, delimiter=';', quotechar='|')
        headers = next(csvreader)
        assert headers == ["SRPM_name", "status", "comment"], f"unexpected headers {headers!r}"
        PackageStatus = namedtuple("PackageStatus", headers[1:]) # type: ignore[misc]
        return {row[0]: PackageStatus(*row[1:])
                for row in csvreader}

parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose', action='count', default=0)
args = parser.parse_args()

loglevel = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}.get(args.verbose, logging.DEBUG)
logging.basicConfig(format='[%(levelname)s] %(message)s', level=loglevel)

PACKAGE_STATUS = read_package_status_metadata()

xcp_set = collect_data_xcpng()
(xs8_srpms_set, xs8_rpms_sources_set) = collect_data_xs8()

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
    # if xcp_evr is not None and xcp_evr < xs8_evr:
    if xcp_evr is None:
        if not repoquery.is_pristine_upstream(str(xs8_evr)):
            print(f'{n} {xcp_evr} -> {xs8_evr}')
    elif xcp_evr < xs8_evr:
        print(f'{n} {xcp_evr} -> {xs8_evr}')
