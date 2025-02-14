import logging
import os
import re
import subprocess

XCPNG_YUMREPO_TMPL = """
[xcpng-{section}{suffix}]
name=xcpng - {section}{suffix}
baseurl=https://updates.xcp-ng.org/8/{version}/{section}/{rpmarch}/
gpgkey=https://xcp-ng.org/RPM-GPG-KEY-xcpng
failovermethod=priority
skip_if_unavailable=False
"""

XCPNG_YUMREPO_USER_TMPL = """
[xcpng-{section}{suffix}]
name=xcpng - {section}{suffix}
baseurl=https://koji.xcp-ng.org/repos/user/8/{version}/{section}/{rpmarch}/
gpgkey=https://xcp-ng.org/RPM-GPG-KEY-xcpng
failovermethod=priority
skip_if_unavailable=False
"""

def setup_xcpng_yum_repos(*, yum_repo_d, sections, bin_arch, version):
    with open(os.path.join(yum_repo_d, "xcpng.repo"), "w") as yumrepoconf:
        for section in sections:
            # HACK: use USER_TMPL if section ends with a number
            if section[-1].isdigit():
                tmpl = XCPNG_YUMREPO_USER_TMPL
            else:
                tmpl = XCPNG_YUMREPO_TMPL

            # binaries
            if bin_arch:
                block = tmpl.format(rpmarch=bin_arch,
                                    section=section,
                                    version=version,
                                    suffix='',
                                    )
                yumrepoconf.write(block)
            # sources
            block = tmpl.format(rpmarch='Source',
                                section=section,
                                version=version,
                                suffix='-src',
                                )
            yumrepoconf.write(block)


XS8_YUMREPO_TMPL = """
[xs8-{section}]
name=XS8 - {section}
baseurl=http://10.1.0.94/repos/XS8/{section}/xs8p-{section}/
failovermethod=priority
skip_if_unavailable=False

[xs8-{section}-src]
name=XS8 - {section} source
baseurl=http://10.1.0.94/repos/XS8/{section}/xs8p-{section}-source/
failovermethod=priority
skip_if_unavailable=False
"""

def setup_xs8_yum_repos(*, yum_repo_d, sections):
    with open(os.path.join(yum_repo_d, "xs8.repo"), "w") as yumrepoconf:
        for section in sections:
            block = XS8_YUMREPO_TMPL.format(section=section)
            yumrepoconf.write(block)

DNF_BASE_CMD = None
def dnf_setup(*, dnf_conf, yum_repo_d):
    global DNF_BASE_CMD
    DNF_BASE_CMD = ['dnf', '--quiet',
                    '--releasever', 'WTF',
                    '--config', dnf_conf,
                    f'--setopt=reposdir={yum_repo_d}',
                    ]

BINRPM_SOURCE_CACHE = {}
def rpm_source_package(rpmname):
    return BINRPM_SOURCE_CACHE[rpmname]

def run_repoquery(args):
    cmd = DNF_BASE_CMD + ['repoquery'] + args
    logging.debug('$ %s', ' '.join(cmd))
    ret = subprocess.check_output(cmd, universal_newlines=True).strip().split()
    logging.debug('> %s', '\n'.join(ret))
    return ret

SRPM_BINRPMS_CACHE = {}         # binrpm-nevr -> srpm-nevr
def fill_srpm_binrpms_cache():
    # HACK: get nevr for what dnf outputs as %{sourcerpm}
    logging.debug("get epoch info for SRPMs")
    args = [
        '--disablerepo=*', '--enablerepo=*-src', '*',
        '--qf', '%{name}-%{version}-%{release}.src.rpm,%{name}-%{evr}',
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
        '--qf', '%{name}-%{evr},%{sourcerpm}', # FIXME no epoch in sourcerpm, why does it work?
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

def srpm_nevr(rpmname):
    args = [
        '--disablerepo=*', '--enablerepo=*-src',
        '--qf=%{name}-%{evr}', # to get the epoch only when non-zero
        '--latest-limit=1',
        rpmname,
    ]
    ret = run_repoquery(args)
    assert ret, f"Found no SRPM named {rpmname}"
    assert len(ret) == 1        # ensured by --latest-limit=1 ?
    return ret[0]

# dnf insists on spitting .src.rpm names it cannot take as input itself
def srpm_strip_src_rpm(srpmname):
    SUFFIX = ".src.rpm"
    assert srpmname.endswith(SUFFIX), f"{srpmname} does not end in .src.rpm"
    nrv = srpmname[:-len(SUFFIX)]
    return nrv
 
def rpm_requires(rpmname):
    args = [
        '--disablerepo=*-src', # else requires of same-name SRPM are included
        '--qf=%{name}-%{evr}', # to avoid getting the arch and explicit zero epoch
        '--resolve',
        '--requires', rpmname,
    ]
    ret = run_repoquery(args)
    return ret

def srpm_requires(srpmname):
    args = [
        '--qf=%{name}-%{evr}', # to avoid getting the arch
        '--resolve',
        '--requires', f"{srpmname}.src",
    ]
    ret = set(run_repoquery(args))
    return ret

def srpm_binrpms(srpmname):
    ret = SRPM_BINRPMS_CACHE.get(srpmname, None)
    if ret is None: # FIXME should not happen
        logging.error("%r not found in cache", srpmname)
        assert False
        return []
    logging.debug("binrpms for %s: %s", srpmname, ret)
    return ret

UPSTREAM_REGEX = re.compile(r'\.el[0-9]+(_[0-9]+)?(\..*|)$')
RPM_NVR_SPLIT_REGEX = re.compile(r'^(.+)-([^-]+)-([^-]+)$')
def is_pristine_upstream(rpmname):
    if re.search(UPSTREAM_REGEX, rpmname):
        return True
    return False

def rpm_parse_nevr(nevr, suffix):
    "Parse into (name, epoch:version, release) stripping suffix from release"
    m = re.match(RPM_NVR_SPLIT_REGEX, nevr)
    assert m, f"{nevr} does not match NEVR pattern"
    n, ev, r = m.groups()
    if ":" in ev:
        e, v = ev.split(":")
    else:
        e, v = "0", ev
    if r.endswith(suffix):
        r = r[:-len(suffix)]
    return (n, e, v, r)

def all_binrpms():
    args = [
        '--disablerepo=*-src',
        '--qf=%{name}-%{evr}', # to avoid getting the arch
        '--latest-limit=1',    # only most recent for each package
        '*',
    ]
    ret = set(run_repoquery(args))
    return ret

def all_srpms():
    args = [
        '--disablerepo=*', '--enablerepo=*-src',
        '--qf=%{name}-%{evr}', # to avoid getting the arch
        '--latest-limit=1',    # only most recent for each package
        '*',
    ]
    ret = set(run_repoquery(args))
    return ret
