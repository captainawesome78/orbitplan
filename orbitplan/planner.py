"""Mission planner: reconcile power, thermal and downlink into one verdict.

The question this answers is not "can the satellite make power?" but: given a
sensor producing data at some rate, can the payload keep up with it, can the
radiator shed the heat that costs, and does whatever survives fit through the
ground link? Whichever of those three fails first is the answer that matters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .budgets import Orbit, PowerBudget, ThermalBudget, LinkBudget
from .workload import Accelerator, Workload


@dataclass
class Sensor:
    """The instrument generating data that needs processing.

    ``gb_per_day`` is the raw volume produced. For duty-cycled instruments give
    the burst rate and the duty: a SAR at 10 GB/s imaging 2% of the time makes
    ``Sensor(burst_gb_per_s=10, duty_cycle=0.02)``.
    """
    gb_per_day: Optional[float] = None
    burst_gb_per_s: Optional[float] = None
    duty_cycle: float = 1.0
    name: str = "sensor"

    def __post_init__(self):
        if self.gb_per_day is None:
            if self.burst_gb_per_s is None:
                raise ValueError("give gb_per_day or burst_gb_per_s")
            self.gb_per_day = self.burst_gb_per_s * self.duty_cycle * 86400.0


@dataclass
class PlanResult:
    # power / thermal envelope
    power_available_w: float
    thermal_limit_w: float
    sustained_compute_w: float
    power_headroom: str                # which of power/thermal binds first

    # workload demand vs capacity
    inferences_required_per_day: float
    inferences_capacity_per_day: float
    compute_margin: float              # capacity / required; <1 means short
    energy_per_inference_j: float
    energy_required_w: float           # continuous watts to keep up
    accelerators_needed: float

    # data
    data_generated_gb_day: float
    data_after_inference_gb_day: float
    downlink_capacity_gb_day: float
    link_margin: float                 # capacity / needed; <1 means short
    achieved_reduction: float
    required_reduction: float

    bottleneck: str                    # power|thermal|downlink|none
    feasible: bool
    message: str
    notes: List[str] = field(default_factory=list)

    @staticmethod
    def _w(x: float) -> str:
        if x < 1.0:
            return f"{x*1000:,.1f} mW"
        return f"{x:,.0f} W"

    @staticmethod
    def _x(v: float) -> str:
        if v == float("inf"):
            return "inf"
        if v >= 1000:
            return f"{v:,.0f}x"
        return f"{v:,.2f}x"

    def summary(self) -> str:
        L = [
            f"bottleneck        : {self.bottleneck}",
            f"envelope          : {self.sustained_compute_w:,.0f} W sustained "
            f"(power {self.power_available_w:,.0f} W | thermal {self.thermal_limit_w:,.0f} W)",
            f"compute needed    : {self._w(self.energy_required_w)} continuous "
            f"({self.accelerators_needed:,.2f} x accelerator)",
            f"inferences/day    : {self.inferences_required_per_day:,.0f} required, "
            f"{self.inferences_capacity_per_day:,.0f} affordable "
            f"(margin {self._x(self.compute_margin)})",
            f"energy/inference  : {self.energy_per_inference_j*1000:,.2f} mJ",
            f"data generated    : {self.data_generated_gb_day:,.1f} GB/day",
            f"after inference   : {self.data_after_inference_gb_day:,.2f} GB/day "
            f"({self._x(self.achieved_reduction)} reduction)",
            f"downlink capacity : {self.downlink_capacity_gb_day:,.1f} GB/day "
            f"(margin {self._x(self.link_margin)})",
            f"verdict           : {self.message}",
        ]
        return "\n".join(L)


@dataclass
class MissionPlan:
    """A payload evaluated against its full orbital envelope."""
    sensor: Optional[Sensor]
    workload: Workload
    accelerator: Accelerator
    power: PowerBudget
    thermal: ThermalBudget
    link: LinkBudget
    orbit: Orbit = None
    demand_per_day: Optional[float] = None
    """Inferences/day required. Overrides the sensor-derived figure -- use for
    continuously served workloads (LLM tokens, on-demand analytics) whose
    demand is not set by an instrument."""

    def __post_init__(self):
        if self.orbit is None:
            self.orbit = self.power.orbit
        if self.demand_per_day is None:
            if self.sensor is None:
                raise ValueError("give a sensor or demand_per_day")
            if self.workload.input_mb <= 0:
                raise ValueError("workload.input_mb must be > 0 to size "
                                 "against a sensor")

    def evaluate(self) -> PlanResult:
        notes: List[str] = []
        wl, ac = self.workload, self.accelerator

        # --- 1. sustained power envelope -----------------------------------
        p_avail = self.power.compute_w
        p_therm = self.thermal.max_compute_w
        sustained = min(p_avail, p_therm)
        headroom = "thermal" if p_therm < p_avail else "power"
        if self.thermal.backend == "builtin":
            notes.append("thermal: builtin fallback "
                         "(pip install orbitherm for the full environment model)")

        # --- 2. demand set by the sensor, not by the clock -----------------
        if self.demand_per_day is not None:
            required = float(self.demand_per_day)
            gen_gb_src = required * wl.input_mb / 1000.0
        else:
            required = (self.sensor.gb_per_day * 1000.0) / wl.input_mb
            gen_gb_src = self.sensor.gb_per_day
        e_inf = wl.energy_j(ac)
        energy_required_w = required * e_inf / 86400.0               # continuous W
        capacity = (sustained * 86400.0) / e_inf if e_inf > 0 else 0.0
        margin = capacity / required if required > 0 else float("inf")

        # device count needed to keep up in wall-clock terms
        compute_seconds = required * wl.latency_s(ac)
        units = compute_seconds / 86400.0
        if units > 1:
            notes.append(f"needs ~{units:,.1f} parallel {ac.name} units to keep "
                         f"up in real time")

        # --- 3. data through the link --------------------------------------
        gen_gb = gen_gb_src
        processed_frac = min(margin, 1.0)          # only what we can process
        out_gb = (required * processed_frac * wl.output_mb) / 1000.0
        # anything we cannot process must go down raw (or be dropped)
        unprocessed_gb = gen_gb * (1.0 - processed_frac)
        out_total = out_gb + unprocessed_gb
        cap_gb = self.link.gb_per_day
        link_margin = cap_gb / out_total if out_total > 0 else float("inf")
        required_reduction = gen_gb / cap_gb if cap_gb > 0 else float("inf")

        # --- 4. verdict: first failure wins --------------------------------
        if margin < 1.0:
            bottleneck = headroom
            feasible = False
            fix = ("radiator area" if headroom == "thermal" else "array area")
            msg = (f"{headroom.capitalize()}-bound. Processing needs "
                   f"{PlanResult._w(energy_required_w)} continuous but only "
                   f"{PlanResult._w(sustained)} is available - short {1/margin:,.1f}x. "
                   f"Increase {fix}, pick a leaner model, or drop the duty cycle.")
        elif link_margin < 1.0:
            bottleneck = "downlink"
            feasible = False
            msg = (f"Downlink-bound. Compute keeps up, but {out_total:,.2f} GB/day "
                   f"still needs to reach the ground against "
                   f"{cap_gb:,.1f} GB/day of capacity - cut output "
                   f"{1/link_margin:,.1f}x further, add passes, or move to a "
                   f"faster band.")
        else:
            bottleneck = "none"
            feasible = True
            msg = (f"Feasible. {required:,.0f} inferences/day fit in "
                   f"{PlanResult._w(energy_required_w)} of a "
                   f"{PlanResult._w(sustained)} envelope, "
                   f"and onboard reduction takes {gen_gb:,.1f} GB/day down to "
                   f"{out_total:,.2f} GB/day inside a {cap_gb:,.1f} GB/day link.")
            tight = min(margin, link_margin)
            if tight < 1.5:
                notes.append(f"margin is thin ({tight:,.2f}x) - little room for "
                             f"degradation or duty-cycle growth")

        return PlanResult(
            power_available_w=p_avail,
            thermal_limit_w=p_therm,
            sustained_compute_w=sustained,
            power_headroom=headroom,
            inferences_required_per_day=required,
            inferences_capacity_per_day=capacity,
            compute_margin=margin,
            energy_per_inference_j=e_inf,
            energy_required_w=energy_required_w,
            accelerators_needed=units,
            data_generated_gb_day=gen_gb,
            data_after_inference_gb_day=out_total,
            downlink_capacity_gb_day=cap_gb,
            link_margin=link_margin,
            achieved_reduction=wl.reduction_ratio,
            required_reduction=required_reduction,
            bottleneck=bottleneck,
            feasible=feasible,
            message=msg,
            notes=notes,
        )
