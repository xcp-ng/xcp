#!/usr/bin/env python3
from argparse import ArgumentParser
import logging
import shutil
import subprocess
import sys
import os.path
import time
import xml.etree.ElementTree as ET

### README
#
# This script allows users to fix xapi databases with incongruent snapshot
# metadata.
#
# The script temporarily disables HA and stops xapi to apply the changes to the
# database. This means that the pool is not running operations like handling
# backups, migrating, starting or stopping VMs, and HA is disabled during the
# operation.
#
# The script needs to be run on the master host of the affected pool.
#
# In unlikely case the script corrupts the database, the script provides an
# option to restore the database from the backup.

xapi_db        = '/var/lib/xcp/state.db'
xapi_db_backup = '/var/lib/xcp/state.db.snapshot_of.backup'
xapi_db_fixed  = '/var/lib/xcp/state.db.snapshot_of.fixed'

bypass_checks = False
MIN_MAJOR = 8
MIN_MINOR = 3

def service_status(name):
    cmd = ['systemctl', 'is-active', name]
    r = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    return r.stdout.strip()

def is_service_active(name):
    return service_status(name) == b'active'

def is_service_inactive(name):
    return service_status(name) in [b'inactive', b'failed']

def poke_service(name, cmd, check, timeout=15):
    end = time.time() + timeout
    subprocess.run(['systemctl', cmd, name], check=True)
    while time.time() < end:
        if check(name):
            return
        time.sleep(2)
    raise TimeoutError(f'Could not {cmd} {name} service in time.')

def start_xapi(ha_enabled):
    logging.info('Starting up xapi...')
    try:
        poke_service('xapi', 'start', is_service_active)
    except TimeoutError:
        logging.error('Starting xapi timed out. Please make sure it\'s working by running `systemctl status xapi`')
        if ha_enabled:
            logging.error('HA was disabled and needs to be enabled back again manually. Please re-enable it by running `xe pool-ha-enable`')
        sys.exit(1)

def stop_xapi():
    logging.info('Shutting down xapi...')
    try:
        poke_service('xapi', 'stop', is_service_inactive, 60)
    except TimeoutError:
        logging.error('Timed out, aborting')
        sys.exit(1)

def start_ha():
    logging.info('Enable HA...')
    end = time.time() + 30
    time.sleep(2)
    while time.time() < end:
        try:
            subprocess.run(['xe', 'pool-ha-enable'], check=True)
            logging.info('HA enabled...')
            return
        except subprocess.CalledProcessError:
            time.sleep(2)
            pass
    raise TimeoutError('Could not re-enable HA in time.')

