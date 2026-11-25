#!/usr/bin/env python3
"""
sync.py  (STEP 3: pulls the last 90 days and writes garmin_data.js)

What it does:
  1. Reads GARMIN_API_KEY (and optional INCLUDE_CYCLE) from the .env file.
  2. Swaps the key for a short-lived access token (never printed).
  3. Downloads 90 days of runs, HRV, sleep, body battery, resting heart rate,
     plus heart rate zones and profile settings.
  4. Writes garmin_data.js, which dashboard.html loads with a script tag.
  5. Prints only COUNTS, never your health numbers.

Uses only Python's standard library, so nothing needs installing.
"""

import base64
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ---- Settings ---------------------------------------------------------------
BASE_URL = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
DAYS = 90            # how much history to pull
CHUNK_DAYS = 28      # long date ranges are requested in pieces of this size
PAUSE = 0.4          # seconds to wait between calls, to be gentle with Garmin
HERE = Path(__file__).resolve().parent   # the folder this file lives in
OUTPUT = HERE / "garmin_data.js"
SECRETS = []         # anything we must never print; filled in once we know it


# ---- Small helpers ----------------------------------------------------------
def scrub(text):
    """Replace any secret (key or token) in a piece of text with ****."""
    text = str(text)
    for s in SECRETS:
        if s:
            text = text.replace(s, "****")
    return text


class SyncError(Exception):
    """A problem we can explain to the user in plain words."""


def read_env_file(path):
    """Read KEY=value lines from .env into a dictionary."""
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def http(method, url, headers, retries=3):
    """Make one request. Returns (status, body_text). Retries on rate limits."""
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as err:
            status, body = err.code, err.read().decode("utf-8", "replace")
            if status == 429 and attempt < retries:      # too many requests: wait, retry
                time.sleep(5 * (attempt + 1))
                continue
            return status, body
        except urllib.error.URLError as err:
            raise SyncError("Could not reach Garmin (" + scrub(err.reason) + "). "
                            "Check your internet connection and try again.")
    return 429, ""


def explain_status(status):
    """Turn an HTTP status code into a friendly hint."""
    if status in (401, 403):
        return ("Garmin refused the key or token. It may be wrong, expired or revoked. "
                "Make a new key on the Garmin Personal API page and put it in .env.")
    if status == 429:
        return "Garmin says too many requests. Wait a few minutes and run sync.py again."
    if status >= 500:
        return "Garmin's servers had a problem. Try again later."
    return "Garmin answered with an unexpected error (HTTP %d)." % status


class Garmin:
    """Tiny client: gets a token once, then makes GET requests that return JSON."""

    def __init__(self, key):
        status, body = http("POST", BASE_URL + TOKEN_PATH,
                            {"Authorization": "ApiKey " + key, "Accept": "*/*"})
        if status != 200:
            raise SyncError(explain_status(status))
        token = body.strip()
        try:                                   # in case Garmin ever switches to JSON
            parsed = json.loads(token)
            token = parsed.get("access_token") or parsed.get("accessToken") or ""
        except (json.JSONDecodeError, AttributeError):
            pass                               # today it is plain text: the token itself
        if not token:
            raise SyncError("Garmin's answer did not contain a token.")
        SECRETS.append(token)
        self.headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
        self.calls = 0

    def get(self, path, params=None, optional=False):
        """GET a path. Returns parsed JSON. If optional, a failure returns None."""
        url = BASE_URL + path + ("?" + urllib.parse.urlencode(params) if params else "")
        time.sleep(PAUSE)
        self.calls += 1
        status, body = http("GET", url, self.headers)
        if status == 200:
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                pass
        if optional and status not in (401, 403, 429):
            return None
        if status == 200:
            raise SyncError("Garmin sent something that is not JSON.")
        raise SyncError(explain_status(status))


def day_chunks(start, end):
    """Split start..end (dates) into pieces of CHUNK_DAYS days: [(from, to), ...]."""
    pieces = []
    cur = start
    while cur <= end:
        stop = min(cur + dt.timedelta(days=CHUNK_DAYS - 1), end)
        pieces.append((cur.isoformat(), stop.isoformat()))
        cur = stop + dt.timedelta(days=1)
    return pieces


