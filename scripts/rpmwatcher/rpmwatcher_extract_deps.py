#!/bin/env python

"""
MUST BE RUN AS ROOT FROM WITHIN A MINIMAL CENTOS CONTAINER

Fetch package roles (installed by default, build deps, extra packages...) from
koji and the online XCP-ng repository, using a CentOS container and yum commands.

Prerequisites:
- a /data directory that contains the workdir dir updated by sync_repos.sh and rpmwatcher_update.py

Note, in what follows:
- NVR means Name Version Release
- NVRA means Name Version Release Arch
Those are common concepts in the RPM world.
"""

from __future__ import print_function
import argparse
import subprocess
import os
import json
import glob
import tempfile

def check_dir(dirpath):
    if not os.path.isdir(dirpath):
        raise Exception("Directory %s doesn't exist" % dirpath)
    return dirpath

def get_all_runtime_deps(name, install_root, include_self=False):
    """
    name can be either a "short" rpm package name ("n") or the full "nvra"
    """
    output = subprocess.check_output(['yumdownloader', '--quiet', '--installroot=' + install_root,
                                      '--resolve', '--urls', name],
                                     stderr=subprocess.STDOUT)
    installable = "Dependency resolution failed" not in output
    deps = []
    for line in output.splitlines():
        if line.endswith(".rpm"):
            rpm_filename = line.split('/')[-1]
            rpm_nvra = rpm_filename[:-4]
            deps.append(rpm_nvra)
    deps = ([a.split('/')[-1][:-4] for a in output.splitlines() if a.endswith(".rpm")])
    if not include_self:
        deps = deps[1:]
    return installable, deps

def get_latest_rpm_nvra(name, install_root, allow_missing=False):
    try:
        output = subprocess.check_output(['yumdownloader', '--quiet', '--urls', '--installroot=%s' % install_root, name])
    except Exception:
        if allow_missing:
            return None
    rpm_nvra = output.splitlines()[0].split('/')[-1][:-4]
    return rpm_nvra

def get_build_deps(filepath, install_root, download_dir):
    output = subprocess.check_output(['yum-builddep', filepath, '--downloadonly', '--quiet',
                                      '--downloaddir=' + download_dir, '--installroot=' + install_root])
    phase = 0
    direct_deps = []
    deps_deps = []
    wrapped_line = False
    for line in output.splitlines():
        if line.startswith("Installing:"):
            phase = 1
            continue
        elif phase == 1 and line.startswith("Installing for dependencies:"):
            phase = 2
            continue
        elif phase >= 1 and line.strip() == "":
            break

        if phase > 0:
            row = line.strip().split()
            if wrapped_line:
                values += row
            else:
                values = row

            if len(values) < 5:
                # line has been wrapped
                wrapped_line = True
                continue
            else:
                wrapped_line = False

            name = values[0]
            arch = values[1]
            evr = values[2]
            vr = evr if ':' not in evr else evr.split(':')[1]
            rpm_nvra = "%s-%s.%s" % (name, vr, arch)
            if phase == 1:
                direct_deps.append(rpm_nvra)
            else:
                deps_deps.append(rpm_nvra)

    return direct_deps, deps_deps

