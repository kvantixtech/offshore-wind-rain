# Changelog

Changes to the method are written here, with the reason, before they take effect.

## 2026-10-02

- **What was checked before writing.** Before `METHOD.md` was written, a metadata-only probe ran in GitHub Actions on 2 October 2026. It was a temporary branch of kvantixtech/nitrogen-sources-denmark, commit `62cad07`. It fetched:
  - DMI's climateData and metObs station lists
  - DWD's directory listings and station descriptions for daily precipitation and climate stations
  - the EMODnet wind-farm layer
  - the Marktstammdatenregister download page
  - the ERA5 catalogue entries.

  It requested no observation, grid or reanalysis value.
- **What the station lists showed.**
  - DMI's precipitation network west of 8.75° E fell from 65 stations (1991) to 28 (2011). Manual gauges were replaced by automatic ones under new station numbers. That is why `METHOD.md` splits series and adds year terms per coast band and network.
  - The EMODnet layer has wrong or missing years for several farms, so turbine registers are used for dates.
- **Independent review.** A draft of `METHOD.md` was reviewed by a separate reviewer that had not written it. The changes made before this first commit:
  - a power check with real randomness
  - fixed effects by 10° direction bin
  - year terms per coast band
  - randomization inference over farm start years
  - an equivalence bound `Δ` fixed in advance, instead of one that depends on noise
  - placebos that contain no real exposure
  - a Part B coefficient for the new farms only, with no reading at interim runs.
- `METHOD.md` committed. No rain-gauge value has been downloaded.

## 2026-10-03: step 1, turbines and farms (no rain data)

- **Danish register.** Energistyrelsen publishes the register as two files:
  - `Vinddata.xlsx` (turbines in the register now): `https://ens.dk/media/8748/download`
  - `Historiske vinddata.xlsx` (decommissioned turbines): `https://ens.dk/media/8746/download`

  Offshore turbines are those with "Type af placering" = `HAV`. In `Vinddata.xlsx` the headers "Kommune" and "Type af placering" are swapped relative to the values, so the column is found by its values (`LAND`/`HAV`). The page states no licence, only a disclaimer. The files are kept unchanged in `data/raw/`.
- **German register.** The Marktstammdatenregister full export is 3.2 GB. Only its member `EinheitenWind.xml` is read, with HTTP range requests, and the zip member's CRC is recorded.
  - Offshore = `WindAnLandOderAufSee` 889 ("Windenergie auf See").
  - Sea = `Seelage` 640 (Nordsee) or 639 (Ostsee).
  - Capacity = `Nettonennleistung`. Start = `Inbetriebnahmedatum`. End = `DatumEndgueltigeStilllegung`.
  - Units without a position or a commissioning date (planned units) are left out and listed in `data/farms_check.json`.
- **Farms without a turbine register here.** These are Gemini I/II (NL) and Lillgrund (SE), the only non-Danish, non-German farms within 150 km of a station. Their dates and sources are in `data/farms_manual.csv`. Rules for dates:
  - When a source gives only a month, the 15th is used.
  - When it gives only a year, capacity rises over that whole year.
- **Lillgrund.** The operator (Vattenfall) says "commissioned in 2007". Power Technology says June 2008. The operator is used, as METHOD.md says, and both sources are in the file.
- **Which farms count.** Farms in the EMODnet layer with status Production, Construction or Dismantled within 150 km of any DMI or DWD precipitation station in the box (station metadata only). The exact gauge set comes in step 2. Exposure is computed only from farms within 100 km (150 km in R1) of each gauge.
- **Farm names and groups.**
  - A register turbine gets the name of the EMODnet farm whose polygon contains it, or lies within 2 km. Otherwise it keeps the register's own park name.
  - Groups for the randomization inference follow METHOD.md. German North Sea farms are split at 54.3° N.
