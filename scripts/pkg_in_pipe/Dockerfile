FROM fedora:41
RUN dnf install -y koji python3-requests python3-pip python3-pygithub
RUN pip install specfile diskcache
VOLUME /tmp/pkg_in_pipe.cache
ADD pkg_in_pipe.py /
ENTRYPOINT ["/pkg_in_pipe.py"]
