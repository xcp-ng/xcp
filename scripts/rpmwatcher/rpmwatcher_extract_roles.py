#!/bin/env python

"""
Continue the work started with rpmwatcher_extract_deps.py

The reason for the split is for debugging purposes:
rpmwatcher_extract_deps.py is solid but long to execute
rpmwatcher_extract_roles.py relies on error-prone algorithms so there's a need to be able
to run it fast to test the changes.

Prerequisites:
- a /data directory that contains the workdir dir updated by rpmwatcher_extract_deps.py

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

def are_siblings(rpm_nvra1, rpm_nvra2, xcp_rpms):
    """ checks whether two RPMs are from the same SRPM """
    return xcp_rpms[rpm_nvra1]['srpm_nvr'] == xcp_rpms[rpm_nvra2]['srpm_nvr']

def main():
    parser = argparse.ArgumentParser(description='Extract package roles for XCP-ng RPMs')
    parser.add_argument('version', help='XCP-ng 2-digit version, e.g. 8.0')
    parser.add_argument('basedir', help='path to the base directory where repos must be present and where '
                                        'we\'ll read data / output results.')
    args = parser.parse_args()

    base_dir = os.path.abspath(check_dir(args.basedir))
    xcp_version = args.version
    work_dir = check_dir(os.path.join(base_dir, 'workdir', xcp_version))

    # Read data from workdir
    with open(os.path.join(work_dir, 'extra_installable_nvra.json')) as f:
        extra_installable_nvra = json.load(f)
    with open(os.path.join(work_dir, 'rpms_installed_by_default_nvra.json')) as f:
        rpms_installed_by_default = json.load(f)
    with open(os.path.join(work_dir, 'xcp-ng_builds_WIP2.json')) as f:
        xcp_builds = json.load(f)
    with open(os.path.join(work_dir, 'xcp-ng_rpms_WIP2.json')) as f:
        xcp_rpms = json.load(f)

    # Update RPM roles
    # For each RPM we store one role, among those in descending priority order:
    # - main: RPMs installed by default
    # - extra: RPMs available in the repos and available for installation on dom0
    # - extra_dep: RPMs that are pulled as dependencies for extra RPMs
    # - main_builddep: direct build dependency for a SRPM that produces main RPMs
    # - main_builddep_dep: dependency of a main_builddep RPM
    # - main_indirect_builddep: builddep of a builddep or of a dep of a builddep, with no limits of depth
    # - extra_builddep: build dependency for a SRPM that produces an extra package or one of its dependencies
    # - extra_builddep_dep: dependency of an extra_builddep RPM
    # - extra_indirect_builddep: builddep of a builddep or of a dep of a builddep, with no limits of depth
    # - other_builddep: direct build dependency for a SRPM that has no RPM with a role
    # - other_builddep_dep: dependency of a other_builddep
    # - other_indirect_builddep: builddep of a builddep or of a dep of a builddep, with no limits of depth
    # - other_dep: dependency for a package that has no roles, not even other_builddep_xxx or other_indirect_builddep
    # - None: no roles

    for rpm_nvra in xcp_rpms:
        xcp_rpms[rpm_nvra]['role'] = None
        xcp_rpms[rpm_nvra]['role_data'] = []

    for rpm_nvra in xcp_rpms:
        if rpm_nvra in rpms_installed_by_default:
            xcp_rpms[rpm_nvra]['role'] = 'main'
        elif rpm_nvra in extra_installable_nvra:
            xcp_rpms[rpm_nvra]['role'] = 'extra'
            for dep in xcp_rpms[rpm_nvra]['deps']:
                if xcp_rpms[dep].get('role') is None and not are_siblings(dep, rpm_nvra, xcp_rpms):
                    xcp_rpms[dep]['role'] = 'extra_dep'
                    xcp_rpms[dep]['role_data'].append(rpm_nvra)

    # Now every rpm_nvra has a 'role' entry, that can be one of the values assigned above, or None

    def update_builddep_role(xcp_rpms, xcp_builds, roles_from, role_to, direct):
        """
        Identify and flag RPMs that are builddeps or deps of builddeps
        """
        for rpm_nvra in xcp_rpms:
            if xcp_rpms[rpm_nvra]['role'] in roles_from:
                srpm_nvr = xcp_rpms[rpm_nvra]['srpm_nvr']
                if srpm_nvr in xcp_builds and 'build-deps' in xcp_builds[srpm_nvr]:
                    for dep_rpm_nvra in xcp_builds[srpm_nvr]['build-deps'][0 if direct else 1]:
                        if xcp_rpms[dep_rpm_nvra]['role'] is None:
                            xcp_rpms[dep_rpm_nvra]['role'] = role_to
                        # store the list of SRPMs the RPM is builddep for
                        if xcp_rpms[dep_rpm_nvra]['role'] == role_to:
                            xcp_rpms[dep_rpm_nvra]['role_data'].append(srpm_nvr)

    def update_indirect_builddep_role(xcp_rpms, xcp_builds, role_prefix, role_to, iterations=10):
        """
        Identify and flag RPMs that are builddeps for builddeps themselves.
        Or deps of builddeps of builddeps.
        Or builddeps of deps of builddeps of deps of builddeps.
        Or builddeps of builddeps of deps of builddeps of builddeps of builddeps
        All of them.
        """
        # Start with builddeps (direct or not) of RPMs whose role starts with role_prefix
        for i in xrange(iterations):
            if i == 0:
                roles_to_scan = [role_prefix + '_builddep', role_prefix + '_builddep_dep']
            else:
                roles_to_scan = [role_to] # after the first iteration
            for rpm_nvra in xcp_rpms:
                if xcp_rpms[rpm_nvra]['role'] in roles_to_scan:
                    # scan the builddeps of its SRPM
                    srpm_nvr = xcp_rpms[rpm_nvra]['srpm_nvr']
                    if srpm_nvr in xcp_builds and 'build-deps' in xcp_builds[srpm_nvr]:
                        for dep_type in [0, 1]:
                            for dep_rpm_nvra in xcp_builds[srpm_nvr]['build-deps'][dep_type]:
                                if xcp_rpms[dep_rpm_nvra]['role'] is None:
                                    xcp_rpms[dep_rpm_nvra]['role'] = role_to
                                # store the list of SRPMs the RPM is builddep for, directly or indirectly
                                if xcp_rpms[dep_rpm_nvra]['role'] == role_to and srpm_nvr not in xcp_rpms[dep_rpm_nvra]['role_data']:
                                    xcp_rpms[dep_rpm_nvra]['role_data'].append(srpm_nvr)

    # The order of execution is important because each step skips RPMs that already have role
    update_builddep_role(xcp_rpms, xcp_builds, roles_from=['main'], role_to='main_builddep', direct=True)
    update_builddep_role(xcp_rpms, xcp_builds, roles_from=['main'], role_to='main_builddep_dep', direct=False)
    update_indirect_builddep_role(xcp_rpms, xcp_builds, role_prefix='main', role_to='main_indirect_builddep')
    update_builddep_role(xcp_rpms, xcp_builds, roles_from=['extra', 'extra_dep'], role_to='extra_builddep', direct=True)
    update_builddep_role(xcp_rpms, xcp_builds, roles_from=['extra', 'extra_dep'], role_to='extra_builddep_dep', direct=False)
    update_indirect_builddep_role(xcp_rpms, xcp_builds, role_prefix='extra', role_to='extra_indirect_builddep')


    # Now deps of RPMs that have no roles
    update_builddep_role(xcp_rpms, xcp_builds, roles_from=[None], role_to='other_builddep', direct=True)
    update_builddep_role(xcp_rpms, xcp_builds, roles_from=[None], role_to='other_builddep_dep', direct=False)
    update_indirect_builddep_role(xcp_rpms, xcp_builds, role_prefix='other', role_to='other_indirect_builddep')
    for rpm_nvra in xcp_rpms:
        if xcp_rpms[rpm_nvra]['role'] is None:
            for dep in xcp_rpms[rpm_nvra]['deps']:
                if xcp_rpms[dep].get('role') is None and not are_siblings(dep, rpm_nvra, xcp_rpms):
                    xcp_rpms[dep]['role'] = 'other_dep'
                    xcp_rpms[dep]['role_data'].append(rpm_nvra)

    # Write RPM data to file
    with open(os.path.join(work_dir, 'xcp-ng_rpms.json'), 'w') as f:
        f.write(json.dumps(xcp_rpms, sort_keys=True, indent=4))

    # Update SRPM roles based on RPM roles
    for srpm_nvr, build_info in xcp_builds.iteritems():
        srpm_roles = {}
        for rpm_nvra in build_info['rpms']:
            rpm_role = xcp_rpms[rpm_nvra]['role']
            if rpm_role is not None:
                if rpm_role.startswith('other_'):
                    # check that no RPM from the SRPM has a role other than 'other_dep' or None
                    a_sibling_has_role = False
                    for sibling_nvra in build_info['rpms']:
                        sibling_role = xcp_rpms[sibling_nvra]['role']
                        if sibling_role is not None and not sibling_role.startswith('other_'):
                            a_sibling_has_role = True
                    if a_sibling_has_role:
                        # skip RPM
                        continue

                if rpm_role not in srpm_roles:
                    srpm_roles[rpm_role] = set()
                if rpm_role in ['main', 'extra']:
                    srpm_roles[rpm_role].add(rpm_nvra)
                else:
                    srpm_roles[rpm_role].update(xcp_rpms[rpm_nvra]['role_data'])
        for role in srpm_roles:
            srpm_roles[role] = list(srpm_roles[role])
        build_info['roles'] = srpm_roles

    # Write SRPM data to file
    with open(os.path.join(work_dir, 'xcp-ng_builds.json'), 'w') as f:
        f.write(json.dumps(xcp_builds, sort_keys=True, indent=4))

if __name__ == "__main__":
    main()
