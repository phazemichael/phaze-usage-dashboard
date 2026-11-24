"""Generate sample_data.json: a synthetic studio in the same shape as data.json.

Lets the dashboard build and run without an API key or real usage data.
Deterministic (fixed seed), so re-running gives the same file.

Usage: python make_sample.py
"""
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
rnd = random.Random(42)

SNAPSHOT = datetime(2026, 11, 3, 13, 30, tzinfo=timezone.utc)
DAYS = 140
CET = timedelta(hours=1)

ORGS = [
    # name, artists, machines, relays, locations
    ("Studio North", 14, 18, 2, 2),
    ("Studio South", 8, 10, 1, 1),
    ("Remote Contractors", 5, 6, 0, 0),
]


def iso(dt):
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main():
    snap_ts = int(SNAPSHOT.timestamp())
    people, machines, relays, sessions, orgs = [], [], [], [], []
    artist_n = machine_n = relay_n = 0

    for oi, (name, n_art, n_mach, n_rel, n_loc) in enumerate(ORGS):
        locs = [f"Site {oi + 1}{chr(65 + i)}" for i in range(n_loc)]
        groups = ["Group A", "Group B"] if n_mach >= 10 else []
        members = []
        org_artists = []
        for k in range(n_art):
            artist_n += 1
            a = f"Artist {artist_n:02d}"
            org_artists.append(a)
            members.append({"name": a, "role": "admin" if k == 0 else "member"})
            people.append({"id": a, "name": a})
        org_machines = []
        for k in range(n_mach):
            machine_n += 1
            mid = f"WS-{machine_n:02d}"
            org_machines.append(mid)
            assign = "user" if k < n_art * 0.8 else ("group" if groups and k % 3 == 0 else "unassigned")
            machines.append({
                "id": mid, "org": oi, "online": rnd.random() < 0.7,
                "assign": assign, "group": groups[k % len(groups)] if assign == "group" else None,
                "location": locs[k % len(locs)] if locs else None,
                "os": "Linux" if rnd.random() < 0.15 else "Windows",
                "version": rnd.choice(["0.14.3", "0.14.3", "0.14.3", "0.14.0", "0.13.0", "0.11.0"]),
                "channel": "test build" if rnd.random() < 0.05 else "release",
            })
        for k in range(n_rel):
            relay_n += 1
            online = k == 0 or rnd.random() < 0.6
            relays.append({
                "org": oi, "name": f"relay-{relay_n:02d}", "location": locs[k % len(locs)] if locs else None,
                "online": online, "maintenance": False,
                "version": "v0.1.5" if online else None,
                "active": rnd.randint(0, 3) if online else None,
                "client_bps": rnd.randint(0, 40_000_000) if online else None,
                "host_bps": rnd.randint(0, 2_000_000) if online else None,
                "uptime": rnd.randint(86_400, 2_000_000) if online else None,
                "cpu": round(rnd.uniform(0.5, 18), 2) if online else None,
                "mem": round(rnd.uniform(15, 45), 2) if online else None,
                "disk": round(rnd.uniform(20, 60), 2) if online else None,
                "reported_at": iso(SNAPSHOT - timedelta(minutes=rnd.randint(1, 30))) if online else None,
            })
        orgs.append({
            "i": oi, "name": name, "member_count": n_art, "machine_count": n_mach,
            "groups": len(groups), "locations": n_loc, "relays": n_rel, "members": members,
        })

        # A few machines that had sessions but are no longer enrolled ("removed").
        retired = [f"WS-{90 + oi * 3 + j:02d}" for j in range(2)]

        # Each artist has a home machine and a working pattern.
        for idx, a in enumerate(org_artists):
            home = org_machines[idx % len(org_machines)]
            heavy = rnd.random() < 0.3
            start_day = rnd.randint(0, 40) if idx > 2 else 0
            for d in range(start_day, DAYS):
                day = (SNAPSHOT - timedelta(days=DAYS - d)).replace(hour=0, minute=0, second=0)
                weekday = (day + CET).weekday()
                p = (0.85 if heavy else 0.55) if weekday < 5 else 0.08
                if rnd.random() > p:
                    continue
                n_sess = 1 + (rnd.random() < 0.35) + (rnd.random() < 0.1)
                t = day + timedelta(hours=rnd.gauss(8.5, 1.2), minutes=rnd.randint(0, 59))
                for _ in range(n_sess):
                    machine = home if rnd.random() < 0.8 else rnd.choice(org_machines + retired)
                    if d < 60 and rnd.random() < 0.05:
                        machine = rnd.choice(retired)
                    st = int(t.timestamp())
                    if rnd.random() < 0.03:  # attempt that never connected
                        sessions.append([oi, a, machine, st, st, 2])
                        t += timedelta(minutes=2)
                        continue
                    if rnd.random() < 0.25:  # quick check-in
                        dur = rnd.randint(20, 600)
                    else:
                        dur = int(min(10, max(0.3, rnd.lognormvariate(math.log(2.6), 0.6))) * 3600)
                    if rnd.random() < 0.012:  # forgot to disconnect
                        dur = rnd.randint(10, 60) * 3600
                    en = st + dur
                    if en >= snap_ts:
                        continue
                    sessions.append([oi, a, machine, st, en, 0])
                    t = datetime.fromtimestamp(en, timezone.utc) + timedelta(minutes=rnd.randint(10, 90))

        # Two sessions that are live right now.
        for a in org_artists[:1 if oi else 2]:
            st = snap_ts - rnd.randint(1800, 10800)
            sessions.append([oi, a, org_machines[org_artists.index(a)], st, snap_ts, 1])

    sessions.sort(key=lambda s: s[3])
    out = {"snapshot_at": iso(SNAPSHOT), "orgs": orgs, "people": people,
           "machines": machines, "relays": relays, "sessions": sessions}
    path = HERE / "sample_data.json"
    path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {path.name}: {len(orgs)} orgs, {len(people)} people, {len(machines)} machines, "
          f"{len(sessions)} sessions")


if __name__ == "__main__":
    main()
