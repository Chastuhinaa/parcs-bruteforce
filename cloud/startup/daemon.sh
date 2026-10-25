#!/bin/bash
exec > >(tee /var/log/parcs.log | sed 's/^/PARCS| /' > /dev/ttyS0) 2>&1
export DEBIAN_FRONTEND=noninteractive
apt_retry() { for i in $(seq 1 60); do apt-get "$@" && return 0; \
              echo "apt busy, retry $i"; sleep 10; done; return 1; }

echo "daemon: installing java"
apt_retry update -qq
apt_retry install -y -qq openjdk-17-jdk-headless wget

wget -q -O /root/Daemon.jar \
     https://github.com/lionell/labs/raw/master/parcs/Daemon/Daemon.jar

cd /root
nohup java -jar Daemon.jar > daemon.out 2>&1 </dev/null &
echo "daemon: ready"
