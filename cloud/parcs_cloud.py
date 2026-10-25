import argparse
import base64
import json
import os
import sys
import time

from google.cloud import compute_v1

ZONE     = "europe-north1-b"
REGION   = "europe-north1"
MACHINE  = "e2-standard-2"
MICRO    = "e2-micro"
IMAGE    = "projects/debian-cloud/global/images/family/debian-12"
REPO     = "https://github.com/Chastuhinaa/parcs-bruteforce.git"
LABEL    = {"parcs": "1"}
DAEMONS  = ["daemon-1", "daemon-2", "daemon-3", "daemon-4"]
HERE     = os.path.dirname(os.path.abspath(__file__))
POLL     = 5


class Api:
    def __init__(self):
        self.calls = []
        self.instances = compute_v1.InstancesClient()
        self.firewalls = compute_v1.FirewallsClient()
        self.regions = compute_v1.RegionsClient()
        self.machine_types = compute_v1.MachineTypesClient()

    def _timed(self, name, fn):
        t0 = time.time()
        result = fn()
        self.calls.append((name, time.time() - t0))
        return result

    def summary(self):
        from collections import Counter
        c = Counter(n for n, _ in self.calls)
        print("\n=== API call summary ===")
        print(f"total calls: {len(self.calls)}")
        for name, cnt in c.most_common():
            lat = [d for n, d in self.calls if n == name]
            print(f"  {name:28s} x{cnt:<3d} avg {sum(lat)/len(lat)*1000:6.0f} ms")


def startup(role):
    with open(os.path.join(HERE, "startup", f"{role}.sh"), encoding="utf-8") as f:
        return f.read()


def metadata(items):
    md = compute_v1.Metadata()
    md.items = [compute_v1.Items(key=k, value=v) for k, v in items.items()]
    return md


def instance_resource(name, mtype, role):
    inst = compute_v1.Instance()
    inst.name = name
    inst.machine_type = f"zones/{ZONE}/machineTypes/{mtype}"
    inst.labels = LABEL

    disk = compute_v1.AttachedDisk()
    disk.boot = True
    disk.auto_delete = True
    disk.initialize_params = compute_v1.AttachedDiskInitializeParams(source_image=IMAGE)
    inst.disks = [disk]

    nic = compute_v1.NetworkInterface()
    nic.network = "global/networks/default"
    nic.access_configs = [compute_v1.AccessConfig(name="External NAT",
                                                  type_="ONE_TO_ONE_NAT")]
    inst.network_interfaces = [nic]

    inst.metadata = metadata({"startup-script": startup(role), "repo": REPO})
    return inst


# --- signalling: VMs report over the serial port (reliable one-way channel) ---

def serial_log(api, project, name):
    try:
        out = api._timed("instances.getSerialPortOutput",
            lambda: api.instances.get_serial_port_output(
                project=project, zone=ZONE, instance=name))
        return out.contents or ""
    except Exception:
        return ""


def parcs_lines(log):
    return [l[len("PARCS| "):] for l in log.splitlines() if l.startswith("PARCS| ")]


def wait_ready(api, project, names, label, marker, timeout=600):
    print(f">> waiting for {label} to report ready")
    pending = set(names)
    start = time.time()
    while pending:
        for name in list(pending):
            if any(l.strip() == marker for l in parcs_lines(serial_log(api, project, name))):
                print(f"   {name} ready")
                pending.discard(name)
        if pending:
            if time.time() - start > timeout:
                raise SystemExit(f"Timeout waiting for {label}: {sorted(pending)}")
            time.sleep(POLL)


def check_quota(api, project):
    print(f">> quota check in {REGION}")
    region = api._timed("regions.get",
                        lambda: api.regions.get(project=project, region=REGION))
    cpus = next((q for q in region.quotas if q.metric == "CPUS"), None)
    limit = cpus.limit if cpus else 0
    usage = cpus.usage if cpus else 0
    need = (len(DAEMONS) + 1) * 2
    api._timed("machineTypes.get",
               lambda: api.machine_types.get(project=project, zone=ZONE,
                                             machine_type=MACHINE))
    print(f"   CPUS quota={limit:.0f} usage={usage:.0f} need={need}")
    if limit - usage < need:
        raise SystemExit(f"Not enough vCPU quota: need {need}, free {limit - usage:.0f}.")


def ensure_firewall(api, project):
    name = "allow-parcs"
    print(f">> firewall rule {name} (tcp:2222, tcp:3333)")
    try:
        api._timed("firewalls.get",
                   lambda: api.firewalls.get(project=project, firewall=name))
        print("   already exists")
        return
    except Exception:
        pass
    fw = compute_v1.Firewall()
    fw.name = name
    fw.network = "global/networks/default"
    fw.direction = "INGRESS"
    fw.source_ranges = ["10.0.0.0/8"]
    fw.allowed = [compute_v1.Allowed(I_p_protocol="tcp", ports=["2222", "3333"])]
    api._timed("firewalls.insert",
               lambda: api.firewalls.insert(project=project, firewall_resource=fw).result())


