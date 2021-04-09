#!/bin/bash

# remove old scratch builds

TOPDIR=/mnt/koji
TIMEARG="+90"
IFS=$'\n'

# we completely remove those that are old enough
# scratch directories are /mnt/koji/scratch/$username/task_$taskid/
# note that $username might contain a slash (e.g. host principals)
cd $TOPDIR/scratch/
for x in $(find $TOPDIR/scratch/ -mindepth 2 -type d -name 'task_*' -prune -mtime $TIMEARG); do
    find "$x" -xdev "!" -type d -printf '%s\t %p\n' -delete -exec touch {}.deleted \; -exec chown apache.apache {}.deleted \;
done

# for tasks, try to remove as a unit
for x in $(find "$TOPDIR"/work/tasks/ -mindepth 2 -maxdepth 2 -type d -mtime $TIMEARG); do
    # delete broken symlinks (that will be links to deleted scratch builds) but leave other symlinks alone
    find "$x" -xdev -xtype l -printf '%s\t %p\n' -delete -exec touch {}.deleted \; -exec chown apache.apache {}.deleted \;
    # Delete SRPMs from buildSRPMFromSCM tasks.
    # There is a slight loss of information because the SRPM that is stored in the
    # packages/ directory is the one coming from the buildArch task.
    # In our case, they should be strictly equivalent, though.
    find "$x" -xdev -type f -name "*.src.rpm" -printf '%s\t %p\n' -delete -exec touch {}.deleted \; -exec chown apache.apache {}.deleted \;
done

# for anything else, just remove old stuff
# but don't remove the top level dirs (e.g. cli-build)
#for x in $(find "$TOPDIR"/work -maxdepth 1 -mindepth 1 \! -name tasks); do
#    find "$x" -xdev '!' -type d -mtime $TIMEARG -print
#    find "$x" -xdev '!' -type d -mtime $TIMEARG -print0 | xargs -0 -r rm -f
#    find "$x" -xdev -depth -mindepth 1 -type d -empty -print0 | xargs -0 -r rmdir
#    find "$x" -xdev -depth -mindepth 1 -type d -empty -print
#done