def query_and_stop_ha():
    logging.info('Check HA...')
    r = subprocess.run(
        [ 'xe', 'pool-list', '--minimal' ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    pool_uuid = r.stdout.strip().split()[-1].decode('utf-8')
    r = subprocess.run(
        [ 'xe', 'pool-param-get', 'param-name=ha-enabled', 'uuid=' + pool_uuid ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    ha_enabled = r.stdout.strip() == b'true'
    if ha_enabled:
        logging.info('Disable HA...')
        subprocess.run(['xe', 'pool-ha-disable'], check=True)
    return ha_enabled

def fix_record(cls_name, record):
    nullref = 'OpaqueRef:NULL'
    snapshot_of = record.get('snapshot_of')
    if record.get('is_a_snapshot') == 'false' and snapshot_of != nullref:
        name = record.get('uuid')
        logging.info(f'The {cls_name} {name} has {snapshot_of} as its "snapshot_of" value, changing to null.')
        record.set('snapshot_of', 'OpaqueRef:NULL')
        ref = record.get('ref')
    elif cls_name == 'VDI' and record.get('is-a-snapshot') == 'true' and snapshot_of == record.get('ref'):
        name = record.get('uuid')
        logging.info(f'The {cls_name} {name} has itself as its "snapshot_of" value, changing to null.')
        record.set('snapshot_of', 'OpaqueRef:NULL')
        record.set('is_a_snapshot', 'false')
        ref = record.get('ref')

def regenerate_database(file):
    logging.info('Regenerating database...')
    tree = ET.parse(file)
    root = tree.getroot()
    vms = root.find('.//table[@name="VM"]')
    vdis = root.find('.//table[@name="VDI"]')
    if vms is None or vdis is None:
        logging.error('Database is missing tables, aborting')
        sys.exit(1)

    for vm in vms.findall('row'):
        fix_record('VM', vm)
    for vdi in vdis.findall('row'):
        fix_record('VDI', vdi)

    return tree

def rewrite_database(original, to):
    tree = regenerate_database(original)
    with open(to, 'wb') as fixed:
        logging.info(f'Writing database to {to}')
        tree.write(fixed, encoding='UTF-8', xml_declaration=True)

def ensure_file_exists(path):
    if not os.path.isfile(path):
        logging.error(f'File {path} does not exist, and cannot continue; aborting.')
        sys.exit(1)

def ensure_file_missing(path):
    if os.path.isfile(path):
        logging.error(f'File {path} already exists, aborting. If you are sure you want to run the command again, please delete the file')
        sys.exit(1)

def copy_database(origin, to):
    shutil.copyfile(origin, to)

def dry_run(args):
    ensure_file_exists(xapi_db)
    regenerate_database(xapi_db)

def restore(args):
    ensure_file_exists(xapi_db_backup)
    if not bypass_checks:
        ha_enabled = query_and_stop_ha()
        stop_xapi()

    try:
        copy_database(xapi_db_backup, to=xapi_db)
    finally:
        start_xapi(ha_enabled)
        if ha_enabled:
            start_ha()

def rewrite(args):
    ensure_file_exists(xapi_db)
    ensure_file_missing(xapi_db_backup)

    if not bypass_checks:
        ha_enabled = query_and_stop_ha()
        stop_xapi()

    try:
        copy_database(xapi_db, to=xapi_db_backup)
        rewrite_database(xapi_db_backup, to=xapi_db)
    finally:
        if not bypass_checks:
            start_xapi(ha_enabled)
            if ha_enabled:
                start_ha()

def get_xcpng_version():
    inventory = {}

    with open("/etc/xensource-inventory") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                inventory[k] = v.strip("'")

    version = inventory.get("PRODUCT_VERSION")

    if not version:
        raise RuntimeError("PRODUCT_VERSION not found")

    major, minor, *_ = version.split(".")
    return int(major), int(minor)


def ensure_supported_version():
    major, minor = get_xcpng_version()

    if (major, minor) < (MIN_MAJOR, MIN_MINOR):
        print(
            f"ERROR: snapshot-fixer.py requires XCP-ng "
            f"{MIN_MAJOR}.{MIN_MINOR} or newer. "
            f"Detected version: {major}.{minor}"
        )
        sys.exit(1)

def main():
    p = ArgumentParser(description='Rewrite erroneous VM snapshot links.')
    p.add_argument('--database', default=None, help='Override the xapi database path (default: /var/lib/xcp/state.db)')
    ps = p.add_subparsers(dest='cmd')
    dp = ps.add_parser('dry-run', help='Prints invalid values in the database, does not stop xapi nor modify the database.')
    dp.set_defaults(func=dry_run)
    bp = ps.add_parser('restore-backup', help='Finds a previous backup, stops xapi, restores the backup and starts xapi.')
    bp.set_defaults(func=restore)
    rp = ps.add_parser('rewrite', help='Stops xapi, backs xapi\'s database up, writes the fixed version, and starts xapi.')
    rp.set_defaults(func=rewrite)
    args = p.parse_args()
    if args.cmd is None:
        p.print_help()
        sys.exit(1)

    if args.database:
        # If the user provided a custom database, we will assume that the provided database is compatible with the script
        # and we will bypass checking the XCP version and stopping / starting HA and XAPI
        xapi_db = args.database
        xapi_db_backup = xapi_db + '.snapshot_of.backup'
        xapi_db_fixed  = xapi_db + '.snapshot_of.fixed'
        bypass_checks = True

    if not bypass_checks:
        ensure_supported_version()

    logging.basicConfig()
    logging.getLogger().setLevel(logging.INFO)

    args.func(args)

if __name__ == '__main__':
    main()