def clock(local_ms):
    """Turn a 'local time as milliseconds' stamp into 'HH:MM'."""
    if not local_ms:
        return None
    return dt.datetime.fromtimestamp(local_ms / 1000, dt.timezone.utc).strftime("%H:%M")


def num(value, digits=1):
    """Round a number, keeping None as None."""
    return None if value is None else round(value, digits)


# ---- Fetching one kind of data each -----------------------------------------
def fetch_hrv(g, start, end):
    out = {}
    for a, b in day_chunks(start, end):
        data = g.get(f"/hrv-service/hrv/daily/{a}/{b}", optional=True) or {}
        for row in data.get("hrvSummaries", []):
            out[row["calendarDate"]] = row
    return out


def fetch_sleep(g, start, end):
    out = {}
    for a, b in day_chunks(start, end):
        rows = g.get("/sleep-service/sleep/dailySleepSummariesByDate",
                     {"startDate": a, "endDate": b}, optional=True) or []
        for row in rows:
            out[row["calendarDate"]] = row
    return out


def fetch_body_battery(g, start, end):
    out = {}
    for a, b in day_chunks(start, end):
        rows = g.get("/wellness-service/wellness/bodyBattery/reports/daily",
                     {"startDate": a, "endDate": b}, optional=True) or []
        for row in rows:
            out[row["date"]] = row
    return out


def fetch_daily_summaries(g, start, end):
    out = {}
    for a, b in day_chunks(start, end):
        data = g.get("/usersummary-service/v2/dailysummaries",
                     {"startDate": a, "endDate": b}, optional=True) or {}
        for row in data.get("data", []):
            out[row["calendarDate"]] = row
    return out


def fetch_vo2(g, start, end):
    """VO2 max values by date. Garmin only lists days when the value was updated.
    Not in the official endpoint list, so a failure just means 'no VO2 max' (never a crash)."""
    out = {}
    try:
        for a, b in day_chunks(start, end):
            rows = g.get(f"/metrics-service/metrics/maxmet/daily/{a}/{b}", optional=True) or []
            for row in rows:
                generic = (row or {}).get("generic") or {}
                value = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
                if generic.get("calendarDate") and value:
                    out[generic["calendarDate"]] = round(value, 1)
    except SyncError:
        pass            # e.g. rate limit: carry on without VO2 max
    return out


def body_battery_at_wake(bb_row, sleep_row):
    """Body battery level closest to wake-up time (within 1.5 hours), else None.
    Garmin gives a short list of [timestamp_ms, level] points for the day."""
    if not bb_row or not sleep_row or not sleep_row.get("sleepEndTimestampGMT"):
        return None
    wake = sleep_row["sleepEndTimestampGMT"]
    points = [p for p in bb_row.get("bodyBatteryValuesArray", []) if p[1] is not None]
    if not points:
        return None
    best = min(points, key=lambda p: abs(p[0] - wake))
    return best[1] if abs(best[0] - wake) <= 1.5 * 3600 * 1000 else None


def build_days(start, end, hrv, sleep, bb, summaries, vo2):
    """One entry per calendar day, with None where Garmin had nothing."""
    days = []
    cur = start
    while cur <= end:
        d = cur.isoformat()
        h, s, b, u = hrv.get(d), sleep.get(d), bb.get(d), summaries.get(d)
        base = (h or {}).get("baseline") or {}
        scores = (s or {}).get("sleepScores") or {}
        days.append({
            "date": d,
            "hrv": (h or {}).get("lastNightAvg"),             # ms, last night's average
            "hrvBaseline": ({"low": base.get("balancedLow"),   # Garmin's own normal range
                             "high": base.get("balancedUpper")} if base else None),
            "hrvStatus": (h or {}).get("status"),
            "restingHR": ((u or {}).get("heartRate") or {}).get("restingValue"),  # bpm
            "sleep": None if not s else {
                "score": (scores.get("overall") or {}).get("value"),   # 0-100
                "totalSec": s.get("sleepTimeSeconds"),
                "deepSec": s.get("deepSleepSeconds"),
                "lightSec": s.get("lightSleepSeconds"),
                "remSec": s.get("remSleepSeconds"),
                "awakeSec": s.get("awakeSleepSeconds"),
                "bedtime": clock(s.get("sleepStartTimestampLocal")),   # "HH:MM"
                "wakeTime": clock(s.get("sleepEndTimestampLocal")),
            },
            "bodyBatteryWake": body_battery_at_wake(b, s),   # 0-100 at wake-up
            "bodyBatteryMax": ((u or {}).get("bodyBattery") or {}).get("maxValue"),
            "vo2Max": vo2.get(d),   # only on days Garmin updated it; the dashboard uses the latest one
        })
        cur += dt.timedelta(days=1)
    return days


