# AlmaLinux 10 is maintained until 2035, longer than XCP-ng 8.3
FROM almalinux:10
RUN dnf install -y python3-rpm python3-markdown awscli2 && dnf clean all
ADD rpmwatcher.py autoindex.py entrypoint.sh /rpmwatcher/
ADD data/centos7-srpms.json data/epel7-srpms.json /rpmwatcher/data/
# S3 compatible servers (e.g. Garage) don't always support virtual-hosted style URLs
RUN printf '[default]\ns3 =\n    addressing_style = path\n' > /rpmwatcher/aws-config
ENV AWS_CONFIG_FILE=/rpmwatcher/aws-config
# Recent aws-cli versions send checksums that some S3 compatible servers reject
ENV AWS_REQUEST_CHECKSUM_CALCULATION=when_required AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
ENTRYPOINT ["/rpmwatcher/entrypoint.sh"]
