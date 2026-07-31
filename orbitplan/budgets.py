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
    DEFAULT_PASSES_PER_DAY, DEFAULT_ISL_RATE, DEFAULT_ISL_DUTY,
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
class RelayLink:
    """Inter-satellite laser relay (crosslink mesh).

    A mesh does not create bandwidth -- it creates *reach*. Instead of storing
    data until this satellite flies over a station, it hands the data to a
    neighbour that can see one now. Two things therefore cap it:

    1. the crosslink itself (``isl_rate_bps`` while a usable path exists), and
    2. this satellite's fair share of the constellation's total ground pipe.

    The second is the one people forget: relaying through 100 satellites into
    10 ground stations still only buys you a tenth of ten stations. If the
    ground segment is thin, a mesh moves the bottleneck rather than removing it.
    """
    isl_rate_bps: float = DEFAULT_ISL_RATE
    isl_duty: float = DEFAULT_ISL_DUTY        # fraction of orbit with a usable path
    constellation_size: int = 100             # satellites sharing the ground segment
    ground_stations: int = 10
    station_rate_bps: float = None            # defaults to Ka-band
    station_availability: float = 0.60        # weather/scheduling/horizon losses
    efficiency: float = 0.80

    def __post_init__(self):
        if self.station_rate_bps is None:
            self.station_rate_bps = DOWNLINK_RATES["ka_band"]
        if self.constellation_size < 1:
            raise ValueError("constellation_size must be >= 1")

    @property
    def isl_limit_gb_per_day(self) -> float:
        """What the crosslink alone could carry."""
        return (self.isl_rate_bps * 86400.0 * self.isl_duty
                * self.efficiency / 8.0) / 1e9

    @property
    def ground_share_gb_per_day(self) -> float:
        """This satellite's share of the constellation's total ground capacity."""
        pool = (self.station_rate_bps * self.ground_stations * 86400.0
                * self.station_availability * self.efficiency / 8.0) / 1e9
        return pool / self.constellation_size

    @property
    def gb_per_day(self) -> float:
        return min(self.isl_limit_gb_per_day, self.ground_share_gb_per_day)

    @property
    def limiting_factor(self) -> str:
        return ("crosslink" if self.isl_limit_gb_per_day
                < self.ground_share_gb_per_day else "ground segment")


@dataclass
class LinkBudget:
    """Capacity to get data down: direct ground passes, plus optional ISL relay."""
    band: str = "x_band"
    rate_bps: float = None
    contact_s: float = DEFAULT_CONTACT_S
    passes_per_day: int = DEFAULT_PASSES_PER_DAY
    efficiency: float = 0.80          # coding/protocol overhead
    relay: "RelayLink" = None         # set to model a laser crosslink mesh

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
    def direct_gb_per_day(self) -> float:
        """Capacity from this satellite's own ground passes."""
        return self.bytes_per_day / 1e9

    @property
    def relay_gb_per_day(self) -> float:
        """Additional capacity contributed by the crosslink mesh."""
        return self.relay.gb_per_day if self.relay else 0.0

    @property
    def gb_per_day(self) -> float:
        """Total usable downlink capacity per day."""
        return self.direct_gb_per_day + self.relay_gb_per_day
