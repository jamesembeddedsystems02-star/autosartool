# SDV Cockpit — In-Car Infotainment HMI

A **software-defined-vehicle (SDV)** infotainment human-machine interface,
styled as a real in-car center-console touchscreen. One self-contained
`index.html` — no build step, no dependencies, no network.

## Run it

```bash
# just open the file
xdg-open infotainment/index.html      # Linux
open infotainment/index.html          # macOS
start infotainment\index.html         # Windows
```

Or double-click `index.html`. It renders at a 16:10 aspect ratio inside a
display bezel so it reads like a dash-mounted screen.

## What's on screen

A left **app dock** switches between full-screen apps; a persistent
dual-zone **climate dock** sits along the bottom, exactly like current OEM
HMIs.

| App | What it does |
|-----|--------------|
| **Home** | Live map preview, now-playing widget, EV state-of-charge ring + range, quick tiles |
| **Maps** | Real-time Google Maps (with an API key) or an animated canvas fallback — turn-by-turn strip, search bar, and a live step list routing to **Times Square, New York** |
| **Media** | Album art with animated EQ, transport controls, sources (Bluetooth / Radio / USB), and a playable queue |
| **Phone** | Recent-calls list (incoming / outgoing / missed) and a working dial pad |
| **Car** | Vehicle top-view with door status, drive-mode selector, energy & range, per-wheel TPMS, and an **over-the-air software update** you can install |
| **Settings** | Vehicle, display & connectivity toggles and segmented controls |

## What's interactive

- Tap the dock to switch apps; quick tiles deep-link into the right screen.
- Climate: raise/lower each zone's temperature, change fan speed, toggle
  AUTO / A-C / defrost / seat heat / recirc / sync.
- Media: play/pause, next/prev, pick a track from the queue, switch source;
  the progress bar and clock advance in real time.
- Car: switch drive mode, and run the **OTA update** — the install bar and
  per-ECU status (VCU / IVI / ADAS / BMS) progress to completion.
- Ambient telemetry: the live clock, a wandering speed readout, and a slowly
  depleting battery/range keep the screen "alive."

## Real-time Google Maps (destination: New York)

The **Home** and **Maps** screens can render a live Google map — dark-themed
to match the cockpit — with a **real-time traffic layer** and a route to
**Times Square, New York** (origin: JFK Airport). The live Directions result
drives the on-screen ETA, distance, arrival time and turn list
(`departureTime = now`, so the ETA reflects current traffic).

This needs a **Google Maps JavaScript API key** (enable *Maps JavaScript API*
+ *Directions API* at <https://console.cloud.google.com/>). Provide it any
one of these ways — no rebuild required:

```bash
# 1. URL parameter (easiest for a quick try)
open "infotainment/index.html?gmapskey=YOUR_KEY"

# 2. Save it once in the browser, then just open the file
localStorage.setItem('sdv_gmaps_key','YOUR_KEY')

# 3. Hardcode it — set GMAPS_API_KEY at the top of the <script> in index.html
```

Change the city by editing `ORIGIN` / `DEST` (lat/lng) in the script.

> **Two important notes.** (1) The Google Maps script loads from
> `maps.googleapis.com`, so it only works when the file is opened locally or
> self-hosted — a **sandboxed preview with a strict Content-Security-Policy
> (e.g. the shared web artifact) blocks it**, and the built-in canvas map is
> shown instead. (2) Without a key, the canvas map (already themed to the
> New York route) is the fallback everywhere. No key is ever committed.

## SDV / AUTOSAR angle

The **Car** screen frames the vehicle as a set of independently updatable
software components — Vehicle Control (VCU), Infotainment (IVI), Driver
Assist (ADAS) and Battery Management (BMS) — receiving a coordinated
over-the-air release. The **BMS** node is the same battery ECU exercised by
the HIL test tool in this repo, so the cockpit's state-of-charge, range and
efficiency read-outs map onto signals the HIL bench can produce.

## Design notes

- Committed dark single-theme (a real in-car display is never light-mode):
  deep blue-black ground, teal-cyan primary accent, electric-blue for
  navigation, and semantic green / amber / red for status.
- No web fonts (a strict page can block CDNs) — a geometric system-sans
  stack with tabular numerals for every read-out.
- The map is drawn on `<canvas>`; everything else is CSS + inline SVG icons.
- All motion is gated behind `prefers-reduced-motion: reduce`.
