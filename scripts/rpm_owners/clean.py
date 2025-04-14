#!/usr/bin/env python3

import json
import sys

import polars as pl

df = pl.read_csv("rpm.csv")
df = df.rename({
    'main role': 'role',
    'Maintained by': 'maintainer',
    'SRPM name': 'package',
    'built by': 'built_by',
    'added by': 'added_by',
    'import reason': 'import_reason',
})
# we don't want to deal with the 'other' packages here
df = df.filter(pl.col('role') != 'None').filter(~pl.col('role').str.starts_with('other'))

# fix some non uniform tags in the dataset
df = df.with_columns(pl.col('maintainer').str.replace('OS Platform.+', 'OS Platform'))

# check all the packages have a maintainer
package_no_maintainers = df.filter(
    ~pl.col('maintainer').is_in(['Hypervisor & Kernel', 'OS Platform', 'Storage', 'XAPI & Network'])
)['package'].to_list()
if package_no_maintainers:
    print(f'error: packages without maintainers: {" ".join(package_no_maintainers)}', file=sys.stderr)
    # exit(0)

packages = dict((r['package'], r) for r in df.rows(named=True))
with open('packages.json', 'w') as f:
    json.dump(packages, f, indent=4, sort_keys=True)
