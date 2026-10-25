#!/usr/bin/env bash
set -euo pipefail

ZONE="europe-north1-a"
REGION="europe-north1"
IMAGE_FAMILY="debian-12"
IMAGE_PROJECT="debian-cloud"
MACHINE="e2-standard-2"
REPO="https://github.com/Chastuhinaa/parcs-bruteforce.git"

DAEMONS=(daemon-1 daemon-2 daemon-3 daemon-4)
PARCS_BASE="https://github.com/lionell/labs/raw/master/parcs"

echo ">> Checking regional vCPU quota in $REGION ..."
CPU_LIMIT=$(gcloud compute regions describe "$REGION" \
    --flatten="quotas" --format="csv[no-heading](quotas.metric,quotas.limit)" 2>/dev/null \
    | awk -F, '$1=="CPUS"{print $2}' || true)
CPU_LIMIT=${CPU_LIMIT%.*}
CPU_LIMIT=${CPU_LIMIT:-0}
NEED=$(( ( ${#DAEMONS[@]} + 1 ) * 2 ))
echo "   quota=$CPU_LIMIT vCPU, need=$NEED vCPU for app + ${#DAEMONS[@]} daemons"
if [ "$CPU_LIMIT" -gt 0 ] && [ "$CPU_LIMIT" -lt "$NEED" ]; then
    MAX_D=$(( CPU_LIMIT / 2 - 1 ))
    if [ "$MAX_D" -lt 1 ]; then MAX_D=1; fi
    echo "   !! quota too small; reducing to $MAX_D daemons"
    DAEMONS=("${DAEMONS[@]:0:$MAX_D}")
elif [ "$CPU_LIMIT" -eq 0 ]; then
    echo "   (could not read quota — proceeding with ${#DAEMONS[@]} daemons)"
fi

echo ">> Enabling Compute Engine API ..."
gcloud services enable compute.googleapis.com

exists() { gcloud compute instances describe "$1" --zone="$ZONE" >/dev/null 2>&1; }

create_if_missing() {
    if exists "$1"; then
        echo "   $1 already exists — skipping"
    else
        echo "   creating $1 ($2) ..."
        gcloud compute instances create "$1" \
            --zone="$ZONE" --machine-type="$2" \
            --image-family="$IMAGE_FAMILY" --image-project="$IMAGE_PROJECT" \
            --quiet
    fi
}

echo ">> Creating VMs ..."
create_if_missing app "$MACHINE"
create_if_missing hosts-server e2-micro
for d in "${DAEMONS[@]}"; do create_if_missing "$d" "$MACHINE"; done

echo ">> Firewall rule for tcp:2222 (daemon), tcp:3333 (hosts-server) ..."
if ! gcloud compute firewall-rules describe allow-parcs >/dev/null 2>&1; then
    gcloud compute firewall-rules create allow-parcs \
        --direction=INGRESS --priority=1000 --network=default \
        --action=ALLOW --rules=tcp:2222,tcp:3333 --source-ranges=10.0.0.0/8
else
    echo "   allow-parcs already exists — skipping"
fi

internal_ip() {
    gcloud compute instances describe "$1" --zone="$ZONE" \
        --format='get(networkInterfaces[0].networkIP)'
}

ensure_ssh_key() {
    [ -f "$HOME/.ssh/google_compute_engine" ] || \
        ssh-keygen -t rsa -N "" -f "$HOME/.ssh/google_compute_engine" -q
}

wait_ssh() {
    echo "   waiting for ssh on $1 ..."
    for _ in $(seq 1 40); do
        gcloud compute ssh "$1" --zone="$ZONE" --command="true" \
            --ssh-flag="-o ConnectTimeout=10" >/dev/null 2>&1 && return 0
        sleep 5
    done
    echo "   !! ssh on $1 not ready"; return 1
}

echo ">> Installing Java and starting daemons ..."
ensure_ssh_key
for d in "${DAEMONS[@]}"; do
    wait_ssh "$d"
    gcloud compute ssh "$d" --zone="$ZONE" --command="
        sudo apt-get update -qq &&
        sudo apt-get install -y -qq openjdk-17-jdk-headless wget &&
        wget -q -O Daemon.jar $PARCS_BASE/Daemon/Daemon.jar &&
        (ss -ltn | grep -q ':2222' || (nohup java -jar Daemon.jar > daemon.log 2>&1 </dev/null & echo \$! > daemon.pid))"
done

echo ">> Starting hosts-server ..."
DAEMON_IPS=$(for d in "${DAEMONS[@]}"; do internal_ip "$d"; done | tr '\n' ' ')
wait_ssh hosts-server
gcloud compute ssh hosts-server --zone="$ZONE" --command="
    sudo apt-get update -qq &&
    sudo apt-get install -y -qq openjdk-17-jdk-headless wget &&
    wget -q -O TCPHostsServer.jar $PARCS_BASE/HostsServer/TCPHostsServer.jar &&
    printf '%s\n' $DAEMON_IPS > hosts.list &&
    (ss -ltn | grep -q ':3333' || (nohup java -jar TCPHostsServer.jar > hosts.log 2>&1 </dev/null & echo \$! > hosts.pid))"

echo ">> Deploying app and running the measurement ..."
HS_IP=$(internal_ip hosts-server)
wait_ssh app
gcloud compute ssh app --zone="$ZONE" --command="
    sudo apt-get update -qq &&
    sudo apt-get install -y -qq openjdk-17-jdk-headless git make &&
    rm -rf lab && git clone -q $REPO lab &&
    cd lab &&
    echo $HS_IP > out/server &&
    make run"

echo ">> Fetching results.csv ..."
gcloud compute scp "app:~/lab/out/results.csv" ./results.csv --zone="$ZONE" || true

echo
echo ">> Done. To delete every billed machine when finished:"
echo "   gcloud compute instances delete app hosts-server ${DAEMONS[*]} --zone=$ZONE --quiet"
