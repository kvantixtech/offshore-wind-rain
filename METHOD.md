# Method: has rain on the coast changed downwind of North Sea wind farms?

This was written before any rain-gauge value was downloaded. Before writing it, only these things were checked:
- that the sources exist, and what access they need
- their station lists, file listings and field names
- the wind-farm layer (positions, capacities, years).

Changes are listed in `CHANGELOG.md`, with the reason, before they take effect. A change made after results exist is marked as such, and the original result stays published next to it.

## Question

Since offshore wind farms were built off Denmark and Germany (about 0.2 GW in the North Sea before 2009, about 9 GW by 2025), has daily precipitation at rain gauges changed on days when the wind blows from the farms towards the gauge? The comparison is with:
- the same gauge on days with the same wind direction before the farms existed
- other gauges at a similar distance from the coast, in the same year and wind sector
- what a weather reanalysis without wind farms gives for the same day and place.

The method has two parts:
- **Part A (retrospective):** gauges in Denmark and northern Germany, 1991–2025.
- **Part B (prospective):** Danish gauges, rerun every year to the end of 2029. It focuses on the new farms just off the Danish west coast (Vesterhav Syd and Nord, Thor). Gauge data are read only after this method is published. Data from 2026 onward did not exist when it was written.

This checks a modelling claim against measurements. It says nothing about whether wind farms should be built, and it is not a verdict on any farm or company.

## The claim being checked

Akhtar, N., Elizalde, A., Geyer, B. & Schrum, C. (2026). *Projected impacts of future offshore wind farms on coastal precipitation over the Northwest European shelf.* Communications Earth & Environment 7, 651. <https://doi.org/10.1038/s43247-026-03852-x>

**What the paper did:**
- Simulated ten years of weather (2008–2017) with a regional climate model at about 5 km.
- Ran it with and without wind farms, for 2023, 2030 and a post-2050 build-out.

**What it found:**
- The abstract: "for post-2050 scenario, precipitation decreases by 10–12% in coastal regions of Germany, the Netherlands, and the United Kingdom, and by more than 15% in parts of Jutland, Denmark, particularly under south-westerly winds. Conversely, precipitation increases over the wind farm areas."
- For today's farms: "existing wind farms under the 2023 and 2030 scenarios indicate small effects on precipitation, with effects primarily confined to marine areas."
- North-westerly winds (280–360°) "exhibit negligible impact on precipitation in the coastal regions".
- The effect is "evident across all seasons except spring".

**What this method can and cannot test:**
- The largest decrease in Jutland lies downwind of a farm cluster the paper places about 80 km off the west coast. That cluster has not been built. So the post-2050 figures cannot be tested with measurements yet.
- What can be tested is the general claim that offshore farms reduce precipitation on the coast downwind. The test uses the farms that exist:
  - Part A asks whether today's farms already show an effect, or whether an effect of a stated size can be ruled out.
  - Part B asks the same question for the new Danish farms.

## Sources

| Source | What | Access |
|---|---|---|
| **DMI open data**, climateData API (`opendataapi.dmi.dk/v2/climateData`) | Station list and metadata. Daily accumulated precipitation `acc_precip` per station, from 1991 | CC BY 4.0, no key |
| **Deutscher Wetterdienst (DWD) Climate Data Center** (`opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/more_precip/`) | Daily precipitation per station, station list, and station metadata (instruments, location history) | CC BY 4.0, no key |
| **ERA5** (Copernicus Climate Change Service, ECMWF), via the CDS API | Hourly total precipitation, wind at 850 hPa, 10 m and 100 m, and the land-sea mask, on a 0.25° grid | CC BY 4.0. Free personal key, stored only as a GitHub secret |
| **EMODnet Human Activities, wind farms** (`ows.emodnet-humanactivities.eu/wfs`, layer `emodnet:windfarmspoly`) | Wind-farm polygons, status, capacity | CC BY 4.0 |
| **Marktstammdatenregister** (Bundesnetzagentur, full export) | German offshore turbines: position, capacity, commissioning and decommissioning dates | dl-de/by-2-0 |
| **Energistyrelsen, Stamdataregister for vindkraftanlæg** | Danish offshore turbines: position, capacity, connection and decommissioning dates | Published by the Danish Energy Agency. The terms are written to `CHANGELOG.md` at first download |

