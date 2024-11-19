import logging
import os
import re
import subprocess
from typing import Iterable, Sequence

XCPNG_YUMREPO_TMPL = """
[xcpng-{section}{suffix}]
name=xcpng - {section}{suffix}
baseurl=https://updates.xcp-ng.org/8/{version}/{section}/{rpmarch}/
gpgkey=https://xcp-ng.org/RPM-GPG-KEY-xcpng
failovermethod=priority
skip_if_unavailable=False
"""

# DNF v4 adds an implicit trailing newline to --qf format, but v5 does not
dnf_version = subprocess.check_output(['dnf', '--version'], universal_newlines=True).strip().split('.')
if int(dnf_version[0]) >= 5:
    QFNL = "\n"
else:
    QFNL = ""

def setup_xcpng_yum_repos(*, yum_repo_d: str, sections: Iterable[str],
                          bin_arch: str | None, version: str) -> None:
    with open(os.path.join(yum_repo_d, "xcpng.repo"), "w") as yumrepoconf:
        for section in sections:
            # binaries
            block = XCPNG_YUMREPO_TMPL.format(rpmarch=bin_arch,
                                              section=section,
                                              version=version,
                                              suffix='',
                                              )
            yumrepoconf.write(block)
            # sources
            block = XCPNG_YUMREPO_TMPL.format(rpmarch='Source',
                                              section=section,
                                              version=version,
                                              suffix='-src',
                                              )
            yumrepoconf.write(block)

DNF_BASE_CMD = None
def dnf_setup(*, dnf_conf: str, yum_repo_d: str) -> None:
    global DNF_BASE_CMD
    DNF_BASE_CMD = ['dnf', '--quiet',
                    '--releasever', 'WTF',
                    '--config', dnf_conf,
                    f'--setopt=reposdir={yum_repo_d}',
                    ]

BINRPM_SOURCE_CACHE: dict[str, str] = {}
def rpm_source_package(rpmname: str) -> str:
    return BINRPM_SOURCE_CACHE[rpmname]

def run_repoquery(args: list[str], split: bool = True) -> str | Sequence[str]:
    assert DNF_BASE_CMD is not None
    cmd = DNF_BASE_CMD + ['repoquery'] + args
    logging.debug('$ %s', ' '.join(cmd))
    output = subprocess.check_output(cmd, universal_newlines=True).strip()
    logging.debug('> %s', output)
    return output.split() if split else output

SRPM_BINRPMS_CACHE: dict[str, set[str]] = {}         # binrpm-nevr -> srpm-nevr
def fill_srpm_binrpms_cache() -> None:
    # HACK: get nevr for what dnf outputs as %{sourcerpm}
    logging.debug("get epoch info for SRPMs")
    args = [
        '--disablerepo=*', '--enablerepo=*-src', '*',
        '--qf', '%{name}-%{version}-%{release}.src.rpm,%{name}-%{evr}' + QFNL,
        '--latest-limit=1',
    ]
    SRPM_NEVR_CACHE = {         # sourcerpm -> srpm-nevr
        sourcerpm: nevr
        for sourcerpm, nevr in (line.split(',')
                                for line in run_repoquery(args))
    }

    # binary -> source mapping
    logging.debug("get binary to source mapping")
    global SRPM_BINRPMS_CACHE, BINRPM_SOURCE_CACHE
    args = [
        '--disablerepo=*-src', '*',
        '--qf', '%{name}-%{evr},%{sourcerpm}' + QFNL, # FIXME no epoch in sourcerpm, why does it work?
        '--latest-limit=1',
    ]
    BINRPM_SOURCE_CACHE = {
        # packages without source are not in SRPM_NEVR_CACHE, fallback to sourcerpm
        binrpm: SRPM_NEVR_CACHE.get(sourcerpm, srpm_strip_src_rpm(sourcerpm))
        for binrpm, sourcerpm in (line.split(',')
                                  for line in run_repoquery(args))
    }

    # reverse mapping source -> binaries
    SRPM_BINRPMS_CACHE = {}
    for binrpm, srpm in BINRPM_SOURCE_CACHE.items():
        binrpms = SRPM_BINRPMS_CACHE.get(srpm, set())
        if not binrpms:
            SRPM_BINRPMS_CACHE[srpm] = binrpms
        binrpms.add(binrpm)

def srpm_nevr(rpmname: str) -> str:
    args = [
        '--disablerepo=*', '--enablerepo=*-src',
        '--qf=%{name}-%{evr}' + QFNL, # to get the epoch only when non-zero
        '--latest-limit=1',
        rpmname,
    ]
    ret = run_repoquery(args)
    assert ret, f"Found no SRPM named {rpmname}"
    assert len(ret) == 1        # ensured by --latest-limit=1 ?
    return ret[0]

# dnf insists on spitting .src.rpm names it cannot take as input itself
def srpm_strip_src_rpm(srpmname: str) -> str:
    SUFFIX = ".src.rpm"
    assert srpmname.endswith(SUFFIX), f"{srpmname} does not end in .src.rpm"
    nrv = srpmname[:-len(SUFFIX)]
    return nrv
 
def rpm_requires(rpmname: str) -> Sequence[str]:
    args = [
        '--disablerepo=*-src', # else requires of same-name SRPM are included
        '--qf=%{name}-%{evr}' + QFNL, # to avoid getting the arch and explicit zero epoch
        '--resolve',
        '--requires', rpmname,
    ]
    ret = run_repoquery(args)
    return ret

def srpm_requires(srpmname: str) -> set[str]:
    args = [
        '--qf=%{name}-%{evr}' + QFNL, # to avoid getting the arch
        '--resolve',
        '--requires', f"{srpmname}.src",
    ]
    ret = set(run_repoquery(args))
    return ret

def srpm_binrpms(srpmname: str) -> set[str]:
    ret = SRPM_BINRPMS_CACHE.get(srpmname, None)
    if ret is None: # FIXME should not happen
        logging.error("%r not found in cache", srpmname)
        assert False
        return []
    logging.debug("binrpms for %s: %s", srpmname, ret)
    return ret

UPSTREAM_REGEX = re.compile(r'\.el[0-9]+(_[0-9]+)?(\..*|)$')
RPM_NVR_SPLIT_REGEX = re.compile(r'^(.+)-([^-]+)-([^-]+)$')
def is_pristine_upstream(rpmname:str) -> bool:
    if re.search(UPSTREAM_REGEX, rpmname):
        return True
    return False
