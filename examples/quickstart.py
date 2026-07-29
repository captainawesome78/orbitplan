"""Run: python examples/quickstart.py"""
import orbitplan as op


def show(title, plan):
    print("=" * 72)
    print(title)
    print("=" * 72)
    r = plan.evaluate()
    print(r.summary())
    for n in r.notes:
        print(f"  note: {n}")
    print()


# --- 1. SAR satellite: the canonical downlink problem ----------------------
show("CASE 1  SAR sat, onboard segmentation (400x reduction)",
     op.MissionPlan(
         sensor=op.Sensor(burst_gb_per_s=10, duty_cycle=0.002, name="SAR"),
         workload=op.Workload.preset("sar_segmenter", input_mb=800, output_mb=2),
         accelerator=op.Accelerator.preset("jetson_agx_orin"),
         power=op.PowerBudget(array_area_m2=8),
         thermal=op.ThermalBudget(radiator_area_m2=2),
         link=op.LinkBudget(band="x_band"),
     ))

# --- 2. same sensor, no onboard processing: downlink everything raw --------
show("CASE 2  same sat, raw downlink (no onboard inference)",
     op.MissionPlan(
         sensor=op.Sensor(burst_gb_per_s=10, duty_cycle=0.002, name="SAR"),
         workload=op.Workload.preset("sar_segmenter", input_mb=800, output_mb=800),
         accelerator=op.Accelerator.preset("jetson_agx_orin"),
         power=op.PowerBudget(array_area_m2=8),
         thermal=op.ThermalBudget(radiator_area_m2=2),
         link=op.LinkBudget(band="x_band"),
     ))

# --- 3. orbital LLM serving: thermal wall --------------------------------
show("CASE 3  orbital LLM serving - big array, undersized radiator",
     op.MissionPlan(
         sensor=None,
         demand_per_day=2.0e11,                      # 200B tokens/day
         workload=op.Workload.preset("llm_1b_token", input_mb=0.002,
                                     output_mb=0.002),
         accelerator=op.Accelerator.preset("nvidia_h100"),
         power=op.PowerBudget(array_area_m2=40),
         thermal=op.ThermalBudget(radiator_area_m2=1.5),
         link=op.LinkBudget(band="optical"),
     ))

# --- 4. power-starved cubesat --------------------------------------------
show("CASE 4  cubesat - undersized array for a heavy model",
     op.MissionPlan(
         sensor=op.Sensor(gb_per_day=9000, name="video"),
         workload=op.Workload.preset("yolov8m", input_mb=6, output_mb=0.01),
         accelerator=op.Accelerator.preset("jetson_orin_nx"),
         power=op.PowerBudget(array_area_m2=0.25),
         thermal=op.ThermalBudget(radiator_area_m2=2.0),
         link=op.LinkBudget(band="x_band"),
     ))

# --- 5. a configuration that actually closes ------------------------------
show("CASE 5  balanced design - everything fits",
     op.MissionPlan(
         sensor=op.Sensor(gb_per_day=300, name="optical"),
         workload=op.Workload.preset("resnet50", input_mb=6, output_mb=0.005),
         accelerator=op.Accelerator.preset("jetson_agx_orin"),
         power=op.PowerBudget(array_area_m2=2.0),
         thermal=op.ThermalBudget(radiator_area_m2=1.0),
         link=op.LinkBudget(band="x_band"),
     ))

