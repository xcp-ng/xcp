This directory contains a collection of scripts whose purpose
is to analyze XCP-ng RPMs and produce useful reports out of it:
- version comparison with CentOS, EPEL and upstream projects
- analysis of the dependencies
- what initially comes from XenServer, what comes from XCP-ng, why,
- and more...

There are prerequisites to be able to run them, among which:
- read access to our koji hub through the `koji` CLI tool (e.g. using the vatesbot user)
- read rsync access to updates.xcp-ng.org
- ability to start and use a CentOS docker image (see docker_commands.txt)
- python-rpm
- python-markdown

See run.sh for the way and order the scripts are run in.
