"""The inference workload and the accelerator that runs it."""
from __future__ import annotations

from dataclasses import dataclass

from .constants import ACCELERATORS, DEFAULT_UTILIZATION, WORKLOADS


@dataclass
class Accelerator:
    """Compute device. ``tops`` is peak INT8; real throughput is derated by
    ``utilization``, which is where most naive orbital estimates go wrong."""
    tops: float
    watts: float
    utilization: float = DEFAULT_UTILIZATION
    name: str = "custom"

    @classmethod
    def preset(cls, key: str, utilization: float = DEFAULT_UTILIZATION) -> "Accelerator":
        if key not in ACCELERATORS:
            raise ValueError(f"unknown accelerator {key!r}; "
                             f"choose from {sorted(ACCELERATORS)}")
        spec = ACCELERATORS[key]
        return cls(tops=spec["tops"], watts=spec["watts"],
                   utilization=utilization, name=key)

    @property
    def effective_ops_per_s(self) -> float:
        return self.tops * 1e12 * self.utilization

    @property
    def ops_per_joule(self) -> float:
        """Effective operations per joule -- the number that sets energy cost."""
        return self.effective_ops_per_s / self.watts


@dataclass
class Workload:
    """One inference task.

    ``gops`` is giga-ops per inference. ``input_mb`` is the raw data each
    inference consumes (what you'd otherwise downlink); ``output_mb`` is what
    the result costs to send instead -- their ratio is the whole argument for
    processing onboard.
    """
    gops: float
    input_mb: float = 0.0
    output_mb: float = 0.0
    name: str = "custom"

    @classmethod
    def preset(cls, key: str, **kw) -> "Workload":
        if key not in WORKLOADS:
            raise ValueError(f"unknown workload {key!r}; "
                             f"choose from {sorted(WORKLOADS)}")
        return cls(gops=WORKLOADS[key], name=key, **kw)

    @property
    def ops(self) -> float:
        return self.gops * 1e9

    @property
    def reduction_ratio(self) -> float:
        """How many times smaller the result is than the raw input."""
        if self.output_mb <= 0:
            return float("inf")
        return self.input_mb / self.output_mb

    def energy_j(self, accel: Accelerator) -> float:
        """Energy for a single inference on ``accel`` (joules)."""
        return self.ops / accel.ops_per_joule

    def latency_s(self, accel: Accelerator) -> float:
        """Wall-clock time for a single inference (seconds)."""
        return self.ops / accel.effective_ops_per_s
