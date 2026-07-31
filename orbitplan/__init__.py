"""orbitplan -- feasibility planner for inference in orbit.

Three constraints decide whether a model can run in space, and they fight each
other: the array must make the power, the radiator must shed the resulting
heat, and the ground link must carry whatever data survives. orbitplan
reconciles all three and names the one that is actually stopping you.

Handles both ground-pass downlink and inter-satellite laser relay, so you can
ask whether a crosslink mesh actually rescues a downlink-bound design.

Pairs with:
  * orbitherm  -- sizes the radiator (used automatically when installed)
  * radshield  -- keeps the model correct under radiation-induced bit flips

Quick start
-----------
    import orbitplan as op

    plan = op.MissionPlan(
        sensor=op.Sensor(burst_gb_per_s=10, duty_cycle=0.002),   # SAR
        workload=op.Workload.preset("sar_segmenter", input_mb=800, output_mb=2),
        accelerator=op.Accelerator.preset("jetson_agx_orin"),
        power=op.PowerBudget(array_area_m2=8),
        thermal=op.ThermalBudget(radiator_area_m2=2),
        link=op.LinkBudget(band="x_band"),
    )
    print(plan.evaluate().summary())
"""

from .budgets import Orbit, PowerBudget, ThermalBudget, LinkBudget, RelayLink
from .workload import Accelerator, Workload
from .planner import MissionPlan, PlanResult, Sensor
from . import constants

__all__ = [
    "Orbit", "PowerBudget", "ThermalBudget", "LinkBudget", "RelayLink",
    "Accelerator", "Workload", "Sensor", "MissionPlan", "PlanResult", "constants",
]
__version__ = "0.2.0"
