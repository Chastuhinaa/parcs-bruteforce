#!/bin/bash
exec > >(tee /var/log/parcs.log | sed 's/^/PARCS| /' > /dev/ttyS0) 2>&1
export DEBIAN_FRONTEND=noninteractive
MD="http://metadata.google.internal/computeMetadata/v1/instance"
md_attr()  { curl -sf -H "Metadata-Flavor: Google" "$MD/attributes/$1"; }
apt_retry() { for i in $(seq 1 60); do apt-get "$@" && return 0; \
              echo "apt busy, retry $i"; sleep 10; done; return 1; }

REPO=$(md_attr repo)
echo "app: installing toolchain"
apt_retry update -qq
apt_retry install -y -qq openjdk-17-jdk-headless git make curl

echo "app: waiting for hosts-server IP"
until HS=$(md_attr hosts-server-ip); do sleep 2; done

rm -rf lab && git clone -q "$REPO" lab && cd lab
echo "$HS" > out/server

echo "app: running measurement against hosts-server $HS"
make run

echo "PARCS-CSV-START"
cat out/results.csv
echo "PARCS-CSV-END"
echo "app: done"
