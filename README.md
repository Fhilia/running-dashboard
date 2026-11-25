# Running Dashboard

A personal dashboard that turns your own Garmin data (runs, HRV, sleep, resting heart rate,
body battery) into one calm page: how ready you are today, a weekly plan, training load,
a race-time estimate, per-run feedback and sleep trends.

- Runs on your own computer. Nothing is uploaded anywhere.
- Python 3 standard library only. Nothing to install, no build step.
- Each person uses **their own** Garmin key on **their own** machine.

> Estimates and suggestions are guides, not medical advice.

This is an unofficial project and is not affiliated with, endorsed by or sponsored by Garmin.
"Garmin" and "Garmin Connect" are trademarks of their owners.

## Quick start (4 steps)

### 1. Make a Garmin Personal API key
1. Log in to Garmin Connect on the web.
2. Open the **Personal API Key** page.
3. Select **Create Key**.
4. Accept the terms.
5. Choose an expiry period (30, 90, 180 or 365 days).
6. Select **Create**.
7. Copy the key. **It is shown only once**, so copy it before you leave the page.
8. Put it in `.env` as `GARMIN_API_KEY` (step 2 below).

Keep the key private. When it expires, make a new one and replace it in `.env`.

### 2. Create your `.env` file
Open a terminal in this folder and run:

```bash
cp .env.example .env
```

`cp` copies a file. This makes a copy called `.env` that only you will edit.
Open `.env` in any text editor and replace `your_key_here` with your key:

```
GARMIN_API_KEY=paste_your_key_here
INCLUDE_CYCLE=false
```

- Do not add quotes or spaces around the key.
- `.env` is listed in `.gitignore`, so git will never include it. Never share it.
- Cycle tracking is opt in. Leave `INCLUDE_CYCLE=false` unless you want it.

### 3. Download your data

```bash
python3 sync.py
```

`python3` runs Python, and `sync.py` is the script. It trades your key for a short-lived
token, downloads the last 90 days and writes `garmin_data.js`. It prints only counts
(for example "51 activities"), never your health numbers. Run it again any time to refresh.

### 4. Open the dashboard
Double-click `dashboard.html`. It opens in your browser. There is nothing to start or install.
The first time, a setup screen asks for your race distance, race date, goal time and how many
days a week you train. Your choices are saved in your browser only.

## Demo mode
Add `?demo` to the end of the page address (for example `.../dashboard.html?demo`) to see
made-up data from `sample_data.js` instead of yours, with a clear "Demo data" notice.
Use this for screenshots. If `garmin_data.js` does not exist, the dashboard falls back
to demo data on its own.

## Putting a demo on GitHub Pages (optional)
GitHub Pages can host `dashboard.html` as a public web page. Because `garmin_data.js` is never
uploaded, the hosted page shows only the **demo data** with the "Demo data" notice. That is
what you want for a public demo: **your real health data never goes online.**

1. Push the project to GitHub.
2. Open the repository on github.com, then **Settings**, then **Pages**.
3. Under **Build and deployment**, set **Source** to **Deploy from a branch**.
4. Choose branch **main** and folder **/ (root)**, then select **Save**.
5. After a minute or two, GitHub shows the address, usually
   `https://YOUR-USERNAME.github.io/running-dashboard/dashboard.html`.

Notes:
- A Pages site is public, even if the repository is private (Pages from a private repository
  needs a paid GitHub plan). Only turn it on if you are happy for anyone to see the demo.
- To use the dashboard with your own data, open `dashboard.html` from your own computer, not the hosted page.
- Never remove `garmin_data.js` from `.gitignore`.

## Privacy
- `garmin_data.js` holds your real health data. It is listed in `.gitignore`. **Never commit it.**
- `.env` holds your key. It is also in `.gitignore`.
- Before any `git commit`, run `git status` and check that neither `.env` nor `garmin_data.js` appears.
- The only network request the page makes is for the Figtree font from Google Fonts.
  Everything else stays on your machine.

## Update it every morning (Mac)
You can have your Mac run `sync.py` for you each morning using `launchd`, the Mac's built-in scheduler.

**a) Find two paths.** In a terminal:

```bash
which python3
```

This prints where Python lives, for example `/usr/bin/python3`. Then, from this folder:

```bash
pwd
```

This prints the full path of the current folder. Note both.

**b) Create the schedule file.** Open a text editor and save the text below as
`~/Library/LaunchAgents/local.running-dashboard.plist`. Replace `PYTHON_PATH` and `FOLDER_PATH`
with what you found above (type full paths, `~` does not work inside this file).

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>local.running-dashboard</string>
  <key>ProgramArguments</key>
  <array>
    <string>PYTHON_PATH</string>
    <string>FOLDER_PATH/sync.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>FOLDER_PATH</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>7</integer>
    <key>Minute</key>
    <integer>30</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/tmp/running-dashboard.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/running-dashboard.log</string>
</dict>
</plist>
```

What the parts mean: `ProgramArguments` is the command to run (Python, then the script).
`StartCalendarInterval` is the time (7:30 every day; change `Hour` and `Minute` as you like).
The last two lines save any messages to a log file. Messages never contain your key
(or health numbers), because `sync.py` hides them.

**c) Switch it on:**

```bash
launchctl load ~/Library/LaunchAgents/local.running-dashboard.plist
```

`launchctl` is the control tool for the scheduler and `load` registers your file.

To test it right now instead of waiting for 7:30:

```bash
launchctl start local.running-dashboard
```

To switch it off:

```bash
launchctl unload ~/Library/LaunchAgents/local.running-dashboard.plist
```

Notes: if your Mac is asleep at 7:30, the job runs when it wakes. Your watch must have synced
to the Garmin Connect app on your phone first, otherwise the newest night is not there yet.
Check `/tmp/running-dashboard.log` if something looks stale.

## Troubleshooting
- **"No GARMIN_API_KEY found"**: `.env` is missing or the line is misspelled. Redo step 2.
- **A message about the key being rejected or expired**: make a new key and replace it in `.env`.
- **"Garmin returned no data"**: open the Garmin Connect app so your watch syncs, then run `python3 sync.py` again.
- **The page says "Demo data"** although you synced: check that `garmin_data.js` sits next to
  `dashboard.html`, and that the address does not end in `?demo`.
- **Today's readiness looks old**: the latest HRV and sleep arrive after the watch syncs. Sync the watch, then run `python3 sync.py` again.
- **Too many requests (429)**: wait a few minutes and run it again.

## Files
| File | What it is |
|---|---|
| `sync.py` | Talks to Garmin and writes `garmin_data.js` |
| `dashboard.html` | The dashboard (open this) |
| `sample_data.js` | Made-up data for demo mode |
| `.env.example` | Template for your private `.env` |
| `.gitignore` | Keeps `.env` and `garmin_data.js` out of git |