def make_km_splits(g, activity_id, summary_distance, summary_duration):
    """Per-kilometre splits for a run, built from Garmin's second-by-second data.
    Returns [{km, distM, durSec, avgHR}] or None if the data is missing.
    This endpoint is not in Garmin's official list, so ANY problem here just
    means 'no splits for this run': it must never stop the whole sync."""
    try:
        return _make_km_splits(g, activity_id, summary_distance, summary_duration)
    except Exception:       # network, rate limit, unexpected shape... all handled the same way
        return None


def _make_km_splits(g, activity_id, summary_distance, summary_duration):
    data = g.get(f"/activity-service/activity/{activity_id}/details",
                 {"maxChartSize": 2000}, optional=True)
    if not data or not data.get("activityDetailMetrics"):
        return None
    idx = {m["key"]: m["metricsIndex"] for m in data["metricDescriptors"]}
    if "sumDistance" not in idx or "sumDuration" not in idx:
        return None
    samples = []
    for row in data["activityDetailMetrics"]:
        m = row["metrics"]
        dist, secs = m[idx["sumDistance"]], m[idx["sumDuration"]]
        hr = m[idx["directHeartRate"]] if "directHeartRate" in idx else None
        if dist is not None and secs is not None:
            samples.append((dist, secs, hr))
    if len(samples) < 2 or samples[-1][0] <= 0 or samples[-1][1] <= 0:
        return None
    # Units differ between fields, so scale both to match the activity summary.
    ds = summary_distance / samples[-1][0]
    ts = summary_duration / samples[-1][1]
    pts = [(d * ds, t * ts, hr) for d, t, hr in samples]

    splits, next_km, last_t, last_d, hrs, prev = [], 1000.0, 0.0, 0.0, [], pts[0]
    for d, t, hr in pts[1:]:
        if hr:
            hrs.append(hr)
        while d >= next_km:       # crossed a kilometre line: interpolate the exact time
            frac = (next_km - prev[0]) / (d - prev[0]) if d > prev[0] else 0
            t_at = prev[1] + frac * (t - prev[1])
            splits.append({"km": len(splits) + 1, "distM": 1000, "durSec": round(t_at - last_t, 1),
                           "avgHR": round(sum(hrs) / len(hrs)) if hrs else None})
            last_t, last_d, hrs, next_km = t_at, next_km, [], next_km + 1000.0
        prev = (d, t, hr)
    rest = pts[-1][0] - last_d
    if rest >= 100:               # keep a final partial km if it is at least 100 m
        splits.append({"km": len(splits) + 1, "distM": round(rest), "durSec": round(pts[-1][1] - last_t, 1),
                       "avgHR": round(sum(hrs) / len(hrs)) if hrs else None})
    return splits


