"""Pull a usage snapshot of the Phaze enterprise from the public API.

Writes raw.json (real names, stays local) and data.json (pseudonymized, the only
file the dashboard embeds). Read-only: only GET requests.

Usage: python fetch.py             (live snapshot)
       python fetch.py --offline   (rebuild data.json from an existing raw.json)
API key: PHAZE_API_KEY env var, else PHAZE_API_KEY in a .env file next to this script.
Optional: PHAZE_API_BASE to point at another API host.
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKIP_EMPTY_ORGS = True


class NotFound(RuntimeError):
    pass


def env_value(name):
    if os.environ.get(name):
        return os.environ[name].strip()
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(rf"\s*{name}\s*=\s*(.+)", line)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return None


BASE = (env_value("PHAZE_API_BASE") or "https://public-api.phaze.app/enterprise/v1").rstrip("/")
KEY = None if "--offline" in sys.argv else env_value("PHAZE_API_KEY")
if KEY is None and "--offline" not in sys.argv:
    sys.exit("No PHAZE_API_KEY found. Set it in the environment or in a .env file next to fetch.py.")


def get(path, **params):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + KEY,
        "Accept": "application/json",
        "User-Agent": "phaze-usage-dashboard/1.0",
    })
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(e.headers.get("Retry-After", "5")) + 1)
                continue
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code == 404:
                raise NotFound(f"GET {path} -> 404: {body}")
            raise RuntimeError(f"GET {path} -> {e.code}: {body}")
    raise RuntimeError(f"GET {path}: rate limited")


def get_all(path, **params):
    out, offset = [], 0
    while True:
        page = get(path, limit=200, offset=offset, **params)
        out.extend(page.get("data") or [])
        offset += 200
        if offset >= page.get("count", 0) or not page.get("data"):
            return out


def locations_and_relays(oid, machines, enterprise):
    """Locations and relays for one org.

    The API moved both from /orgs/{id}/... to the enterprise level (/locations,
    /relays) in November 2026. Enterprise-level records carry no org_id, so an
    org gets the locations its machines sit in and the relays at those
    locations. Relays without a location are listed under the first org.
    Falls back to the old org-scoped routes if the enterprise ones are missing.
    """
    if enterprise is None:
        return get_all(f"/orgs/{oid}/locations"), get_all(f"/orgs/{oid}/relays")
    used = {m.get("location_id") for m in machines if m.get("location_id")}
    locs = [l for l in enterprise["locations"] if l["id"] in used]
    relays = [r for r in enterprise["relays"]
              if r.get("location_id") in used or (not r.get("location_id") and not enterprise["unlocated_taken"])]
    if any(not r.get("location_id") for r in relays):
        enterprise["unlocated_taken"] = True
    return locs, relays


def main():
    if "--offline" in sys.argv:
        raw = json.loads((HERE / "raw.json").read_text(encoding="utf-8"))
        (HERE / "data.json").write_text(json.dumps(pseudonymize(raw), separators=(",", ":")), encoding="utf-8")
        print("rebuilt data.json from raw.json")
        return
    snapshot = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    orgs = get_all("/orgs")
    try:
        enterprise = {"locations": get_all("/locations"), "relays": get_all("/relays"), "unlocated_taken": False}
    except NotFound:
        enterprise = None
    raw = {"snapshot_at": snapshot, "orgs": []}
    for o in orgs:
        oid = o["id"]
        conns = get_all(f"/orgs/{oid}/connections")
        if SKIP_EMPTY_ORGS and not conns:
            print(f"skip {o.get('name')!r}: no connections")
            continue
        machines = get_all(f"/orgs/{oid}/machines")
        locations, relays = locations_and_relays(oid, machines, enterprise)
        entry = {
            "org": o,
            "connections": conns,
            "machines": machines,
            "members": get_all(f"/orgs/{oid}/members"),
            "groups": get_all(f"/orgs/{oid}/groups"),
            "locations": locations,
            "relays": relays,
        }
        print(f"{o.get('name')!r}: {len(conns)} connections, {len(entry['machines'])} machines, "
              f"{len(entry['members'])} members, {len(entry['relays'])} relays")
        raw["orgs"].append(entry)
    (HERE / "raw.json").write_text(json.dumps(raw, indent=1), encoding="utf-8")
    (HERE / "data.json").write_text(json.dumps(pseudonymize(raw), separators=(",", ":")), encoding="utf-8")
    print("wrote raw.json and data.json")


def ts(s):
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()) if s else None


def pseudonymize(raw):
    """Replace people and machines with stable-per-build aliases, ranked by usage."""
    snap = ts(raw["snapshot_at"])
    # usage per accessor / machine to rank aliases (most active = 01)
    use_p, use_m = {}, {}
    for e in raw["orgs"]:
        for c in e["connections"]:
            st = ts(c.get("connected_at")) or ts(c.get("created_at"))
            en = ts(c.get("disconnected_at")) or ts(c.get("last_heartbeat_at")) or st
            d = max(0, en - st) if c.get("connected_at") else 0
            use_p[c["accessor_id"]] = use_p.get(c["accessor_id"], 0) + d
            use_m[c["machine_id"]] = use_m.get(c["machine_id"], 0) + d
        for m in e["machines"]:
            use_m.setdefault(m["id"], 0)
        for m in e["members"]:
            use_p.setdefault(m.get("user_id") or m.get("id"), 0)
    p_alias = {pid: f"Artist {i:02d}" for i, pid in enumerate(sorted(use_p, key=lambda k: -use_p[k]), 1)}
    m_alias = {mid: f"WS-{i:02d}" for i, mid in enumerate(sorted(use_m, key=lambda k: -use_m[k]), 1)}

    out = {"snapshot_at": raw["snapshot_at"], "orgs": [], "people": [], "machines": [],
           "relays": [], "sessions": []}
    out["people"] = [{"id": a, "name": a} for a in sorted(p_alias.values())]
    for oi, e in enumerate(raw["orgs"]):
        o = e["org"]
        groups = {g["id"]: f"Group {chr(65 + gi)}" for gi, g in enumerate(e["groups"])}
        locs = {l["id"]: f"Site {oi + 1}{chr(65 + li)}" for li, l in enumerate(e["locations"])}
        out["orgs"].append({
            "i": oi, "name": o.get("name"),
            "member_count": o.get("member_count"), "machine_count": o.get("machine_count"),
            "groups": len(e["groups"]), "locations": len(e["locations"]), "relays": len(e["relays"]),
            "members": sorted(({"name": p_alias[m.get("user_id") or m.get("id")], "role": m.get("role") or "member"}
                               for m in e["members"]), key=lambda x: x["name"]),
        })
        for m in e["machines"]:
            kind = "user" if m.get("assignee_id") else ("group" if m.get("group_id") else "unassigned")
            ch = m.get("channel") or "release"
            out["machines"].append({
                "id": m_alias[m["id"]], "org": oi, "online": bool(m.get("is_online")), "assign": kind,
                "group": groups.get(m.get("group_id")), "location": locs.get(m.get("location_id")),
                "os": (m.get("os") or "unknown").capitalize(),
                "version": (re.match(r"\d+\.\d+\.\d+", m.get("version") or "") or [None])[0],
                "channel": "release" if ch == "release" else "test build",
            })
        for r in e["relays"]:
            s = r.get("stats") or {}
            out["relays"].append({
                "org": oi, "name": f"relay-{len(out['relays']) + 1:02d}",
                "location": locs.get(r.get("location_id")), "online": bool(r.get("is_online")),
                "maintenance": bool(r.get("is_maintenance_mode_enabled")),
                "version": s.get("version"), "active": s.get("active_connections"),
                "client_bps": s.get("client_bits_per_second"), "host_bps": s.get("host_bits_per_second"),
                "uptime": s.get("uptime_seconds"), "cpu": s.get("cpu_busy_percent"),
                "mem": s.get("memory_percent"), "disk": s.get("disk_used_percent"),
                "reported_at": s.get("reported_at"),
            })
        for c in e["connections"]:
            who = p_alias.get(c["accessor_id"], "Artist ??")
            what = m_alias.get(c["machine_id"], "WS-??")
            if not c.get("connected_at"):
                # attempt that never connected: status 2
                t0 = ts(c.get("created_at")) or ts(c.get("last_heartbeat_at"))
                out["sessions"].append([oi, who, what, t0, t0, 2])
                continue
            st = ts(c["connected_at"])
            dis = ts(c.get("disconnected_at"))
            hb = ts(c.get("last_heartbeat_at"))
            active = dis is None and hb is not None and snap - hb < 180
            en = snap if active else (dis or hb or st)
            out["sessions"].append([oi, who, what, st, max(st, en), 1 if active else 0])
    out["sessions"].sort(key=lambda s: s[3])
    return out


if __name__ == "__main__":
    main()