**About ERA5:**
- It is used as the comparison because its model physics contains no wind farms, and no rain-gauge data are assimilated over Europe.
- It does assimilate observations such as surface pressure and satellite winds over the sea, and these may carry small farm signals. For that reason wind direction is taken at 850 hPa, well above the turbines.
- An hourly ERA5 precipitation value at time `t` is the amount accumulated over the hour ending at `t`.

## Definitions

**Gauge series**
- One station's daily precipitation with no break in instrument or position.
- A station is split into separate series:
  - at every change of precipitation instrument type in its metadata
  - at every move of more than 1 km or 20 m in height.
- For DMI, each station number is its own series. The network moved from manual to automatic gauges in 2007–2011 under new station numbers. The split rule is applied to DMI's location history as well.

**Day**
- The 24-hour window that each network's daily value covers, as stated in the source documentation, for each period if the documentation changes over time.
- The window is written to `CHANGELOG.md` at first download, before any value is read.
- ERA5 hourly values are summed or averaged over the same window.
- **Window check.** Before the main analysis, a script finds, for each series, the shift of −1, 0 or +1 day that gives the highest correlation between `P` and `R`. This uses only `P` and `R`, never `E`. If the best shift differs from the documented window, the series is shifted by it, and the shift is logged in `results/`.

**Gauge value `P`**
- The daily precipitation (mm).
- Values flagged as missing or invalid by the source are dropped. The flags used are written to `CHANGELOG.md` at first download.

**Reanalysis value `R`**
- ERA5 total precipitation (mm) summed over the day's window.
- It is taken at the nearest grid cell whose land-sea mask is at least 0.5.

**Wind direction `θ`**
- The direction the wind comes from: the daily vector mean of ERA5 850 hPa wind over the day's window, at the grid cell nearest the gauge.
- Days with a vector-mean speed below 3 m/s have no clear direction and are left out.

**Direction bins and sectors**
- **Direction bin:** `θ` in 36 bins of 10°.
- **Sector:** `θ` in 8 sectors of 45° centred on N, NE, E, … NW.

**Coast band**
- The distance from the gauge to the nearest open-sea coastline: 0–10 km, 10–30 km or more than 30 km.
- **Sea basin:** North Sea and Wadden Sea, or Skagerrak–Kattegat–Baltic.
- The coastline is taken from the ERA5 land-sea mask at 0.5, so it is the same for every gauge.

**Turbines and capacity**
- Each offshore turbine is a point with its own capacity, its own commissioning date (Germany) or connection date (Denmark), and its decommissioning date where one exists.
- For farms without turbine positions in the registers (Dutch and Swedish farms), the EMODnet polygon is covered by points on a 500 m grid, and the farm's capacity is shared equally among them.
  - Those farms' first-power and full-commissioning dates are taken from the operator or the national authority, with the source in `data/farms.csv`.
  - Capacity rises linearly between the two dates.
- Farms included: every offshore farm within 150 km of any gauge used.

**Exposure `E`**
- The operating offshore wind capacity (GW) upwind of the gauge that day.
- It is the sum of the capacity of turbine points that are in operation that day and lie both:
  - within 22.5° of the bearing `θ` from the gauge
  - within 100 km of the gauge.
- `E` uses only wind and turbine data. It is computed and committed before any gauge value is read.

**Equivalence bound `Δ`**
- Fixed here, before any data are read: the effect per GW that would change rain by 10 % at the most exposed gauge.
- Formula: `Δ = 100 · (1 − 0.9^(1/E_max))` % per GW.
- `E_max` is the highest daily `E` at any gauge in 2025, from the committed exposure file.
- 10 % is the size of the paper's post-2050 coastal decrease. A change that large from today's farms would be far beyond what the paper expects for 2023.

## Which gauges and years