def fetch_activities(g, start, end):
    """All activities in the range. Runs also get per-km splits."""
    raw, offset = [], 0
    while True:
        page = g.get("/activitylist-service/activities/search/activities",
                     {"start": offset, "limit": 100, "startDate": start.isoformat(),
                      "endDate": end.isoformat()}) or []
        raw += page
        if len(page) < 100:
            break
        offset += 100

    activities = []
    for a in sorted(raw, key=lambda x: x["startTimeLocal"]):
        kind = (a.get("activityType") or {}).get("typeKey", "other")
        is_run = "run" in kind
        item = {
            "id": a["activityId"],
            "date": a["startTimeLocal"][:10],
            "startLocal": a["startTimeLocal"],
            "type": kind,                                   # e.g. running, strength_training
            "isRun": is_run,
            "distanceM": num(a.get("distance"), 1),
            "durationSec": num(a.get("duration"), 1),
            "avgHR": num(a.get("averageHR"), 0),
            "maxHR": num(a.get("maxHR"), 0),
            "avgSpeedMps": num(a.get("averageSpeed"), 3),   # metres per second
            "elevationGainM": num(a.get("elevationGain"), 0),
            "cadence": num(a.get("averageRunningCadenceInStepsPerMinute"), 0),
            "trainingLoad": num(a.get("activityTrainingLoad"), 1),   # Garmin's own value, or None
            "trainingEffect": num(a.get("aerobicTrainingEffect"), 1),
            "hrZoneSec": [num(a.get(f"hrTimeInZone_{i}"), 0) for i in range(1, 6)],
            "splits": None,
        }
        if is_run and item["distanceM"] and item["durationSec"]:
            item["splits"] = make_km_splits(g, a["activityId"], item["distanceM"], item["durationSec"])
        activities.append(item)
    return activities


def fetch_zones(g):
    """Heart rate zones, preferring the running entry."""
    rows = g.get("/biometric-service/heartRateZones/v2", optional=True) or []
    if not rows:
        return None
    row = next((r for r in rows if str(r.get("sport", "")).upper() == "RUNNING"), None)
    row = row or next((r for r in rows if str(r.get("sport", "")).upper() == "DEFAULT"), rows[0])
    return {
        "sport": row.get("sport"),
        "restingHR": row.get("restingHeartRateUsed"),
        "maxHR": row.get("maxHeartRateUsed"),
        "lactateThresholdHR": row.get("lactateThresholdHeartRateUsed"),
        "zoneFloors": [row.get(f"zone{i}Floor") for i in range(1, 6)],   # lowest bpm of zones 1-5
    }


def fetch_profile(g):
    """Only the harmless settings the dashboard needs (no name, no email)."""
    p = g.get("/userprofile-service/userprofile/settings", optional=True) or {}
    return {
        "measurementSystem": p.get("measurementSystem"),                # e.g. metric
        "firstDayOfWeek": (p.get("firstDayOfWeek") or {}).get("dayId"),  # Garmin's day id
    }


def fetch_cycle(g, today):
    """Opt-in only (INCLUDE_CYCLE=true). Stores Garmin's summary for today as it is;
    it will be mapped to a cleaner structure once we have seen the real response."""
    raw = g.get(f"/periodichealth-service/menstrualcycle/summary/{today.isoformat()}", optional=True)
    return {"enabled": True, "raw": raw}


# ---- Writing the output file ------------------------------------------------
HEADER = """/* garmin_data.js  -  written by sync.py. PRIVATE: contains your real health data, never commit it.
 *
 * window.GARMIN_DATA = {
 *   schemaVersion : 1,
 *   lastSynced    : ISO timestamp (UTC),
 *   range         : { from: "YYYY-MM-DD", to: "YYYY-MM-DD" },
 *   profile       : { measurementSystem, firstDayOfWeek },
 *   heartRateZones: { sport, restingHR, maxHR, lactateThresholdHR, zoneFloors: [z1..z5 lowest bpm] },
 *   days: [ one per calendar day, oldest first; None (null) when Garmin had no data
 *     { date, hrv (ms), hrvBaseline {low, high} | null, hrvStatus, restingHR (bpm),
 *       sleep { score 0-100, totalSec, deepSec, lightSec, remSec, awakeSec, bedtime "HH:MM", wakeTime "HH:MM" } | null,
 *       bodyBatteryWake (0-100), bodyBatteryMax,
 *       vo2Max (number on days Garmin updated it, otherwise null; may be null everywhere) } ],
 *   activities: [ oldest first, every activity type
 *     { id, date, startLocal, type, isRun, distanceM, durationSec, avgHR, maxHR, avgSpeedMps,
 *       elevationGainM, cadence, trainingLoad (Garmin's value or null), trainingEffect,
 *       hrZoneSec [5 numbers], splits: [{ km, distM, durSec, avgHR }] | null } ],
 *   cycle: { enabled: false } or { enabled: true, raw: ... }   (only when INCLUDE_CYCLE=true)
 * };
 */
"""