def create_all(api, project):
    print(">> creating 6 VMs (app, hosts-server, 4 daemons)")
    plans = [("app", MACHINE, "app"), ("hosts-server", MICRO, "hosts-server")]
    plans += [(d, MACHINE, "daemon") for d in DAEMONS]
    ops = []
    for name, mtype, role in plans:
        res = instance_resource(name, mtype, role)
        ops.append((name, api._timed("instances.insert",
                   lambda r=res: api.instances.insert(project=project, zone=ZONE,
                                                       instance_resource=r))))
    for name, op in ops:
        api._timed("operations.wait", lambda o=op: o.result())
        print(f"   created {name}")


def internal_ip(api, project, name):
    inst = api._timed("instances.get",
                      lambda: api.instances.get(project=project, zone=ZONE, instance=name))
    return inst.network_interfaces[0].network_i_p


def set_meta(api, project, name, key, value):
    inst = api._timed("instances.get",
                      lambda: api.instances.get(project=project, zone=ZONE, instance=name))
    md = inst.metadata
    md.items.append(compute_v1.Items(key=key, value=value))
    api._timed("instances.setMetadata",
        lambda: api.instances.set_metadata(project=project, zone=ZONE,
                instance=name, metadata_resource=md).result())
    print(f"   set {name}:{key}")


def stream_app_until_done(api, project, timeout=900):
    print(">> live log from app (serial port):")
    printed = 0
    start = time.time()
    while True:
        lines = parcs_lines(serial_log(api, project, "app"))
        for l in lines[printed:]:
            if l.strip() not in ("PARCS-CSV-START", "PARCS-CSV-END"):
                print("   " + l)
        printed = len(lines)
        if any(l.strip() == "app: done" for l in lines):
            return lines
        if time.time() - start > timeout:
            print("!! timeout waiting for app to finish")
            return lines
        time.sleep(POLL)


def collect_results(lines):
    csv, cap = [], False
    for l in lines:
        s = l.strip()
        if s == "PARCS-CSV-START":
            cap = True
            continue
        if s == "PARCS-CSV-END":
            cap = False
            continue
        if cap:
            csv.append(s)
    if not csv:
        print("!! no results captured")
        return
    out = os.path.join(HERE, "..", "results", "cloud_results.csv")
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(csv) + "\n")
    print(f">> results written to {os.path.normpath(out)}")
    print("\n".join(csv))


def delete_tagged(api, project):
    print(">> deleting VMs tagged parcs=1")
    found = api._timed("instances.list",
        lambda: api.instances.list(project=project, zone=ZONE))
    ops = []
    for inst in found:
        if not (inst.labels and inst.labels.get("parcs") == "1"):
            continue
        print(f"   deleting {inst.name}")
        ops.append(api._timed("instances.delete",
            lambda n=inst.name: api.instances.delete(project=project, zone=ZONE, instance=n)))
    for op in ops:
        api._timed("operations.wait", lambda o=op: o.result())
    print("   all deleted")


def print_plan(project):
    plans = [("app", MACHINE), ("hosts-server", MICRO)] + [(d, MACHINE) for d in DAEMONS]
    print(json.dumps({
        "project": project, "zone": ZONE, "region": REGION,
        "quota_check": ["regions.get", "machineTypes.get"],
        "firewall": {"name": "allow-parcs", "ports": ["2222", "3333"]},
        "instances_insert": [{"name": n, "machineType": m} for n, m in plans],
        "wiring": ["setMetadata hosts-server:daemon-ips", "setMetadata app:hosts-server-ip"],
        "teardown": "instances.list -> delete where labels.parcs=1",
    }, indent=2))


def resolve_project():
    for var in ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "CLOUDSDK_CORE_PROJECT"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        import google.auth
        _, project = google.auth.default()
        if project:
            return project
    except Exception:
        pass
    raise SystemExit("Set GOOGLE_CLOUD_PROJECT or run: gcloud config set project <id>")


def main():
    ap = argparse.ArgumentParser(description="Deploy PARCS brute-force via Compute Engine API")
    ap.add_argument("--plan", action="store_true", help="print planned requests, create nothing")
    ap.add_argument("--delete", action="store_true", help="delete tagged VMs and exit")
    ap.add_argument("--keep", action="store_true", help="do not delete VMs at the end")
    args = ap.parse_args()

    project = resolve_project()

    if args.plan:
        print_plan(project)
        return

    api = Api()
    if args.delete:
        delete_tagged(api, project)
        api.summary()
        return

    t0 = time.time()
    try:
        check_quota(api, project)
        ensure_firewall(api, project)
        create_all(api, project)

        wait_ready(api, project, DAEMONS, "daemons", "daemon: ready")
        daemon_ips = "\n".join(internal_ip(api, project, d) for d in DAEMONS)
        set_meta(api, project, "hosts-server", "daemon-ips", daemon_ips)

        wait_ready(api, project, ["hosts-server"], "hosts-server", "hosts-server: ready")
        hs_ip = internal_ip(api, project, "hosts-server")
        set_meta(api, project, "app", "hosts-server-ip", hs_ip)

        lines = stream_app_until_done(api, project)
        collect_results(lines)
    finally:
        if not args.keep:
            delete_tagged(api, project)
        print(f"\ntotal wall time: {time.time() - t0:.1f} s")
        api.summary()


if __name__ == "__main__":
    main()