- **Area:** gauges on land or islands in Denmark and Germany between 4.5° and 13.0° E and 53.3° and 57.9° N. Inland gauges and gauges with no farm upwind stay in; they are the comparison.
- **Period:** Part A runs from 1 January 1991 to 31 December 2025.
- **Valid series:** a gauge series is used if it has at least 3 calendar years with values on at least 90 % of days in the period.
  - Day counts are computed by a script that outputs only the number of non-missing values per series and year.
  - No value is printed, plotted or summarised at that step.
- **The years before the farms:** 1991–2001 had no wind farm in the North Sea. Inner Danish waters had under 0.1 GW: Vindeby, Tunø Knob and Middelgrunden. Middelgrunden (40 MW, 2000) lies a few kilometres from the Copenhagen gauges. This period is used for the power check.

## Analyses

**1. Power check (before the main analysis)**
- It uses gauge data for 1991–2001 only.
- Each run:
  1. resamples whole calendar years with replacement from 1991–2001, all gauges together, to build an 11-year panel
  2. draws a start year uniformly from 1993–1997. From that year the 2025 turbine layout is switched on linearly over 3 years and then stays fully on. That gives a synthetic exposure from the real wind directions
  3. multiplies `P` by `exp(β·E_syn)` and fits the main model.
- Effects tested: `ρ` = −1, −2, −3, −5, −7.5, −10, −15, −20 and −30 % per GW, with 100 runs each, seed 20261002.
- `X` is the smallest `|ρ|` for which at least 80 % of runs give a 95 % interval that excludes 0.
- `X` is written to `CHANGELOG.md` before Analysis 2 runs.
- `X` is reported as the smallest effect the design can detect. It is not the bound for ruling effects out; that is `Δ`.
- With 11 years and a short ramp, `X` is a cautious estimate for the full 35-year design.
- For Part B, the same check is run with gauge series within 10 km of a current DMI automatic station, and a synthetic Vesterhav-plus-Thor layout. That gives `X_B`.

**2. The relation (primary).** A Poisson regression (pseudo-maximum likelihood), with one row per gauge series and day:

    P ~ exp( β·E + [series × direction bin × season] + [series × ERA5 class] + [year × sector × coast band × network] )

The terms in brackets are fixed effects:
- **Series × direction bin × season** (seasons DJF, MAM, JJA, SON):
  - each gauge's normal rain for each 10° wind direction and season
  - absorbs gauge placement, coastline, instrument, and how rain varies with direction
  - so `β` comes from changes over time, not from geometry.
- **Series × ERA5 class:** each gauge's own relation to the reanalysis value `R`. The classes are 0, ≤0.5, ≤1, ≤2, ≤4, ≤8, ≤16 and >16 mm.
- **Year × sector × coast band × network** (network = DMI or DWD):
  - anything that changed in a year for one wind sector, for all gauges at the same distance from the coast in the same network
  - examples: wetter westerlies, warmer seas, changes in how much rain coastal gauges catch.
  - Coastal gauges with no farm upwind, such as north-west Jutland or the Baltic coasts, are the comparison for exposed coastal gauges.

How to read `β`:
- It is reported as `ρ = 100·(exp(β) − 1)` % per GW.
- Intervals are on the `ρ` scale, by transforming the endpoints for `β`.

**Intervals for `β`**
- **Primary:** standard errors clustered by calendar year (35 clusters), with a t distribution with 34 degrees of freedom. Both 95 % and 90 % intervals are reported.
- **Randomization inference:** the effect comes from a handful of farm groups, so the year-clustered interval can be too narrow. Each farm group gets a start year drawn independently from 1993–2023. Its own ramp and capacity are kept, `E` is recomputed and the model refitted.
  - This is done 199 times, seed 20261002.
  - The p-value is the share of draws (counting the real one) with `|β|` at least as large as the real one.
  - The farm groups are: Horns Rev; Vesterhav; Thor; the German Bight north of 54.3° N; the German Bight south of 54.3° N; Dutch farms; Nysted and Rødsand; Anholt; Kriegers Flak and Baltic 1/2; Lillgrund; other German Baltic farms; and other Danish inner-water farms.
- **Also reported:**
  - leave-one-year-out (jackknife) intervals
  - two-way clustering by year and series
  - the estimate with each farm group left out in turn.