- **First run (commit `9d1bf65`), and what it led to:**
  - **Turbines.** 2,863 turbine points: 750 Danish (ENS), 1,808 German (MaStR), 305 grid points for Gemini and Lillgrund. 59 farms.
  - **Left out.** 101 German units have no commissioning date: the planned clusters "NC 1–4", 6 He Dreiht units and 1 Windanker unit. They are listed in the check file.
  - **No farm missing.** No EMODnet farm within 150 km of a station is without turbines.
  - **Two naming fixes,** made before any exposure is computed:
    1. All turbines of one register park now take the EMODnet name that most of that park's turbines match. For example, one Arkona unit lay just outside the polygon and became a farm of its own.
    2. Danish register turbines outside every EMODnet polygon and without a park name (the 11 Vindeby turbines, 1991–2017) are named from `data/farm_names_extra.csv`, which cites its source. This changes names and groups only, not capacity or dates.
  - **German total.** In operation at the end of 2025: 9,737 MW. Deutsche WindGuard, *Status des Offshore-Windenergieausbaus in Deutschland, Jahr 2025*, gives 9,740 MW. The difference is under 0.1 %.
  - **Danish total.** 2,632 MW. The national figure to compare with is still to be found; check 1 is not passed until it is.
  - **Danish dates are per park.** The register gives one connection date for all turbines of most Danish parks, for example Horns Rev 3: 2018-12-23. The capacity of such a park therefore starts on one day.
- **The coverage check follows the fix.** After the renaming, the EMODnet layer's second polygon for Baltic 1 ("EnBW Baltic I", the same 48 MW farm as "EnBW Windpark Baltic 1") was reported as missing. The check now counts a polygon as covered when any turbine point lies within 2 km of it, whatever name the turbine carries.

## 2026-10-03: step 2, gauge list and day counts (no precipitation amount is output)

`tools/gauges.py` downloads:
- DMI's station metadata and DWD's station files: location history, instrument history and parameter description.
- The daily precipitation files, from which it counts the days that have a value per gauge series and year.

**What a "value" means:**
- **DWD:** any `RS` that is not the missing-value code `-999`.
- **DMI:** any daily feature with a value. Missing days are absent from DMI's API.

**What is kept and what is not:**
- Only counts are kept, together with flag counts, the start and end times of DMI's daily values, and the SHA-256 of every download.
- The downloaded values are discarded.
- The values are fetched again in step 5, for 1991–2001 only, and in step 6.

**Series splits:**
- DMI: one station number is one series. It is split if the station moves more than 1 km or 20 m in height.
- DWD: series are split at every change of precipitation instrument type and at every such move.

**First and last period of a DMI station.** DMI's metadata versions can start after the station began. The first period therefore starts at the earliest `operationFrom`, and the last period ends at the latest `operationTo`.
- **First run (commit `4598d52`), and what it led to:**
  - **What was counted.** 882 DMI stations and 427 DWD stations in the box. 1,954 gauge series, of which 1,384 have at least 3 complete years (660 DMI, 724 DWD).
  - **Splits.** DMI's metadata has 476 location changes of more than 1 km under the same station number, so 402 DMI series start with a move. DWD has 165 moves and 346 instrument changes.
  - **DMI flags.** The flags present are only qcStatus `manual` or `none`, with validity `True`. Nothing is flagged invalid, so no DMI value is dropped on flags.
  - **DWD flags.** QN_6 is 9, 3 or 1 (and `-999` on 9 rows). All released levels are kept. Only the missing code `-999` in `RS` is dropped.
  - **The day window is not settled yet.** DWD gives it per station and period in `Metadaten_Parameter`. For example, at station 52 until 2001 it reads "07:30 – 07:30 FT. GZ": 07:30 legal local time to 07:30 on the following day. The script is therefore extended to keep the RS window text for every station period, and DMI's window with its UTC offset. This is metadata only. The window rule is fixed here before any value is read (check 2).

## 2026-10-03: day windows fixed (check 2), before any value is read

From the second run (commit `3797cb7`), metadata only.

**DMI**
- Every daily value runs from 00:00 to 00:00 Danish local time. The API states the offsets: `+01:00` in winter, `+02:00` in summer, and mixed on the days the clock changes.
- A DMI day D is therefore D 00:00 to D+1 00:00 local time.

**DWD**
- The window for `RS` is stated for every station period in `Metadaten_Parameter`, and kept in `data/gauges/dwd_rs_windows.csv`.

