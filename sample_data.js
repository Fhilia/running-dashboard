/* sample_data.js  -  FAKE data for a made-up runner. Safe to share and to commit.
 *
 * Same structure as garmin_data.js (see the comment at the top of that file, or sync.py),
 * but stored in window.SAMPLE_DATA. dashboard.html shows it, with a "demo data" notice,
 * when garmin_data.js is missing.
 *
 * Instead of fixed dates (which would go stale), the 90 days are generated each time the page
 * loads, ending today. A "seeded" random generator makes the numbers the same on every load.
 * Nothing here comes from a real person.
 */
(function () {
  // --- tiny seeded random generator (same sequence every time) ---
  var seed = 20240601;
  function rand() {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  function noise(sd) { return (rand() + rand() + rand() - 1.5) * 2 * sd / 1.5 * 0.5; }  // roughly bell shaped
  function round(x, d) { var m = Math.pow(10, d || 0); return Math.round(x * m) / m; }
  function clamp(x, lo, hi) { return Math.max(lo, Math.min(hi, x)); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function iso(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function clock(minutes) { minutes = ((minutes % 1440) + 1440) % 1440; return pad(Math.floor(minutes / 60)) + ":" + pad(Math.round(minutes % 60)); }

  var DAYS = 90;
  var today = new Date(); today.setHours(12, 0, 0, 0);
  var dates = [];
  for (var i = DAYS - 1; i >= 0; i--) { var d = new Date(today); d.setDate(d.getDate() - i); dates.push(d); }

  // --- daily numbers ---
  var days = dates.map(function (d, idx) {
    var fromEnd = DAYS - 1 - idx;                      // 0 = today
    var hrv = round(63 + noise(5), 0);
    var rhr = round(52 + noise(1.6), 0);
    var score = round(clamp(79 + noise(7), 45, 98), 0);
    var bed = 23 * 60 + noise(35);
    var total = round(clamp(7.3 * 3600 + noise(2400), 4 * 3600, 10 * 3600), 0);
    var wake = bed + total / 60 + 25;
    var bbWake = round(clamp(62 + (score - 79) * 0.9 + noise(9), 12, 98), 0);
    var skipRow = (idx % 29 === 3);                    // a few gaps, like real life (watch not worn)
    return {
      date: iso(d),
      hrv: skipRow ? null : hrv,
      hrvBaseline: skipRow ? null : { low: 54, high: 71 },
      hrvStatus: skipRow ? null : (hrv >= 54 ? "BALANCED" : "UNBALANCED"),
      restingHR: rhr,
      sleep: skipRow ? null : {
        score: score,
        totalSec: total,
        deepSec: round(total * 0.18, 0),
        lightSec: round(total * 0.55, 0),
        remSec: round(total * 0.22, 0),
        awakeSec: round(total * 0.05, 0),
        bedtime: clock(bed),
        wakeTime: clock(wake)
      },
      bodyBatteryWake: skipRow ? null : bbWake,
      bodyBatteryMax: skipRow ? null : clamp(bbWake + 3, 0, 100),
      vo2Max: (idx % 4 === 0) ? round(48.4 + idx * 0.018, 1) : null,   // only on "updated" days
      _fromEnd: fromEnd
    };
  });

  // --- activities: a simple weekly rhythm (see below), with a gentle build over the 90 days ---
  var activities = [];
  var nextId = 9000000001;
  function addRun(day, kind, km, pace, hr, treadmill, noSplits) {
    var distanceM = round(km * 1000 + noise(60), 0);
    var durationSec = round(distanceM / 1000 * pace, 1);
    var start = day.date + " " + (kind === "long" ? "08:15:00" : "18:10:00");
    var splits = null;
    if (!noSplits) {
      splits = [];
      var whole = Math.floor(distanceM / 1000);
      for (var k = 1; k <= whole; k++) {
        var fade = 1 + (kind === "tempo" ? 0.004 : 0.012) * (k / whole);        // slows a little over the run
        splits.push({ km: k, distM: 1000, durSec: round(pace * fade + noise(3), 1),
                      avgHR: round(hr - 4 + 8 * (k / whole) + noise(1.5), 0) });  // heart rate drifts up
      }
      var rest = distanceM - whole * 1000;
      if (rest >= 100) splits.push({ km: whole + 1, distM: round(rest, 0), durSec: round(rest / 1000 * pace, 1), avgHR: round(hr + 4, 0) });
    }
    var hours = durationSec / 3600;
    var z = kind === "tempo" ? [120, 360, 900, 1200, 120] : kind === "long" ? [200, 3300, 1800, 300, 0] : [400, 2400, 700, 0, 0];
    var scale = durationSec / z.reduce(function (a, b) { return a + b; }, 0);
    activities.push({
      id: nextId++, date: day.date, startLocal: start,
      type: treadmill ? "treadmill_running" : "running", isRun: true,
      distanceM: distanceM, durationSec: durationSec,
      avgHR: round(hr, 0), maxHR: round(hr + 14, 0), avgSpeedMps: round(1000 / pace, 3),
      elevationGainM: treadmill ? 0 : round(20 + km * 6 + noise(10), 0), cadence: round(166 + (kind === "tempo" ? 8 : 0) + noise(2), 0),
      trainingLoad: noSplits ? null : round(hours * (kind === "tempo" ? 150 : kind === "long" ? 105 : 65) + noise(5), 1),
      trainingEffect: round(kind === "tempo" ? 3.6 + noise(0.3) : kind === "long" ? 3.1 + noise(0.2) : 2.4 + noise(0.2), 1),
      hrZoneSec: z.map(function (s) { return round(s * scale, 0); }),
      splits: splits
    });
  }
  function addGym(day) {
    var dur = round(2700 + noise(500), 1);
    activities.push({ id: nextId++, date: day.date, startLocal: day.date + " 07:00:00", type: "strength_training", isRun: false,
      distanceM: null, durationSec: dur, avgHR: round(112 + noise(5), 0), maxHR: round(146 + noise(6), 0), avgSpeedMps: null,
      elevationGainM: null, cadence: null, trainingLoad: round(dur / 3600 * 45, 1), trainingEffect: 1.8, hrZoneSec: [900, 1300, 400, 0, 0], splits: null });
  }
  days.forEach(function (day, idx) {
    var dow = new Date(day.date + "T12:00:00").getDay();   // 0 = Sunday
    var week = Math.floor(idx / 7);                         // grows slowly: gentle build
    if (day._fromEnd === 0) return;                         // today: not run yet
    // Matches the 5 days a week plan: Mon easy, Tue gym, Wed tempo, Fri easy, Sun long (Thu and Sat rest)
    if (dow === 1) addRun(day, "easy", 6 + week * 0.1, 355 + noise(8), 142 + noise(3), false, false);
    if (dow === 2) addGym(day);
    if (dow === 3) addRun(day, "tempo", 8 + week * 0.1, 318 + noise(5), 164 + noise(3), false, false);
    if (dow === 5) addRun(day, "easy", 5 + week * 0.1, 360 + noise(8), 141 + noise(3), idx % 3 === 0, week === 5);  // one run without splits
    if (dow === 0) addRun(day, "long", 12 + Math.min(week, 6) * 0.6, 352 + noise(6), 149 + noise(3), false, false);
  });

  days.forEach(function (day) { delete day._fromEnd; });

  window.SAMPLE_DATA = {
    schemaVersion: 1,
    lastSynced: new Date().toISOString().slice(0, 19) + "Z",
    range: { from: days[0].date, to: days[days.length - 1].date },
    profile: { measurementSystem: "metric", firstDayOfWeek: 2 },
    heartRateZones: { sport: "RUNNING", restingHR: 52, maxHR: 188, lactateThresholdHR: 168, zoneFloors: [96, 114, 132, 151, 170] },
    days: days,
    activities: activities,
    cycle: { enabled: false }
  };
})();
