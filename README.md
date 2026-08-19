# orbitplan

**Feasibility planner for inference in orbit — find the constraint that's actually stopping you.**

Three things decide whether a model can run in space, and they fight each other:
the array has to make the power, the radiator has to shed the heat that power
becomes, and the ground link has to carry whatever data survives. Optimising one
in isolation is how orbital compute plans die. `orbitplan` reconciles all three
against a real sensor or serving load and names the binding constraint.

Part of a set:

- [`orbitherm`](https://github.com/captainawesome78/orbitherm) — sizes the radiator (used automatically when installed)
- [`radshield`](https://github.com/captainawesome78/radshield) — keeps the model correct under radiation-induced bit flips

## Install

```bash
pip install orbitplan            # core
pip install orbitplan[thermal]   # + orbitherm for the full thermal model
```

## Quick start

```python
import orbitplan as op

plan = op.MissionPlan(
    sensor=op.Sensor(burst_gb_per_s=10, duty_cycle=0.002),      # SAR instrument
    workload=op.Workload.preset("sar_segmenter", input_mb=800, output_mb=2),
    accelerator=op.Accelerator.preset("jetson_agx_orin"),
    power=op.PowerBudget(array_area_m2=8),
    thermal=op.ThermalBudget(radiator_area_m2=2),
    link=op.LinkBudget(band="x_band"),
)

r = plan.evaluate()
print(r.bottleneck)     # -> 'none'
print(r.summary())
```

Drop the onboard inference (`output_mb=800`) and the same satellite becomes
downlink-bound: 1,728 GB/day of raw data against 72 GB/day of X-band capacity.
That gap is the entire business case for processing in orbit.

### Does a laser mesh fix it?

```python
link = op.LinkBudget(band="x_band", relay=op.RelayLink(
    constellation_size=100, ground_stations=10))

print(link.gb_per_day)             # 694 GB/day, up from 72
print(link.relay.limiting_factor)  # 'ground segment'
```

Ten-fold more capacity — and the raw-downlink case is *still* infeasible. The
optical terminals could carry ~600,000 GB/day; the constellation's share of ten
ground stations is 622. Relaying through 100 satellites into 10 stations buys a
tenth of ten stations. Widen the ground segment (20 sats / 30 stations → 9,400
GB/day) and it finally closes.

## Should it run in orbit at all?

`compare_placement()` answers the commercial question the feasibility engine
doesn't: process onboard, or downlink everything and use a terrestrial cloud?

```python
r = op.compare_placement(
    workload=op.Workload.preset("sar_segmenter", input_mb=800, output_mb=2),
    inferences_per_day=2160,
    data_gb_per_day=1728,
    link=op.LinkBudget(band="x_band"),
)
print(r.winner)      # 'orbit'
print(r.summary())
```

```
ground  : $9,600.00/day (station $9,600.00 + compute $0.00)
          needs 16.00 h of contact, 0.67 h available  <-- IMPOSSIBLE
orbit   : $64.96/day (amortised $40.96 + station $24.00), at 1.15x redundancy
winner  : orbit (147.8x cheaper)
crossover: orbit wins above ~11.7 GB/day
```

The asymmetry that decides it: process in orbit and you downlink a *result*;
process on the ground and you must first downlink *everything* — and contact
time is billed by the minute and rationed by orbital geometry. Past a few
GB/day the ground option stops being expensive and starts being impossible.

It is not biased toward orbit. Below the crossover it says so plainly:

```
winner  : ground (1.5x cheaper)
verdict : Ground, 1.5x cheaper. At 5.0 GB/day there isn't enough data to
          justify amortising $74,750 of hardware and launch.
```

Pass `data_must_stay_onboard=True` to model a sovereignty constraint — the
ground option is then disqualified on compliance, and the tool reports the
premium you're paying rather than pretending it's cheaper.

Prices default to public list rates (AWS Ground Station wideband, EC2 g5.xlarge)
and are overridable via `GroundOption` / `OrbitOption` — they date quickly.

### Correctness isn't free — it's priced in

A single-event upset can silently corrupt a result on commodity hardware, and every
mitigation costs compute. `redundancy_factor` prices that, and **defaults to 1.15** —
the lightweight case of periodic scrubbing and checksummed weights.

```python
for R in [1.0, 1.15, 1.74, 3.0]:
    r = op.compare_placement(..., orbit=op.OrbitOption(redundancy_factor=R))
    print(R, r.crossover_gb_per_day, r.winner)
```

```
1.00   6.43 GB/day   orbit     # no protection at all
1.15   7.39 GB/day   orbit     # default: scrubbing + checksums
1.74  11.18 GB/day   ground    # EMR-like
3.00  19.25 GB/day   ground    # classical 3-MR
```

The crossover moves roughly linearly with the factor, which makes it a bigger lever
than launch price or hardware price — and on an 8 GB/day workload the verdict flips
from orbit to ground at a factor of just **1.245**. Use `3.0` for classical triple
modular redundancy; `1.74` approximates the Efficient Modular Redundancy of
[Wang et al., ASPLOS '26](https://www.cs.columbia.edu/~junfeng/papers/radshield-asplos26.pdf),
which reports 63% less runtime overhead than 3-MR.

**Changed in 0.4.0.** Earlier versions behaved as `1.0`, silently pricing correctness at
zero and biasing every verdict toward orbit. Pass `redundancy_factor=1.0` to reproduce
figures published against 0.3.x.

## What it models

**Power** — solar array output derated for cell efficiency, packing, eclipse
fraction, battery round-trip and PMAD losses, minus bus overhead.

**Thermal** — the heat-rejection ceiling on sustained compute. Delegates to
`orbitherm` when installed; falls back to a bare Stefan-Boltzmann estimate
otherwise.

**Downlink** — contact time × rate × passes, derated for protocol overhead, versus
the data actually produced. Anything the payload can't process has to go down raw.

**Inter-satellite relay** (optional) — a laser crosslink mesh. A mesh doesn't
create bandwidth, it creates *reach*: instead of storing data until this
satellite flies over a station, it hands off to a neighbour that can see one
now. So it's capped by the crosslink **and** by this satellite's share of the
constellation's total ground pipe — and in practice the ground segment binds
first, which is the part most mesh plans get wrong.

**Workload** — energy and latency per inference from real accelerator
efficiency (peak TOPS derated by an achievable-utilisation factor, which is
where most naive estimates go wrong).

## Verdicts

`evaluate()` returns a `PlanResult` whose `bottleneck` is one of:

| value | meaning |
|---|---|
| `power` | the array can't sustain the processing load |
| `thermal` | the radiator can't shed the heat that load produces |
| `downlink` | compute keeps up, but the results still don't fit the link |
| `none` | all three close, with margin |

Every result carries the numbers behind the call — margins, watts required
versus available, GB/day generated versus downlinked — so you can see *how far*
off you are, not just that you failed.

## Presets

Accelerators: `jetson_orin_nx`, `jetson_agx_orin`, `nvidia_l4`, `nvidia_h100`.
Workloads: `resnet50`, `vit_b16`, `yolov8m`, `sar_segmenter`, `llm_1b_token`.
Bands: `s_band`, `x_band`, `ka_band`, `optical`. All overridable.

## Scope

First-order feasibility triage — for architecture trade studies, go/no-go calls
and sanity-checking orbital compute claims. Not a substitute for detailed
mission design: it assumes circular LEO, worst-case (β=0) eclipse geometry, an
isothermal radiator, and steady-state operation.

## License

Apache-2.0
