# Workflow to merge into feature tags

We now have two feature tags, `v8.3-v-storagepreview` and
`v8.3-v-kernelpreview` that can be used to share early feature previews to
our end users without affecting the main updates stream.

A special workflow to get those features out, and eventually merge them
into `v8.3`, is laid out here.


## Create 8.3-<feature>preview branches and open your PRs against it

The PRs to merge changes into the feature tag will need to be opened
against the `8.3-<feature>preview` branch, so the first step is to create
those, pointing to `8.3` initially.  In the SRPMs repositories impacted:

```bash
git fetch origin
git push origin origin/8.3:refs/heads/8.3-<feature>preview
```

For example, assuming the feature is `kernelpreview`:

```bash
git fetch origin
git push origin origin/8.3:refs/heads/8.3-kernelpreview
```

## Do test-builds in your user tags for testing

Make sure to add a `<feature>preview` marker to the Release version, so
that we cannot confuse a package meant for preview tags.

e.g. for the kernel:

```diff
diff --git a/SPECS/kernel.spec b/SPECS/kernel.spec
index 3d4345b78aef..fcfdc846b704 100644
--- a/SPECS/kernel.spec
+++ b/SPECS/kernel.spec
@@ -45,7 +45,7 @@
 Name: kernel
 License: GPLv2
 Version: %{usver}
-Release: %{?xsrel}.16%{?dist}
+Release: %{?xsrel}.16.0.kernelpreview.1%{dist}
```

> [!IMPORTANT]
>
> Don't just prepend `.<feature>preview`, and make sur to have the `.0` (or
> any other number as you create new releases) as a release suffix
> otherwise the EVR in xcp-ng-updates takes precedence, as it will compare
> the first character of your feature, 'k' for kernelpreview, or 's' for
> storagepreview with the 'x' in xcpng8.3.  I've learned this the hard way.

Then do your builds as you usually would, in your user tag with either
--test-build (if you use --pre-builds, they won't have precedence over
what's already in xcp-ng-updates):

```bash
koji_build.py --test-build testbuild v8.3-u-<usertag> .
```

For example, for a build targetting `v8.3-kernelpreview` built by Quentin
Casasnovas:

```bash
koji_build.py --test-build testbuild v8.3-u-qcasasnovas1 .
```

This will add a `-0.tesbuild.<X>` suffix to your release, where <X> will be
auto-incremented every time you start a new build from the same EVR.

The main difference between `--pre-build` and `--test-build` is precedence
on yum update with:
```
# For the same EVR
--pre-build < normal build < --test-build
```

You can then share your user tag repository in the PR so that reviewers can
test the resulting packages.

## Official <feature>preview builds and CI.

All the packages inside the `v8.3-v-<feature>preview` tag have to be built
from the newly created `8.3-<feature>preview` branch, once the PRs have
been merged.

To do so do a normal build, in `v8.3-v-<feature>preview-incoming` (like you
would in v8.3-incoming):

```bash

git fetch origin
git checkout -B 8.3-featurepreview origin/8.3-featurepreview
koji_build.py v8.3-v-<feature>preview-incoming .
```

This last build is the equivalent of the build in `v8.3-incoming`, and
that's what needs to go to CI.

Once the CI comes back green, that build can be moved from the user tag
into the `v8.3-v-<feature>preview`.

> [!WARNING]
>
> An update in xcp-ng-update bumping the `Release` field to something more
> recent than what is released in the `xcp-ng-<feature>preview` repository
> will now have precedence and causes risks to be prefered over the preview
> packages.  It is up to the feature teams to find a way to prevent the
> system from being in an inconsistent state.
>
> For the kernel, this is achieved by the kernel having a Version field
> always bigger than what is in xcp-ng-updates (4.19.325 versus 4.19.19),
> and all dependent modules having a hard dependency on the kernel-uname-r
> they were built against, so that yum would refuse to update a driver once
> the techpreview kernel is installed, preventing inconsistencies.

## Create forum post

Now is time to create the forum post with instructions to end users on how
to enable the feature tag repository and install the tech preview packages.
The instructions should also include a way to go back to the main
repositories.

The instructions to install the preview packages look like this (needs to
be run as root):

```bash
# Download the repo file
wget -O /etc/yum.repos.d/xcp-ng-previews.repo https://repo.vates.tech/xcp-ng/8/8.3/xcp-ng-previews.repo

# Enable the <feature>preview repository
yum-config-manager --enable xcp-ng-<feature>preview

# Update the packages (accept the GPG key once verified)
yum update
```

The instructions to downgrade the kernel and corresponding modules look
like this:

```bash

# Disable the kernelpreview repository
yum-config-manage --disable xcp-ng-kernelpreview

yum downgrade --setopt=protected_packages=                                                            \
	$(repoquery --repoid=xcp-ng-updates kernel)                                                              \
	$(repoquery --installed --whatrequires 'kernel-uname-r = 4.19.325-cip137' | sed 's/-.:.*//')
```

It should be made clear in the forum post that security updates are _not_
guaranteed on the tech preview packages, and that in order to be fully
patched, a downgrade to the xcp-ng-updates packages might be necessary.
