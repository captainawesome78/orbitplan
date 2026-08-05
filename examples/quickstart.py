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



# --- 6. does an inter-satellite laser mesh rescue the raw-downlink case? ----
print("=" * 72)
print("CASE 6  laser mesh relay - does reach beat storage?")
print("=" * 72)
for label, link in [
    ("direct X-band only",
     op.LinkBudget(band="x_band")),
    ("mesh: 100 sats / 10 stations",
     op.LinkBudget(band="x_band",
                   relay=op.RelayLink(constellation_size=100, ground_stations=10))),
    ("mesh: 20 sats / 30 stations",
     op.LinkBudget(band="x_band",
                   relay=op.RelayLink(constellation_size=20, ground_stations=30))),
]:
    r = op.MissionPlan(
        sensor=op.Sensor(burst_gb_per_s=10, duty_cycle=0.002),
        workload=op.Workload.preset("sar_segmenter", input_mb=800, output_mb=800),
        accelerator=op.Accelerator.preset("jetson_agx_orin"),
        power=op.PowerBudget(array_area_m2=8),
        thermal=op.ThermalBudget(radiator_area_m2=2),
        link=link,
    ).evaluate()
    print(f"  {label:30s} {r.downlink_capacity_gb_day:9.1f} GB/day -> {r.bottleneck}")
    if link.relay:
        print(f"  {'':30s} limited by the {link.relay.limiting_factor}")
print()

# --- 7. should this run in orbit at all? ------------------------------------
print("=" * 72)
print("CASE 7  placement economics - orbit vs terrestrial cloud")
print("=" * 72)
link = op.LinkBudget(band="x_band")
for label, wl, n, gb in [
    ("SAR, 1,728 GB/day",
     op.Workload.preset("sar_segmenter", input_mb=800, output_mb=2), 2160, 1728),
    ("cubesat, 5 GB/day",
     op.Workload.preset("resnet50", input_mb=6, output_mb=0.005), 833, 5),
]:
    r = op.compare_placement(workload=wl, inferences_per_day=n,
                             data_gb_per_day=gb, link=link)
    print(f"\n-- {label}")
    print(r.summary())

print("\n-- same cubesat, but the data may not leave the spacecraft")
r = op.compare_placement(
    workload=op.Workload.preset("resnet50", input_mb=6, output_mb=0.005),
    inferences_per_day=833, data_gb_per_day=5, link=link,
    data_must_stay_onboard=True)
print(r.message)
print()