def write_output(data):
    text = HEADER + "window.GARMIN_DATA = " + json.dumps(data, indent=1) + ";\n"
    OUTPUT.write_text(text, encoding="utf-8")


# ---- Main -------------------------------------------------------------------
def main():
    env = read_env_file(HERE / ".env")
    key = env.get("GARMIN_API_KEY", "")
    if not key or key == "your_key_here":
        raise SyncError("No GARMIN_API_KEY found in .env. Copy .env.example to .env and paste your key.")
    SECRETS.append(key)
    include_cycle = env.get("INCLUDE_CYCLE", "false").lower() == "true"

    today = dt.date.today()
    start = today - dt.timedelta(days=DAYS - 1)

    print("Connecting to Garmin ...")
    g = Garmin(key)

    print("Downloading HRV, sleep, body battery, resting heart rate ...")
    vo2 = fetch_vo2(g, start, today)
    hrv = fetch_hrv(g, start, today)
    sleep = fetch_sleep(g, start, today)
    bb = fetch_body_battery(g, start, today)
    summaries = fetch_daily_summaries(g, start, today)
    days = build_days(start, today, hrv, sleep, bb, summaries, vo2)

    print("Downloading activities (this takes a minute) ...")
    activities = fetch_activities(g, start, today)

    print("Downloading heart rate zones and settings ...")
    zones = fetch_zones(g)
    profile = fetch_profile(g)
    cycle = fetch_cycle(g, today) if include_cycle else {"enabled": False}

    data = {
        "schemaVersion": 1,
        "lastSynced": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "range": {"from": start.isoformat(), "to": today.isoformat()},
        "profile": profile,
        "heartRateZones": zones,
        "days": days,
        "activities": activities,
        "cycle": cycle,
    }

    if not any(d["hrv"] or d["sleep"] or d["restingHR"] for d in days) and not activities:
        raise SyncError("Garmin returned no data for the last %d days. Has your watch synced "
                        "to the Garmin Connect app recently?" % DAYS)

    write_output(data)

    # Counts only, never values.
    runs = [a for a in activities if a["isRun"]]
    print("\nDone. Wrote garmin_data.js (%d API calls)." % g.calls)
    print(f"  Days covered         : {len(days)}  ({start} to {today})")
    print(f"  Days with HRV        : {sum(1 for d in days if d['hrv'] is not None)}")
    print(f"  Days with HRV range  : {sum(1 for d in days if d['hrvBaseline'])}")
    print(f"  Days with resting HR : {sum(1 for d in days if d['restingHR'] is not None)}")
    print(f"  Days with sleep      : {sum(1 for d in days if d['sleep'])}")
    print(f"  Days with body batt. : {sum(1 for d in days if d['bodyBatteryWake'] is not None)}")
    print(f"  Activities           : {len(activities)}  (runs: {len(runs)}, runs with km splits: "
          f"{sum(1 for a in runs if a['splits'])})")
    print(f"  Days with VO2 max    : {sum(1 for d in days if d['vo2Max'] is not None)}")
    if runs and not all(a["splits"] for a in runs):
        print(f"  Note: {sum(1 for a in runs if not a['splits'])} run(s) have no km splits; "
              "the dashboard will show pace and heart rate only for those.")
    print(f"  Runs with Garmin load: {sum(1 for a in runs if a['trainingLoad'] is not None)}")
    print(f"  Heart rate zones     : {'yes' if zones else 'no'}")
    print(f"  Cycle data           : {'included' if include_cycle else 'off (INCLUDE_CYCLE is not true)'}")


if __name__ == "__main__":
    try:
        main()
    except SyncError as err:
        print("\nProblem: " + scrub(err))
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(1)