def main():
    parser = argparse.ArgumentParser(description='Extract package roles for XCP-ng RPMs')
    parser.add_argument('version', help='XCP-ng 2-digit version, e.g. 8.0')
    parser.add_argument('basedir', help='path to the base directory where repos must be present and where '
                                        'we\'ll read data / output results.')
    args = parser.parse_args()

    base_dir = os.path.abspath(check_dir(args.basedir))
    xcp_version = args.version
    xcp_major = xcp_version.split('.')[0]
    xcp_srpm_repo = check_dir(os.path.join(base_dir, 'xcp-ng', xcp_version))
    xcp_rpm_repo = check_dir(os.path.join(base_dir, 'xcp-ng_rpms', xcp_version))
    work_dir = check_dir(os.path.join(base_dir, 'workdir', xcp_version))

    # Read data from workdir
    with open(os.path.join(work_dir, 'xcp-ng_builds_WIP.json')) as f:
        xcp_builds = json.load(f)
    with open(os.path.join(work_dir, 'xcp-ng-rpms-srpms.json')) as f:
        xcp_ng_rpms_srpms = json.load(f)

    # Prepare CentOS container
    for f in glob.glob('/etc/yum.repos.d/*.repo'):
        os.unlink(f)

    repofilepath = '/etc/yum.repos.d/xcp-ng-rpmwatcher.repo'

    with open(repofilepath, 'w') as f:
        for repo in ['base', 'updates', 'candidates', 'testing', 'ci']:
            f.write("""
[xcp-ng-{repo}]
name = XCP-ng {repo} Repository
baseurl = http://mirrors.xcp-ng.org/{xcp_major}/{xcp_version}/{repo}/x86_64/ http://updates.xcp-ng.org/{xcp_major}/{xcp_version}/{repo}/x86_64/
enabled = 1
gpgcheck = 1
repo_gpgcheck = 1
gpgkey = file:///etc/pki/rpm-gpg/RPM-GPG-KEY-xcpng
""".format(repo=repo, xcp_major=xcp_major, xcp_version=xcp_version))

    subprocess.check_call(
        [
            'curl',
            '-sSf',
            'https://xcp-ng.org/RPM-GPG-KEY-xcpng',
            '-o', '/etc/pki/rpm-gpg/RPM-GPG-KEY-xcpng'
        ]
    )

    # Prepare temporary directory that will serve as installroot
    install_root = tempfile.mkdtemp()

    # Install GPG keys inside the install_root
    print("\n*** Installing GPG keys in install_root ***")
    subprocess.check_call(['yumdownloader', '-q', '-y', '--urls', 'xcp-ng-deps', '--installroot=%s' % install_root])

    # Get the list of RPMs that are installed by default (deps of xcp-ng-deps)
    print("\n*** Get list of RPMs installed by default on XCP-ng (deps of xcp-ng-deps) ***")
    installable, rpms_installed_by_default = get_all_runtime_deps('xcp-ng-deps', install_root, include_self=True)
    if not installable:
        raise Exception("What? xcp-ng-deps is not installable?")

    # Add a few base packages to the install root, e.g. kernel to avoid other packages such as kernel-alt
    # to be seen as better fit for the "kernel" provides than standard kernel because of higher version
    # Note: this simple command pulls more than 100 base packages :o
    # This could be either a very good thing or a bad one...
    a_few_base_packages = ['kernel']
    print("\n*** Install base packages in install root (kernel and its deps) ***")
    subprocess.check_call(['yum', 'install', '-q', '-y', ' '.join(a_few_base_packages), '--installroot=%s' % install_root])

    # Remove any yum repo file that may have been installed inside the install root.
    # We don't want them to interfere / take precedence over our /etc/yum.repos.d/xcp-ng-rpmwatcher.repo,
    # which is outside the install root.
    print("\n*** Remove extraneous repo files ***")
    subprocess.check_call(['rm', '-rf', install_root + '/etc/yum.repos.d'])

    # Install GPG keys again, becomes needed again after installing the 100+ packages above
    # We do it now, after actually installing packages in installroot.
    print("\n*** Install GPG keys again in install_root ***")
    subprocess.check_call(['yumdownloader', '-y', '--urls', 'xcp-ng-deps', '--installroot=%s' % install_root])


    # For every SRPM built by ourselves, get its build dependencies
    # We use our local RPMs directory as target directory to avoid downloads
    print("\n*** Get build deps for every SRPM built by XCP-ng ***")
    for srpm_nvr, build_info in xcp_builds.iteritems():
        if build_info['built-by'] == 'xcp-ng':
            build_info['build-deps'] = get_build_deps(os.path.join(xcp_srpm_repo, srpm_nvr + ".src.rpm"),
                                                      install_root,
                                                      xcp_rpm_repo)


    # dict to store data about RPMs, with rpm_nvra as the key
    xcp_rpms = {}

    # For each RPM from our repos, get its runtime dependencies, and add info from xcp_ng_rpms_srpms
    print("\n*** Get runtime deps for all RPMs ***")
    for srpm_nvr, build_info in xcp_builds.iteritems():
        for rpm_nvra in build_info['rpms']:
            installable, deps = get_all_runtime_deps(rpm_nvra, install_root)
            xcp_rpms[rpm_nvra] = {
                'deps': deps,
                'installable':  installable,
                'name': xcp_ng_rpms_srpms[rpm_nvra]['name'],
                'srpm_nvr': xcp_ng_rpms_srpms[rpm_nvra]['srpm_nvr']
            }

    with open(os.path.join(work_dir, 'xcp-ng_rpms_WIP2.json'), 'w') as f:
        f.write(json.dumps(xcp_rpms, sort_keys=True, indent=4))
    with open(os.path.join(work_dir, 'xcp-ng_builds_WIP2.json'), 'w') as f:
        f.write(json.dumps(xcp_builds, sort_keys=True, indent=4))
    with open(os.path.join(work_dir, 'rpms_installed_by_default_nvra.json'), 'w') as f:
        f.write(json.dumps(rpms_installed_by_default, sort_keys=True, indent=4))

    # Get the list of extra installable RPMs, as RPM NVRA.
    print("\n*** Get list of extra_installable packages ***")
    with open(os.path.join(work_dir, 'extra_installable.txt')) as f:
        extra_installable = f.read().splitlines()
    rpms_extra_installable = []
    for name in extra_installable:
        nvra = get_latest_rpm_nvra(name, install_root, allow_missing=True)
        # the package may be missing if it's still in xcp-ng-incoming and already listed
        # there's an xcp-ng-tests test which will verify all extra packages are actually installable
        # so let's not fail here.
        if nvra:
            rpms_extra_installable.append(nvra)
    with open(os.path.join(work_dir, 'extra_installable_nvra.json'), 'w') as f:
        f.write(json.dumps(rpms_extra_installable, sort_keys=True, indent=4))

if __name__ == "__main__":
    main()
