# Project description

## XCP-ng: free/libre and 100% community backed XenServer

### What is it?

Currently, XenServer is a turnkey virtualization plat-form, distributed as a distribtion (based on CentOS). It comes with a feature rich toolstack, called XAPI. Vast majority of XenServer code is Open Source.

**But since XenServer 7.3, Citrix removed a lot of features from it. The goal of XCP-ng is to make a fully community backed version of XenServer, without any feature restrictions.**

The other goal is to also create a real ecosystem, not depending of one company only.

# Where We Are Now?

The first proof-of-concept is [already working](https://xcp-ng.github.io/news/2018/01/22/xcp-ng-on-tracks.html), so it's technically doable. The next step is to achieve *Phase I*.

## Phase I

Initial release of XCP-ng, based on latest XenServer sources. Simple yet functional release.

## Phase II

Automation + documentation for building XCP-ng packages, creating the ISO and/or the RPM repo.

## Phase III

Community code inserted into XCP-ng project (Gluster support, soft RAID etc.)

# People and companies behind XCP-ng

* Vates (Xen Orchestra editor)
* Zentific

# Risks and challenges

With a software development project like this (involving various pieces of existing code), the biggest risk and challenge is inevitably shipping on time.

To combat delays, we'll be setting regular milestones and work with people with previous developer experience on XenServer, XAPI and CentOS.

This biggest challenge will be to deliver simple upgrade path from XenServer and also give a seamless experience to go from a CentOS to XCP-ng (via RPM repository).

# FAQ