**3. Reading (Part A).** The rows are applied in order, and the first that fits is the reading.

| Reading | Condition |
|---|---|
| **Drier downwind** | The 95 % interval is entirely below 0, and the randomization p-value is below 0.05 |
| **Wetter downwind** | The 95 % interval is entirely above 0, and the randomization p-value is below 0.05 |
| **Effects of `Δ` or more ruled out** | The 90 % interval lies entirely within ±`Δ` (two one-sided tests at 5 %) |
| **Inconclusive** | Anything else |

**Labels and overrides**
- A "Drier" or "Wetter" reading whose 95 % interval also lies within ±`Δ` is labelled **small**.
- **Placebo failure.** If either placebo (below) has a 95 % interval excluding 0, and its estimate is at least half the primary estimate in size, the reading becomes **Inconclusive (placebo failed)**.
- **Too few exposed gauges.** If check 4 fails, the result is shown as exploratory, without a reading.
- **What to compare with the paper.** The paper expects small effects on land from today's farms, so "Effects of `Δ` or more ruled out" agrees with the paper's 2023 scenario. "Drier downwind" would be more than the paper expects for 2023. No reading confirms or refutes the post-2050 figures.
- The result is also shown as the change at `E_max`.

**4. Placebos (reported next to the primary result)**
- **P1, farms behind the gauge:**
  - `E_down` is computed for farms on the bearing `θ + 180°` and added to the primary model next to `E`. A farm downwind of the gauge is not expected to change its rain.
  - **P1b** does the same for farms at `θ ± 90°`.
  - The width of each interval is reported. Easterly days carry little rain, so a narrow interval matters more than a null.
- **P2, early start:**
  - `E_lead` is `E` computed with every turbine date moved 5 years earlier, minus the real `E`. It is added to the primary model on 1991–2025, and its coefficient should be 0.
  - In a second version, every date is moved 10 years earlier, the model is fitted on 1991–2008, and the real `E` is kept in the model.

**Robustness checks** are reported next to the primary result, never instead of it:
- **R1:** distance limit of 50 km and of 150 km.
- **R2:** sector half-width of 10° and of 45°.
- **R3:** wind direction from ERA5 10 m wind instead of 850 hPa.
- **R4:** `E` counted only when `θ` is 200–280°, the directions the paper names.
- **R5:** October to March only. Also the full year, with year × sector × season fixed effects.
- **R6:** without the ERA5 term.
- **R7:** only gauge series that run unbroken from 1991 to 2025.
- **R8:** Danish gauges only, and German gauges only.
- **R9:** capacity weighted by 1/distance instead of counted flat.
- **R10, heavy rain:** the outcome is whether `P` is at least 10 mm (logistic model, same terms). The paper describes a shift from heavy to lighter rain.
- **R11:** year × sector × coast band × sea basin, instead of × network.
- **R12:** series × ERA5 10 m wind-speed tercile × sector added. This catches gauges catching less rain in strong wind.
- **R13:** capacity counted only on days when the ERA5 100 m wind is 3–25 m/s, the range in which turbines run.
- **R14:** without gauges on islands inside or between farm areas (Helgoland). There the paper expects *more* rain.

**5. Part B (prospective)**
- It runs on Danish gauge series only, from 1 January 2011, after DMI's change to automatic gauges.
- `E` is split in two:
  - `E_new`: Vesterhav Nord, Vesterhav Syd, Thor, and farms added later
  - `E_old`: all other farms.
- The reading uses the coefficient on `E_new`, with the same rows as Part A and the bound `Δ_B`, computed like `Δ` from the highest `E_new` in the final year.
- **Year terms:** year × sector × coast band, with one network.
- **Interim runs:** run once a year by 31 May, for data to the end of 2026, 2027 and 2028. They report the estimate and interval, but **no reading**.
- **Final run:** the Part B reading uses data to the end of 2029.
- **New farms:** farms added after this method (for example Nordsøen I) enter `E_new` only through a dated `CHANGELOG.md` entry, made before that year's data are read.

## Compute

- Analyses 1 and 2 and the randomization fits are split over a GitHub Actions job matrix.
- Each job writes its estimates. `tools/build.py` then combines them.
- If a job cannot run within the runner's limits, the change of plan is written to `CHANGELOG.md` before any results are read.

