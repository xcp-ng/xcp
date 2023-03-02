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

class JsonSortAndEncode(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, list):
            return sorted(list)
        if isinstance(obj, set):
            return sorted(list(obj))
        return json.JSONEncoder.default(self, obj)

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
    # For each RPM we store mosts roles as well as the related RPMs or SRPMs:
    # - main: RPMs installed by default
    # - extra: RPMs available in the repos and available for installation on dom0
    # - extra_dep: RPMs that are pulled as dependencies for extra RPMs and aren't extra or main
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
    #              the "other_dep" package must also have no roles itself, except other_*
    # - None: no roles

    for rpm_nvra in xcp_rpms:
        xcp_rpms[rpm_nvra]['roles'] = {}

    def add_rpm_role(xcp_rpms, rpm_nvra, role, related_rpm_nvra):
        if role not in xcp_rpms[rpm_nvra]['roles']:
            xcp_rpms[rpm_nvra]['roles'][role] = set()
        xcp_rpms[rpm_nvra]['roles'][role].add(related_rpm_nvra)

    for rpm_nvra in xcp_rpms:
        if rpm_nvra in rpms_installed_by_default:
            # for now the related RPM for the 'main' role is the RPM itself
            # in the future we may want to improve this and detail the dependency chain more
            add_rpm_role(xcp_rpms, rpm_nvra, 'main', rpm_nvra)

        if rpm_nvra in extra_installable_nvra:
            add_rpm_role(xcp_rpms, rpm_nvra, 'extra', rpm_nvra)

    for rpm_nvra in xcp_rpms:
        if rpm_nvra in extra_installable_nvra:
            for dep in xcp_rpms[rpm_nvra]['deps']:
                if not xcp_rpms[dep]['roles']:
                    add_rpm_role(xcp_rpms, dep, 'extra_dep', rpm_nvra)

    def intersect_or_both_empty(list1, list2):
        if not list1 and not list2:
            return True
        return bool(list(set(list1) & set(list2)))

    def srpm_rpms_have_roles(xcp_rpms, xcp_builds, srpm_nvr):
        for rpm_nvra in xcp_builds[srpm_nvr]['rpms']:
            if xcp_rpms[rpm_nvra]['roles']:
                return True
        return False

    def update_builddep_role(xcp_rpms, xcp_builds, roles_from, role_to, direct):
        """
        Identify and flag RPMs that are builddeps or deps of builddeps
        """
        for rpm_nvra in xcp_rpms:
            if intersect_or_both_empty(xcp_rpms[rpm_nvra]['roles'].keys(), roles_from):
                srpm_nvr = xcp_rpms[rpm_nvra]['srpm_nvr']
                # if roles_from is empty and the RPM belongs to a SRPM that already has RPMs with roles,
                # don't retain that RPM. We don't want other_builddep and other_builddep_dep to pop everywhere
                # a SRPM produces an unused RPM among other useful RPMs
                if not roles_from and srpm_rpms_have_roles(xcp_rpms, xcp_builds, srpm_nvr):
                    continue
                if srpm_nvr in xcp_builds and 'build-deps' in xcp_builds[srpm_nvr]:
                    for dep_rpm_nvra in xcp_builds[srpm_nvr]['build-deps'][0 if direct else 1]:
                        add_rpm_role(xcp_rpms, dep_rpm_nvra, role_to, srpm_nvr)

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
                if intersect_or_both_empty(xcp_rpms[rpm_nvra]['roles'].keys(), roles_to_scan):
                    # if roles_to_scan is empty and the RPM belongs to a SRPM that already has RPMs with roles,
                    # don't retain that RPM. We don't want other_indirect_builddep to pop everywhere
                    # a SRPM produces an unused RPM among other useful RPMs
                    if not roles_to_scan and srpm_rpms_have_roles(xcp_rpms, xcp_builds, srpm_nvr):
                        continue
                    # scan the builddeps of its SRPM
                    srpm_nvr = xcp_rpms[rpm_nvra]['srpm_nvr']
                    if srpm_nvr in xcp_builds and 'build-deps' in xcp_builds[srpm_nvr]:
                        for dep_type in [0, 1]:
                            for dep_rpm_nvra in xcp_builds[srpm_nvr]['build-deps'][dep_type]:
                                # since the roles_to_scan are already build deps, the SRPMs to point
                                # as target of the indirect builddep must be those that the build deps
                                # themselves target
                                for role_from in roles_to_scan:
                                    for upper_srpm_nvr in xcp_rpms[rpm_nvra]['roles'].get(role_from, []):
                                        # Interpretation:
                                        # If...
                                        # 1. dep_rpm_nvra   ---(direct or pulled build dep of)--->     srpm_nvr
                                        # 2. srpm_nvr       -------------(produces)-------------->     rpm_nvra
                                        # 3. rpm_nvra       ------("role_from" build dep of)----->     upper_srpm_nvr
                                        # Then...
                                        # dep_rpm_nvra      -------("role_to" build dep of)------>     upper_srpm_nvr
                                        add_rpm_role(xcp_rpms, dep_rpm_nvra, role_to, upper_srpm_nvr)

    update_builddep_role(xcp_rpms, xcp_builds, roles_from=['main'], role_to='main_builddep', direct=True)
    update_builddep_role(xcp_rpms, xcp_builds, roles_from=['main'], role_to='main_builddep_dep', direct=False)
    update_indirect_builddep_role(xcp_rpms, xcp_builds, role_prefix='main', role_to='main_indirect_builddep')
    update_builddep_role(xcp_rpms, xcp_builds, roles_from=['extra', 'extra_dep'], role_to='extra_builddep', direct=True)
    update_builddep_role(xcp_rpms, xcp_builds, roles_from=['extra', 'extra_dep'], role_to='extra_builddep_dep', direct=False)
    update_indirect_builddep_role(xcp_rpms, xcp_builds, role_prefix='extra', role_to='extra_indirect_builddep')

    # Now deps of RPMs that still have no roles
    update_builddep_role(xcp_rpms, xcp_builds, roles_from=[], role_to='other_builddep', direct=True)
    update_builddep_role(xcp_rpms, xcp_builds, roles_from=[], role_to='other_builddep_dep', direct=False)
    update_indirect_builddep_role(xcp_rpms, xcp_builds, role_prefix='other', role_to='other_indirect_builddep')
    for rpm_nvra in xcp_rpms:
        if not xcp_rpms[rpm_nvra]['roles']:
            for dep in xcp_rpms[rpm_nvra]['deps']:
                # other_dep possible only if has no other role than 'other_*'
                if not [x for x in xcp_rpms[dep]['roles'] if not x.startswith('other_')]:
                    add_rpm_role(xcp_rpms, dep, 'other_dep', rpm_nvra)

    # Write RPM data to file
    with open(os.path.join(work_dir, 'xcp-ng_rpms.json'), 'w') as f:
        f.write(json.dumps(xcp_rpms, sort_keys=True, indent=4, cls=JsonSortAndEncode))

    # Update SRPM roles based on RPM roles
    for srpm_nvr, build_info in xcp_builds.iteritems():
        srpm_roles = {}
        for rpm_nvra in build_info['rpms']:
            for rpm_role, role_data in xcp_rpms[rpm_nvra]['roles'].iteritems():
                if rpm_role in ('extra_dep', 'other_dep'):
                    # ignore deps towards RPM of the same SRPM
                    role_data = [x for x in role_data if xcp_rpms[x]['srpm_nvr'] != srpm_nvr]

                if not role_data:
                    continue

                if rpm_role not in srpm_roles:
                    srpm_roles[rpm_role] = set()
                srpm_roles[rpm_role].update(role_data)
        build_info['roles'] = srpm_roles

    # Write SRPM data to file
    with open(os.path.join(work_dir, 'xcp-ng_builds.json'), 'w') as f:
        f.write(json.dumps(xcp_builds, sort_keys=True, indent=4, cls=JsonSortAndEncode))

if __name__ == "__main__":
    main()
