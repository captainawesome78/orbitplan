"""The three orbital constraints, each as an independent budget.

Power  -- how much energy the spacecraft can give the compute payload.
Thermal-- how much heat that payload can actually shed (the real ceiling).
Link   -- how much data can reach the ground, and therefore how much must be
          reduced onboard.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .constants import (
    MU_EARTH, R_EARTH, SOLAR_CONSTANT, SOLAR_CELL_EFFICIENCY,
    ARRAY_PACKING_FACTOR, BATTERY_ROUND_TRIP, PMAD_EFFICIENCY,
    BUS_POWER_OVERHEAD_W, STEFAN_BOLTZMANN, DEFAULT_EMISSIVITY,
    DEFAULT_RADIATOR_TEMP_C, DOWNLINK_RATES, DEFAULT_CONTACT_S,
    DEFAULT_PASSES_PER_DAY,
)


# ---------------------------------------------------------------- orbit ----
@dataclass
class Orbit:
    """Circular LEO orbit."""
    altitude_km: float = 550.0

    @property
    def period_s(self) -> float:
        a = R_EARTH + self.altitude_km * 1000.0
        return 2 * math.pi * math.sqrt(a ** 3 / MU_EARTH)

    @property
    def eclipse_fraction(self) -> float:
        a = R_EARTH + self.altitude_km * 1000.0
        return (2 * math.asin(R_EARTH / a)) / (2 * math.pi)

    @property
    def orbits_per_day(self) -> float:
        return 86400.0 / self.period_s


# ---------------------------------------------------------------- power ----
@dataclass
class PowerBudget:
    """Solar array + battery. Returns the watts available to compute."""
    array_area_m2: float
    orbit: Orbit = None
    cell_efficiency: float = SOLAR_CELL_EFFICIENCY
    bus_overhead_w: float = BUS_POWER_OVERHEAD_W

    def __post_init__(self):
        if self.orbit is None:
            self.orbit = Orbit()

    @property
    def peak_w(self) -> float:
        """Array output while sunlit."""
        return (SOLAR_CONSTANT * self.cell_efficiency
                * ARRAY_PACKING_FACTOR * self.array_area_m2)

    @property
    def orbit_average_w(self) -> float:
        """Continuous power after eclipse, battery and PMAD losses."""
        ecl = self.orbit.eclipse_fraction
        sunlit = 1.0 - ecl
        # energy harvested only while sunlit; the eclipse share is delivered
        # through the battery and pays the round-trip penalty
        direct = self.peak_w * sunlit * sunlit
        stored = self.peak_w * sunlit * ecl * BATTERY_ROUND_TRIP
        return (direct + stored) * PMAD_EFFICIENCY

    @property
    def compute_w(self) -> float:
        """Watts left for the inference payload after the bus takes its cut."""
        return max(self.orbit_average_w - self.bus_overhead_w, 0.0)


# -------------------------------------------------------------- thermal ----
def _fallback_max_power(area_m2: float, temp_c: float, emissivity: float) -> float:
    t_k = temp_c + 273.15
    return emissivity * STEFAN_BOLTZMANN * area_m2 * t_k ** 4


@dataclass
class ThermalBudget:
    """Heat-rejection ceiling on sustained compute power.

    Uses :mod:`orbitherm` when installed (richer environment model); otherwise
    falls back to a bare Stefan-Boltzmann estimate.
    """
    radiator_area_m2: float
    radiator_temp_c: float = DEFAULT_RADIATOR_TEMP_C
    emissivity: float = DEFAULT_EMISSIVITY
    orientation: str = "deep_space"

    @property
    def backend(self) -> str:
        try:
            import orbitherm  # noqa: F401
            return "orbitherm"
        except ImportError:
            return "builtin"

    @property
    def max_compute_w(self) -> float:
        """Largest dissipation this radiator can shed at ``radiator_temp_c``."""
        try:
            from orbitherm import physics as _p
            env = _p.environmental_flux(self.orientation, self.emissivity)
            net = _p.radiative_flux(_p.c_to_k(self.radiator_temp_c),
                                    self.emissivity) - env
            return max(net, 0.0) * self.radiator_area_m2
        except ImportError:
            return _fallback_max_power(self.radiator_area_m2,
                                       self.radiator_temp_c, self.emissivity)


# ----------------------------------------------------------------- link ----
@dataclass
class LinkBudget:
    """Ground-contact capacity -- the ceiling on what can be downlinked raw."""
    band: str = "x_band"
    rate_bps: float = None
    contact_s: float = DEFAULT_CONTACT_S
    passes_per_day: int = DEFAULT_PASSES_PER_DAY
    efficiency: float = 0.80          # coding/protocol overhead

    def __post_init__(self):
        if self.rate_bps is None:
            if self.band not in DOWNLINK_RATES:
                raise ValueError(f"unknown band {self.band!r}; "
                                 f"choose from {sorted(DOWNLINK_RATES)} "
                                 f"or pass rate_bps")
            self.rate_bps = DOWNLINK_RATES[self.band]

    @property
    def bytes_per_day(self) -> float:
        return (self.rate_bps * self.contact_s * self.passes_per_day
                * self.efficiency / 8.0)

    @property
    def gb_per_day(self) -> float:
        return self.bytes_per_day / 1e9
