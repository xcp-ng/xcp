#!/usr/bin/env python3

import csv
import gzip
import logging
import tempfile
import xml.etree.ElementTree as ET
from collections import namedtuple
from typing import Iterable, Iterator
from urllib.request import urlopen

import rpm  # type: ignore

import repoquery

ARCH = "x86_64"
XCP_VERSION = "8.3"

class EVR:
    def __init__(self, e: str, v: str, r: str):
        self._evr = ('0' if e in [None, 'None'] else e, v, r)

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
            return f'{self._evr[0]}:{self._evr[1]}-{self._evr[2]}'
        else:
            return f'{self._evr[1]}-{self._evr[2]}'

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

def get_xs8_rpm_updates():
    NS = {'repo': 'http://linux.duke.edu/metadata/repo'}
    BASE_URL = 'http://repos/repos/XS8/normal/xs8p-normal'

    # read the update info path from repomd.xml
    with urlopen(f'{BASE_URL}/repodata/repomd.xml') as f:
        repomd = f.read()
    data = ET.fromstring(repomd).find("repo:data[@type='updateinfo']", NS)
    assert data is not None
    location = data.find('repo:location', NS)
    assert location is not None
    path = location.attrib['href']

    # read the update info file
    res = {}
    with urlopen(f'{BASE_URL}/{path}') as cf, gzip.open(cf, 'rb') as f:
        updateinfo = f.read()
    updates = ET.fromstring(updateinfo).findall('update')
    for update in updates:
        update_id = update.find('id')
        assert update_id is not None
        update_id = update_id.text
        pkglist = update.find('pkglist')
        assert pkglist is not None
        collection = pkglist.find('collection')
        assert collection is not None
        packages = collection.findall('package')
        for package in packages:
            evr = EVR(package.attrib['epoch'], package.attrib['version'], package.attrib['release'])
            rpm = f'{package.attrib["name"]}-{evr}'
            srpm = repoquery.rpm_source_package(rpm, default=rpm)
            res[srpm] = update_id
    return res
