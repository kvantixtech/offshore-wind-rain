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
