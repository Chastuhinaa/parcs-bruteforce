#!/bin/bash
exec > >(tee /var/log/parcs.log | sed 's/^/PARCS| /' > /dev/ttyS0) 2>&1
export DEBIAN_FRONTEND=noninteractive
MD="http://metadata.google.internal/computeMetadata/v1/instance"
md_attr()  { curl -sf -H "Metadata-Flavor: Google" "$MD/attributes/$1"; }
apt_retry() { for i in $(seq 1 60); do apt-get "$@" && return 0; \
              echo "apt busy, retry $i"; sleep 10; done; return 1; }

echo "hosts-server: installing java"
apt_retry update -qq
apt_retry install -y -qq openjdk-17-jdk-headless wget curl
wget -q -O /root/TCPHostsServer.jar \
     https://github.com/lionell/labs/raw/master/parcs/HostsServer/TCPHostsServer.jar

echo "hosts-server: waiting for daemon IPs"
until IPS=$(md_attr daemon-ips); do sleep 2; done

cd /root
printf '%s\n' $IPS > hosts.list
echo "hosts-server: hosts.list = $IPS"
nohup java -jar TCPHostsServer.jar > hosts.out 2>&1 </dev/null &
echo "hosts-server: ready"
