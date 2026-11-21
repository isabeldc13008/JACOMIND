# Simula una instancia Lightsail Ubuntu 24.04 con systemd como PID 1 (solo para pruebas).
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -q && apt-get install -y -q systemd systemd-sysv sudo curl ca-certificates && \
    rm -f /lib/systemd/system/multi-user.target.wants/* /etc/systemd/system/*.wants/* \
          /lib/systemd/system/sockets.target.wants/*udev* /lib/systemd/system/sysinit.target.wants/systemd-tmpfiles-setup*
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
