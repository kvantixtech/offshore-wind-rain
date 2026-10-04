# Has rain on the coast changed downwind of North Sea wind farms?

A 2026 modelling study (Akhtar et al., *Communications Earth & Environment* 7, 651) projects that a large post-2050 build-out of offshore wind in the North Sea would cut coastal rain by 10–15 %, and by more than 15 % in parts of Jutland. For today's farms it expects small effects, mostly at sea.

This repository checks the claim with open measurements:
- **Part A:** do rain gauges in Denmark and northern Germany, 1991–2025, show a change on days when the wind blows from existing farms? Or can an effect of a stated size be ruled out?
- **Part B:** the same question for the new farms off the Danish west coast (Vesterhav, Thor), rerun every year to 2029.

The method was written and committed before any rain-gauge data were read: [`METHOD.md`](METHOD.md). Every change after that, and why, is in [`CHANGELOG.md`](CHANGELOG.md).

**Status:** method committed; turbines, gauge list and day windows done; ERA5 being fetched. No rain-gauge value has been read.

**Live status page:** <https://kvantix.tech/playground/wind-rain/>

Sources:
- DMI open data (CC BY 4.0)
- Deutscher Wetterdienst Climate Data Center (CC BY 4.0)
- ERA5 from the Copernicus Climate Change Service (CC BY 4.0)
- EMODnet Human Activities (CC BY 4.0)
- Marktstammdatenregister (dl-de/by-2-0)
- Energistyrelsen's turbine register.

Kvantix · CVR 46296036 · MIT licence for code. The data keeps its source licences.
