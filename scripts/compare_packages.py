#!/bin/env python
from __future__ import print_function
from collections import OrderedDict
import argparse
import os
import glob
import subprocess
from datetime import datetime

def list_rpms(directory):
    rpms = OrderedDict()
    for filepath in sorted(glob.glob(os.path.join(directory, '*.rpm'))):
        info = subprocess.check_output(['rpm', '-qp', filepath, '--qf',
                                        "%{name},,%{license},,%{vendor},,%{buildhost},,"
                                        "%{buildtime},,%{evr},,%{sourcerpm},,%{summary}"])
        info = info.split(',,')
        rpms[info[0]] = {
            'filepath': filepath,
            'filename': os.path.basename(filepath),
            'license': info[1],
            'vendor': info[2],
            'buildhost': info[3],
            'buildtime': datetime.fromtimestamp(float(info[4])),
            'evr': info[5],
            'sourcerpm': info[6],
            'summary': info[7]
        }
    return rpms

def main():
    parser = argparse.ArgumentParser(description='Compares two sets of RPM packages')
    parser.add_argument('dir1', help='first directory')
    parser.add_argument('dir2', help='second directory')
    args = parser.parse_args()

    DEVNULL = open(os.devnull, 'w')

    dir1 = os.path.abspath(args.dir1)
    dir2 = os.path.abspath(args.dir2)

    # list RPMs
    rpms1 = list_rpms(dir1)
    rpms2 = list_rpms(dir2)

    for name, info in rpms1.iteritems():
        if name not in rpms2:
            info['removed'] = True
            rpms2[name] = info

    rpms2 = OrderedDict(sorted(rpms2.iteritems(), key=lambda t: t[0]))

    vendors = set([info['vendor'] for info in rpms1.itervalues()])
    vendors |= set([info['vendor'] for info in rpms2.itervalues()])

    for vendor in sorted(list(vendors)):
        print("\n\n-------------------- Vendor: %s ------------------------\n" % vendor)
        for name, info in rpms2.iteritems():
            if info['vendor'] != vendor:
                continue
            if name not in rpms1:
                print("*** %s added" % info['filename'])
                print("Summary: %s" % info['summary'])
                print("License: %s" % info['license'])
                print(subprocess.check_output(['rpm', '-qlp', info['filepath']]))
            elif info.get('removed', False):
                print("*** %s removed" % info['filename'])
                print("Summary: %s" % info['summary'])
                print("License: %s" % info['license'])
                print(subprocess.check_output(['rpm', '-qlp', info['filepath']]))
            else:
                previous = rpms1[name]['filename']
                if info['evr'] == rpms1[name]['evr']:
                    # version unchanged, check diff
                    ret = subprocess.call(['diff', '-q', rpms1[name]['filepath'], info['filepath']],
                                          stdout=DEVNULL, stderr=subprocess.STDOUT)
                    if (ret != 0):
                        status = "%s EVR unchanged, new file differs" % previous
                    else:
                        status = "%s EVR unchanged, new file identical" % previous
                    print("*** %s" % status)
                else:
                    status = "%s => %s" % (previous, info['filename'])
                    print("*** %s" % status)
                    if info['summary'] != rpms1[name]['summary']:
                        print("Summary (previous): %s" % rpms1[name]['summary'])
                    print("Summary: %s" % info['summary'])
                    if info['license'] != rpms1[name]['license']:
                        print("License (previous): %s" % rpms1[name]['license'])
                    print("License: %s" % info['license'])

                print(subprocess.check_output("rpmdiff -iT %s %s 2>&1 || echo" % (rpms1[name]['filepath'], info['filepath']),
                                              shell=True),
                      end='')

if __name__ == "__main__":
    main()
