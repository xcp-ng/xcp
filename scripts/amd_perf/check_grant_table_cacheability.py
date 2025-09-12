#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pathlib
import re

# Grant table cacheability test tool.


def find_xen_platform_pci():
    for child in pathlib.Path("/sys/bus/pci/drivers/xen-platform-pci").iterdir():
        if child.is_dir():
            return child
    return None


def xen_platform_pci_io_address(xen_platform_pci_id):
    # Find 'xen-platform-pci' IO mem resource address.
    pci_resource_output = (xen_platform_pci_id / "resource").read_text()

    # First line is taken by PCI IO port, select 2nd line for IO mem.
    address_line = pci_resource_output.splitlines()[1].split()
    start_address = int(address_line[0], 16)
    return start_address


def mtrr_ranges():
    # List and check MTRR ranges.
    return pathlib.Path("/proc/mtrr").read_text().splitlines()


def are_grant_tables_inside_uncachable_mapping(mtrr_ranges_list, pci_io_address):
    regexp = r'reg(.*): base=(0x[0-9a-f]*) \(.*\), size=(.*)MB, count=(.*): (.*)'

    for mtrr_range in mtrr_ranges_list:
        m = re.match(regexp, mtrr_range)
        base_address = int(m.group(2), 16)
        size = int(m.group(3)) * 1024 * 1024
        cache_mode = m.group(5)

        # Check that PCI io memory address is inside MTRR configuration.
        if pci_io_address >= base_address and pci_io_address < base_address + size and cache_mode == "uncachable":
            return True
    return False


if __name__ == "__main__":
    pci = find_xen_platform_pci()
    if pci is None:
        print("Could not find xen-platform-pci device")
        exit(2)
    pci_io_address = xen_platform_pci_io_address(pci)
    print("'xen-platform-pci' PCI IO mem address is 0x{0:08X}".format(pci_io_address))
    mtrr_ranges_list = mtrr_ranges()
    if are_grant_tables_inside_uncachable_mapping(mtrr_ranges_list, pci_io_address):
        print("Grant table cacheability fix is NOT ACTIVE.")
        exit(1)
    else:
        print("Grant table cacheability fix is ACTIVE.")
        exit(0)
