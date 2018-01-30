# Project description

## XCP new generation: free/libre and 100% community backed XenServer

### What is it?

Currently, XenServer is a turnkey virtualization plat-form, distributed as a distribtion (based on CentOS). It comes with a feature rich toolstack, called XAPI. Vast majority of XenServer code is Open Source.

**But since XenServer 7.3, Citrix removed a lot of features from it. The goal of XCP-ng is to make a fully community backed version of XenServer, without any feature restrictions.**

The other goal is to also create a real ecosystem, not depending of one company only. More sponsors = healthier project!

### How the money will be used?

The money will be **managed transparently** (ie publicly), on the [XCP meta-repo](https://github.com/xcp-ng/xcp). Priorities are to **bootstrap the project quickly**, and produce documentation to let everyone able to build it. In order to do that, here is how the money will be used, in priority to:

1. compensate people time directly contributing (with XenServer/XAPI/CentOS experience)
2. pay for various project hosting fees
3. communicate around it

### Where We Are Now?

The first proof-of-concept is [already working](https://xcp-ng.github.io/news/2018/01/22/xcp-ng-on-tracks.html), so it's technically doable. The next step is to achieve *Phase I*.

#### Phase I

Initial release of XCP-ng, based on latest XenServer sources. Simple yet functional release, with:

* a manually crafted XCP-ng ISO
* a RPM repo

#### Phase II

Automation + documentation for building XCP-ng packages, creating the ISO and/or the RPM repo. Also:

* turn a CentOS into XCP-ng via RPM repo
* turn a XenServer to XCP-ng via ISO upgrade

#### Phase III

Community code inserted into XCP-ng project, like:

* bundled Gluster support
* Software RAID during install
* ZFS driver
* better compression
* etc.

### People and companies behind XCP-ng

#### Companies

* Vates (Xen Orchestra editor)
* Zentific
* Your company if you sponsor it!

#### People

* Olivier (Xen Orchestra project founder)
* John Else (contractor, former XAPI dev)
* Nick Couchman
* Jon Sands
* Mike Hidalgo

### Risks and challenges

With a software development project like this (involving various pieces of existing code), the biggest risk and challenge is inevitably shipping on time.

To combat delays, we'll be setting regular milestones and work with people with previous developer experience on XenServer, XAPI and CentOS.

This biggest challenge will be to deliver simple upgrade path from XenServer and also give a seamless experience to go from a CentOS to XCP-ng (via RPM repository).

### FAQ

* Will it be "compatible" with XenCenter?

In short: yes. We aim to have a codebase that's close to XenServer. We can't be 100% sure about Citrix products on top of XenServer (if they check product name), but API will be 100% compatible. For example, Xen Orchestra will work on top of XCP-ng.

* Will `xe` CLI still works?

Absolutely. `xe` won't be changed.

* Is it possible to upgrade an existing XenServer to XCP-ng?

That's one of the project's goal, indeed. We want to provide a simple upgrade path to let people "update" their infrastructure without high migration costs.

* Will I enjoy all features for free?

All features available from the sources of XenServer will be free. No more pool size limitation, or VDI live migration restrictions.

* Is there any pro support coming?

It's a bit early to say. Pro support or not, XCP-ng will stay a community project anyway. No one will "steal" it for it's own agenda.

* Why "XCP-ng" name?

Because in the past, XCP (aka "Xen Cloud Project") had the similar objective. However, the project was stalled because only Citrix was behind it. Nobody want to do the same mistake: it's up to you to be a sponsor or a contributor!