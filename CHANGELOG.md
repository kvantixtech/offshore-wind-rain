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
