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
