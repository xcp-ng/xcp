#!/usr/bin/env python3

import koji  # type: ignore

config = koji.read_config("koji")
s = koji.ClientSession('https://kojihub.xcp-ng.org', config)
s.ssl_login(config['cert'], None, config['serverca'])

# We look for builds tagged only with built-by-xcp-ng, and no other tag
# These are builds that we don't need in our history and that we could
# delete to recover some disk space.
# To do so, we just untag them, so that koji-gc later marks them for deletion
# if all conditions for this are met.
tag = 'built-by-xcp-ng'
tagged = s.listTagged(tag)
result = []
with s.multicall() as m:
    result = [m.listTags(binfo) for binfo in tagged]
loners = []
for binfo, tinfos in zip(tagged, result):
    tags = [tinfo['name'] for tinfo in tinfos.result]
    if len(tags) == 1:
        loners.append((binfo['id'], binfo['nvr']))

print("The following packages built by XCP-ng don't belong to any tag other than %s" % tag)
print("and will be removed from it so that they can be garbage-collected later.")
for id, nvr in loners:
    print("Untagging build {} ({}) from {}.".format(id, nvr, tag))
    s.untagBuild(tag, id)
