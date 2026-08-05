"""Where should this workload run -- in orbit, or on the ground?

orbitplan's planner answers "can this run in orbit?". This module answers the
harder commercial question: *should* it.

The comparison hinges on an asymmetry people routinely miss. Process in orbit
and you downlink a small result. Process on the ground and you must first
downlink **everything** -- and ground-station time is billed by the minute and
strictly rationed by orbital geometry. For data-heavy instruments the ground
option often isn't merely expensive, it is physically impossible: the contact
hours required exceed the contact hours that exist.

Reference prices are public list rates (AWS Ground Station, EC2 GPU instances)
and are overridable -- they date quickly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .constants import (
    GS_COST_PER_MIN, CLOUD_GPU_USD_PER_HOUR, CLOUD_GPU_TOPS,
    DEFAULT_UTILIZATION, LAUNCH_COST_PER_KG, DEFAULT_MISSION_YEARS,
)
from .budgets import LinkBudget
from .workload import Workload, Accelerator


@dataclass
class GroundOption:
    """Downlink everything raw, then compute in a terrestrial cloud."""
    gpu_usd_per_hour: float = CLOUD_GPU_USD_PER_HOUR
    gpu_tops: float = CLOUD_GPU_TOPS
    utilization: float = DEFAULT_UTILIZATION
    station_usd_per_min: float = GS_COST_PER_MIN

    def compute_usd_per_day(self, workload: Workload, inferences_per_day: float) -> float:
        ops = inferences_per_day * workload.ops
        dev_ops_s = self.gpu_tops * 1e12 * self.utilization
        gpu_hours = ops / dev_ops_s / 3600.0
        return gpu_hours * self.gpu_usd_per_hour

    def contact_hours_needed(self, gb_per_day: float, link: LinkBudget) -> float:
        """Hours of ground-station contact required to bring the raw data down."""
        bits = gb_per_day * 1e9 * 8
        return bits / (link.rate_bps * link.efficiency) / 3600.0

    def station_usd_per_day(self, gb_per_day: float, link: LinkBudget) -> float:
        return self.contact_hours_needed(gb_per_day, link) * 60.0 * self.station_usd_per_min


@dataclass
class OrbitOption:
    """Process onboard; downlink only the result."""
    payload_mass_kg: float = 25.0
    hardware_usd: float = 40_000.0        # space-qualified accelerator + avionics
    launch_usd_per_kg: float = LAUNCH_COST_PER_KG
    mission_years: float = DEFAULT_MISSION_YEARS
    station_usd_per_min: float = GS_COST_PER_MIN

    @property
    def capex_usd(self) -> float:
        return self.payload_mass_kg * self.launch_usd_per_kg + self.hardware_usd

    @property
    def amortised_usd_per_day(self) -> float:
        return self.capex_usd / (self.mission_years * 365.0)

    def station_usd_per_day(self, out_gb_per_day: float, link: LinkBudget) -> float:
        bits = out_gb_per_day * 1e9 * 8
        minutes = bits / (link.rate_bps * link.efficiency) / 60.0
        return minutes * self.station_usd_per_min


@dataclass
class PlacementResult:
    ground_station_usd_day: float
    ground_compute_usd_day: float
    ground_total_usd_day: float
    ground_contact_hours_needed: float
    ground_contact_hours_available: float
    ground_feasible: bool

    orbit_amortised_usd_day: float
    orbit_station_usd_day: float
    orbit_total_usd_day: float

    winner: str            # "orbit" | "ground"
    cost_ratio: float      # how many times cheaper the winner is
    crossover_gb_per_day: Optional[float]
    sensitivity_forced: bool
    message: str

    def _ratio_phrase(self) -> str:
        if self.cost_ratio >= 1:
            return f"{self.cost_ratio:,.1f}x cheaper"
        # only reachable when a constraint forces the pricier option
        return f"{1/self.cost_ratio:,.1f}x more expensive, accepted for compliance"

    def summary(self) -> str:
        L = [
            f"ground  : ${self.ground_total_usd_day:,.2f}/day "
            f"(station ${self.ground_station_usd_day:,.2f} + compute ${self.ground_compute_usd_day:,.2f})",
            f"          needs {self.ground_contact_hours_needed:,.2f} h of contact, "
            f"{self.ground_contact_hours_available:,.2f} h available"
            + ("" if self.ground_feasible else "  <-- IMPOSSIBLE"),
            f"orbit   : ${self.orbit_total_usd_day:,.2f}/day "
            f"(amortised ${self.orbit_amortised_usd_day:,.2f} + station ${self.orbit_station_usd_day:,.2f})",
            f"winner  : {self.winner} ({self._ratio_phrase()})",
        ]
        if self.crossover_gb_per_day:
            L.append(f"crossover: orbit wins above ~{self.crossover_gb_per_day:,.1f} GB/day")
        L.append(f"verdict : {self.message}")
        return "\n".join(L)


def compare_placement(
    workload: Workload,
    inferences_per_day: float,
    data_gb_per_day: float,
    link: LinkBudget,
    ground: GroundOption = None,
    orbit: OrbitOption = None,
    data_must_stay_onboard: bool = False,
) -> PlacementResult:
    """Compare running ``workload`` in orbit against downlinking and running it
    on the ground.

    ``data_must_stay_onboard`` models a sovereignty / sensitivity constraint:
    if the raw data may not transit third-party ground stations, the ground
    option is disqualified regardless of price.
    """
    ground = ground or GroundOption()
    orbit = orbit or OrbitOption()

    # --- ground: downlink everything, then compute ---
    g_hours_needed = ground.contact_hours_needed(data_gb_per_day, link)
    g_hours_avail = (link.contact_s * link.passes_per_day) / 3600.0
    g_station = ground.station_usd_per_day(data_gb_per_day, link)
    g_compute = ground.compute_usd_per_day(workload, inferences_per_day)
    g_total = g_station + g_compute
    g_feasible = g_hours_needed <= g_hours_avail

    # --- orbit: process, downlink the result ---
    out_gb = inferences_per_day * workload.output_mb / 1000.0
    o_amort = orbit.amortised_usd_per_day
    o_station = orbit.station_usd_per_day(out_gb, link)
    o_total = o_amort + o_station

    # --- crossover: data volume at which orbit becomes cheaper ---
    # ground scales linearly with volume; orbit is dominated by fixed capex
    per_gb = (ground.station_usd_per_day(1.0, link)
              + ground.compute_usd_per_day(workload, 1000.0 / workload.input_mb)
              if workload.input_mb > 0 else 0.0)
    crossover = (o_total / per_gb) if per_gb > 0 else None

    # --- verdict ---
    if data_must_stay_onboard:
        winner, ratio, forced = "orbit", (g_total / o_total if o_total else float("inf")), True
        msg = ("Orbit, by constraint. The raw data may not transit third-party "
               "ground stations, so processing onboard is the only compliant "
               f"option (it also happens to cost ${o_total:,.2f}/day vs "
               f"${g_total:,.2f}).")
    elif not g_feasible:
        winner, ratio, forced = "orbit", (g_total / o_total if o_total else float("inf")), False
        msg = (f"Orbit, and the ground option is not merely expensive - it is "
               f"impossible. Downlinking {data_gb_per_day:,.0f} GB/day needs "
               f"{g_hours_needed:,.1f} h of contact against {g_hours_avail:,.2f} h "
               f"available. The data physically cannot come down.")
    elif o_total < g_total:
        winner, ratio, forced = "orbit", g_total / o_total, False
        msg = (f"Orbit, {g_total/o_total:,.1f}x cheaper. Ground-station minutes to "
               f"bring {data_gb_per_day:,.0f} GB/day down (${g_station:,.2f}/day) "
               f"dominate everything else.")
    else:
        winner, ratio, forced = "ground", (o_total / g_total if g_total else float("inf")), False
        msg = (f"Ground, {o_total/g_total:,.1f}x cheaper. At {data_gb_per_day:,.1f} GB/day "
               f"there isn't enough data to justify amortising "
               f"${orbit.capex_usd:,.0f} of hardware and launch. Downlink it and "
               f"use the cloud.")

    return PlacementResult(
        ground_station_usd_day=g_station,
        ground_compute_usd_day=g_compute,
        ground_total_usd_day=g_total,
        ground_contact_hours_needed=g_hours_needed,
        ground_contact_hours_available=g_hours_avail,
        ground_feasible=g_feasible,
        orbit_amortised_usd_day=o_amort,
        orbit_station_usd_day=o_station,
        orbit_total_usd_day=o_total,
        winner=winner,
        cost_ratio=ratio,
        crossover_gb_per_day=crossover,
        sensitivity_forced=forced,
        message=msg,
    )
