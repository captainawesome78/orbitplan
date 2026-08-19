# Changelog

## 0.4.0

### Changed — placement results move

**`compare_placement` now prices radiation fault tolerance by default, and every
placement number this package produces has shifted.** Until now the orbit side assumed
the workload runs exactly once, which silently valued correctness at zero and biased
every verdict toward orbit.

`OrbitOption.redundancy_factor` defaults to **1.15** — periodic scrubbing and
checksummed weights, the cheap end of the range. On the reference SAR scenario the
crossover moves from **6.43 to 7.39 GB/day**, and orbit's daily cost from $59.62 to
$64.96.

Pass `redundancy_factor=1.0` to reproduce anything published against 0.3.x.

This is a deliberate break. The previous default was not neutral — it was an assumption
that nobody checks their results, stated by omission.

### Added

- **`OrbitOption.redundancy_factor`** — the parameter behind the change above.

  Use `1.0` for no protection, `1.15` (default) for scrubbing and checksums, `1.74`
  for the Efficient Modular Redundancy of Wang et al., ASPLOS '26, which reports 63%
  less runtime overhead than 3-MR, and `3.0` for classical triple modular redundancy.
  The factor scales both `hardware_usd` and `payload_mass_kg`, since more compute
  needs more silicon *and* the power and radiator area to run it.

  Values below 1.0 raise `ValueError`.

- `PlacementResult.redundancy_factor`, surfaced in `summary()`. When the factor is
  left at its default, `summary()` now says so explicitly rather than leaving the
  omission invisible.

### Why this matters

The crossover moves roughly linearly with the factor. On the reference SAR scenario
(800 MB in / 2 MB out, X-band, 25 kg, $40,000 hardware, $1,000/kg, 5 years):

| redundancy | crossover     |                          |
| ---------- | ------------- | ------------------------ |
| 1.0        | 6.43 GB/day   | 0.3.x behaviour          |
| **1.15**   | **7.39 GB/day** | **new default**        |
| 1.74       | 11.18 GB/day  | EMR-like                 |
| 3.0        | 19.25 GB/day  | classical 3-MR           |

At an 8 GB/day operating point the verdict flips from orbit to ground at a factor of
**1.245** — so the default sits just below the line, and any mission running more than
the lightest mitigation should expect the answer to change.

### Compatibility

Placement figures move. `crossover_gb_per_day`, `orbit_total_usd_day`, `cost_ratio` and
in marginal cases `winner` will all differ from 0.3.x for the same inputs. Pin
`redundancy_factor=1.0` if you need the old numbers.

Nothing outside `compare_placement` is affected — power, thermal, downlink and relay
results are unchanged.

---

## 0.3.0 — 5 Aug 2026

Inter-satellite relay modelling (`RelayLink`), constellation and ground-segment
limits.

## 0.2.0 — 31 Jul 2026

Placement comparison (`compare_placement`), ground versus orbit economics.

## 0.1.0 — 29 Jul 2026

Initial release: power, thermal and downlink budgets with bottleneck identification.