## Data handling

- Every download is saved in `data/raw/`, or as a compressed extract of the region where the source is large, with its SHA-256 in `data/manifest.json`.
- Keys are never stored in the repository.
- `tools/build.py` computes everything from `data/`. CI recomputes it on every change and fails if any result differs.

**Order of work.** Each step is committed before the next one reads anything new:
1. Turbines and farms (`data/farms.csv`), with capacity per day and sources.
2. Gauge list and day counts.
3. ERA5.
4. Exposure `E`, `E_down`, `E_lead`, and `E_max`, `Δ`.
5. Power check (gauge values 1991–2001), giving `X` and `X_B`.
6. Window check, then the main analysis, placebos, robustness and randomization.

## Checks that must pass before results are shown

1. **Farm table.**
   - Every farm in the EMODnet layer with status "Production" or "Construction" within 150 km of a gauge has capacity and dates from a turbine register or a cited source.
   - National offshore totals at the end of 2025 match the national statistics within 5 %.
2. **Windows and flags.** The day window of each network and the dropped flags are in `CHANGELOG.md` before gauge values are read.
3. **Order.** `E`, `Δ` and `X` are committed before Analysis 2 runs.
4. **Enough exposed gauges.** At least 10 gauge series reach `E ≥ 0.5` GW on at least 100 days each. Otherwise the result is exploratory.
5. **No early reading.** No gauge value from after 2001 is read by any script before step 5 of the order of work is committed.

## What this can't show

- **The post-2050 scenario.** The farms that drive the paper's largest Jutland effect do not exist yet. No reading here confirms or refutes those figures.
- **Effects per GW don't scale up.** The effect is assumed to rise in proportion to installed GW within 100 km. Wakes saturate and fade with distance, so per-GW figures do not carry over to a much larger build-out.
- **Small effects.** Rain varies a lot from day to day and year to year. Effects smaller than `X` cannot be told apart from zero.
- **Gauges are not the sea.** The paper expects more rain over the farms. This method uses land and island gauges only.
- **Gauges catch less rain in strong wind,** and the catch changes with the instrument. Instrument changes are handled by splitting series and by the year terms per coast band, but a gauge's catch can still drift. R12 tests part of this.
- **ERA5 is not truth.** It is used as a comparison, and its errors are absorbed by each gauge's ERA5 classes. Assimilated observations may carry small farm signals.
- **One direction per day.** The wind turns within a day, and the 850 hPa wind is not the wind at turbine height.
- **Things that change at the same time as a farm.** A change at a coastal gauge that coincides with a nearby farm, such as a site change or local land use, cannot be separated from the farm beyond what the placebos and comparison gauges test.
- **A relation across gauges and years is not an experiment.**

## References

- Akhtar, N., Elizalde, A., Geyer, B. & Schrum, C. (2026). Communications Earth & Environment 7, 651. <https://doi.org/10.1038/s43247-026-03852-x>
- Akhtar, N., Geyer, B. & Schrum, C. (2022). *Impacts of accelerating deployment of offshore windfarms on near-surface climate.* Scientific Reports 12, 18307. <https://www.nature.com/articles/s41598-022-22868-9>
- Al Fahel, N. & Archer, C. L. (2020). *Observed onshore precipitation changes after the installation of offshore wind farms.* Bulletin of Atmospheric Science and Technology 1, 179–203. <https://link.springer.com/article/10.1007/s42865-020-00012-7>
- Vautard, R. et al. (2014). *Regional climate model simulations indicate limited climatic impacts by operational and planned European wind energy projects.* Nature Communications 5, 3196. <https://www.nature.com/articles/ncomms4196>
- Platis, A. et al. (2018). *First in situ evidence of wakes in the far field behind offshore wind farms.* Scientific Reports 8, 2163. <https://www.nature.com/articles/s41598-018-20389-y>
- Hersbach, H. et al. (2020). *The ERA5 global reanalysis.* Quarterly Journal of the Royal Meteorological Society 146, 1999–2049. <https://doi.org/10.1002/qj.3803>