| Text in the file | Window for date D |
|---|---|
| `05:51 - 05:50 FT. UTC` and `06:00 - 06 FT. UTC (05:51-05:50 FT.UTC)` (automatic) | D 06:00 UTC to D+1 06:00 UTC |
| `… sonst 07:30 - 07:30 FT. GZ`, and `… sonst 07:30 GZ` (manual stations) | D 07:30 to D+1 07:30 legal local time (CET/CEST) |

"FT" is Folgetag (the following day) and "GZ" is Gesetzliche Zeit (legal local time). The `NBL 07:00` rule applies only before 1991 and is not used.

**The rule for ERA5 (step 3)**
- ERA5's hourly values are the amount in the hour *ending* at their timestamp.
- For each gauge day, the window start is converted to UTC and rounded to the nearest whole hour, with halves rounded down. For example, 07:30 CET is 06:30 UTC, which becomes 06:00 UTC.
- R is the sum of the 24 ERA5 hours whose end times lie in the window (start, start + 24 h]. On days when the clock changes, a local-time window has 23 or 25 hours, and the sum covers them all.
- The 850 hPa wind direction is the vector mean over the same hours.
- The window check in METHOD.md (best shift of −1, 0 or +1 day) still runs before the main analysis and catches any day assigned wrongly.

## 2026-10-04: step 3, ERA5 (no rain-gauge value is read)

`tools/era5.py` fetches hourly ERA5 from the Copernicus Climate Data Store (CC BY 4.0):
- **Variables:** total precipitation; 10 m and 100 m wind; 850 hPa wind; the land-sea mask (once).
- **Area:** 52.8–58.5° N, 4.0–13.5° E.
- **Period:** 1991–2025, plus the hours on either side.

**Cells**
- Each valid gauge series gets:
  - its nearest cell with land-sea mask ≥ 0.5, for R
  - its nearest cell of any kind, for the wind.
- Every cell holding a turbine point is kept for the 100 m wind (R13).
- The cell lists are in `data/era5/series_cells.csv` and `farm_cells.csv`.

**What is kept**
- The hourly values are summed or averaged over the day windows fixed on 3 October:
  - `DMI`
  - `DWD_UTC06`
  - `DWD_LT0730`
- Danish cells get the DMI window. German cells get both DWD windows. Which one applies to a series on a date follows `data/gauges/dwd_rs_windows.csv`.
- For R13, the number of hours with 100 m wind of 3–25 m/s is kept for every farm cell and window.

**What is not kept, and why**
- The hourly downloads are about 4 GB, which is too large for the repository. Their SHA-256 is listed per year in `data/era5/downloads_<year>.csv`, and the reduced day values are committed.
- ERA5 is a fixed archive. Only the newest months (ERA5T) can be revised, and 2025 was final by the time of download.
- This is the "compressed extract of the region" allowed in METHOD.md.

**Key.** The CDS key is a GitHub secret (`CDSAPI_KEY`) and is never written to the repository.
- **First attempt failed, and the fetching was changed (no data affected).**
  - What happened: the first run sent up to 32 monthly requests at once. CDS rejected most of them with "Number queued requests for this dataset is temporarily limited", and the script's retries made it worse. The logs are in `data/era5/first_attempt/`.
  - What changed: whole years are now fetched one at a time, with one request per dataset, the two datasets side by side.
  - A rejection for the queue limit now means waiting 10 minutes before trying again.
  - Each year is reduced to day windows once the next year (its 1 January) is in.
  - The hourly files wait between runs in the GitHub Actions cache. They are never committed.
  - An hourly schedule carries on until 1991–2025 are all in.
  - Nothing about what is computed changes.
- **Request size.** A whole year of single-level data was refused ("cost limits exceeded"). A refused selection is now split in two by months, as often as needed. The data are the same.

## 2026-10-04: live status for the page

- `tools/status.py` writes `data/status.json`: the steps, whether each is done, its commit, the counts behind it, and how many ERA5 years are in.
- It is built only from committed files and the git log. It never holds a rain-gauge value or a result. The result goes on the page by hand, after it has been checked.
- The ERA5 workflow runs it after each commit. A `status` workflow runs it after changes pushed by hand.
- The page at kvantix.tech/playground/wind-rain/ reads the file live.
