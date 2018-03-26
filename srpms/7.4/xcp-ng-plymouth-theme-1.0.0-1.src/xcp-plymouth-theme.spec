Summary:        A plymouth theme for XCP-ng
Name:           xcp-ng-plymouth-theme
Version:        1.0.0
Release:        1
License:        GPLv2+
Group:          System Environment/Base

Source0:         https://code.citrite.net/rest/archive/latest/projects/XS/repos/%{name}/archive?at=v%{version}&format=tar.gz&prefix=%{name}-%{version}#/%{name}.tar.gz

BuildRoot:      %{_tmppath}/%{name}-%{version}
BuildArch:      noarch
Requires:       plymouth, plymouth-plugin-script, plymouth-graphics-libs, gnu-free-sans-fonts
BuildRequires:  kernel-devel

%define themedir     %{_datadir}/plymouth/themes/xcp-ng
%define plymouthconf %{_sysconfdir}/plymouth/plymouthd.conf

%description
The %{name} package contains the XCP-ng theme for plymouth.

%prep
%autosetup -p1 -n xcp-ng-plymouth-theme-1.0.0

%install

install -m 755 -d %{buildroot}/%{themedir}
install -m 755 -p -D xcp-ng.plymouth xcp-ng.script -t %{buildroot}/%{themedir}
install -m 755 -p -D background.png progress_bar.png progress_box.png -t %{buildroot}/%{themedir}

%post
/usr/sbin/plymouth-set-default-theme xcp-ng
%{regenerate_initrd_post}

%postun
if grep -q "^Theme *= *xcp-ng *$" "%{plymouthconf}"; then
   /usr/sbin/plymouth-set-default-theme text
   %{regenerate_initrd_postun}
fi

%posttrans
%{regenerate_initrd_posttrans}

%triggerin -- plymouth

if grep -q "^ShowDelay *=" "%{plymouthconf}"; then
    sed -i 's/^ShowDelay *=.*/ShowDelay = 0/' %{plymouthconf}
else
    echo ShowDelay = 0 >> %{plymouthconf}
fi

%files
%{themedir}/xcp-ng.plymouth
%{themedir}/xcp-ng.script
%{themedir}/background.png
%{themedir}/progress_bar.png
%{themedir}/progress_box.png
