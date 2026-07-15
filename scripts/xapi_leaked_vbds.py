#!/usr/bin/env python3

import XenAPI

def main():
    session = XenAPI.xapi_local()
    xapi = session.xenapi
    try:
        xapi.login_with_password("root", "", "0.1", "leaked_vbds_script")
        # Get a list of snapshots
        vms = xapi.VM.get_all_records()
        snap_vms = {ref: vm for ref, vm in vms.items() if vm['is_a_snapshot']}
        nonsnap_vms = {ref: vm for ref, vm in vms.items() if not vm['is_a_snapshot']}

        # Dict of {vm: last_snapshot}
        vm_snaps = {vm_ref: vm['parent'] for (vm_ref, vm) in nonsnap_vms.items() if
                    vm['parent'] != 'OpaqueRef:NULL' and
                    not vm['parent'].startswith('Ref:')}

        # Find the snapshots the VM could have been reverted to
        vm_reverted_snaps = {}
        for vm_ref, snap in vm_snaps.items():
            snaps = [snap]
            while True:
                new_snap = xapi.VM.get_parent(snap)

                if new_snap.startswith('Ref:'):
                    new_snap = next((vm_ref for (vm_ref, vm) in snap_vms.items()
                                     if vm['children'] and vm['children'][0] == snap),
                                    'OpaqueRef:NULL')
                if new_snap == 'OpaqueRef:NULL':
                    break
                snaps.append(new_snap)
                snap = new_snap

            vm_uuid = xapi.VM.get_uuid(vm_ref)

            # VM keeps the snapshot's install time
            install_time = xapi.VM_metrics.get_install_time(xapi.VM.get_metrics(vm_ref))
            snaps = [snap for snap in snaps if
                     install_time == xapi.VM_metrics.get_install_time(xapi.VM.get_metrics(snap))]

            if snaps:
                vm_reverted_snaps[vm_ref] = snaps

        for vm, snapshots in vm_reverted_snaps.items():
            # List of VBDs that are attached to VMs
            vm_vbds = xapi.VM.get_VBDs(vm)
            vm_vbds = {xapi.VBD.get_device(vbd_ref): vbd_ref for vbd_ref in vm_vbds}
            vm_set = set(vm_vbds)
            vm_uuid = xapi.VM.get_uuid(vm)

            for snap in snapshots:
                # List of VBDs that are attached to snapshots
                snapshotted_vbds = xapi.VM.get_VBDs(snap)
                snapshotted_vbds = {xapi.VBD.get_device(vbd_ref): vbd_ref for vbd_ref in snapshotted_vbds}
                snap_set = set(snapshotted_vbds)

                # List of VBDs that are not part of the snapshotted VM but
                # are attached to the VM currently
                diff = set(vm_vbds) - snap_set
                if diff:
                    vm_uuid = xapi.VM.get_uuid(vm)
                    vm_name_label = xapi.VM.get_name_label(vm)
                    snap_uuid = xapi.VM.get_uuid(snap)
                    snap_name_label = xapi.VM.get_name_label(snap)
                    vbds = ','.join([f'{dev} ({xapi.VBD.get_uuid(vm_vbds[dev])})' for dev in diff])
                    print(f'VM {vm_uuid} ("{vm_name_label}") has VBDs that are'
                    f' not present in the snapshot it was reverted to ({snap_uuid}'
                    f' "{snap_name_label}"): {vbds}')

    finally:
        session.xenapi.session.logout()

if __name__ == "__main__":
    main()
