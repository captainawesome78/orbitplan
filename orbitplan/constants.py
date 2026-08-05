"""Reference figures for orbital inference planning.

All SI unless noted. These are first-order engineering values drawn from public
hardware specs and standard link/power budgets -- good for feasibility triage,
not for flight design.
"""

# --- Orbit / environment ---
MU_EARTH = 3.986004418e14      # m^3/s^2
R_EARTH = 6.371e6              # m
SOLAR_CONSTANT = 1361.0        # W/m^2

# --- Power subsystem ---
SOLAR_CELL_EFFICIENCY = 0.30   # triple-junction space cells
ARRAY_PACKING_FACTOR = 0.85    # usable cell area / panel area
BATTERY_ROUND_TRIP = 0.85      # charge/discharge efficiency
PMAD_EFFICIENCY = 0.90         # power management & distribution losses
BUS_POWER_OVERHEAD_W = 30.0    # ADCS, comms, C&DH baseline draw

# --- Accelerator efficiency (INT8 TOPS per watt, peak) ---
# Real utilization is far below peak; see DEFAULT_UTILIZATION.
ACCELERATORS = {
    "jetson_orin_nx": {"tops": 100.0, "watts": 25.0},
    "jetson_agx_orin": {"tops": 275.0, "watts": 60.0},
    "nvidia_l4": {"tops": 485.0, "watts": 72.0},
    "nvidia_h100": {"tops": 1979.0, "watts": 700.0},
}
DEFAULT_UTILIZATION = 0.40     # fraction of peak TOPS actually achieved

# --- Downlink (bits/second) ---
DOWNLINK_RATES = {
    "s_band": 10e6,
    "x_band": 300e6,
    "ka_band": 1.2e9,
    "optical": 10e9,
}
DEFAULT_CONTACT_S = 480.0      # ~8 min usable per ground station pass
DEFAULT_PASSES_PER_DAY = 5     # typical single-station LEO access

# --- Thermal (mirrors orbitherm defaults; used only in fallback) ---
STEFAN_BOLTZMANN = 5.670374419e-8
DEFAULT_EMISSIVITY = 0.85
DEFAULT_RADIATOR_TEMP_C = 50.0

# --- Reference workloads (INT8 giga-ops per inference) ---
WORKLOADS = {
    "resnet50": 8.0,
    "vit_b16": 35.0,
    "yolov8m": 80.0,
    "sar_segmenter": 200.0,
    "llm_1b_token": 2.0,
}

# --- Inter-satellite laser links ---
DEFAULT_ISL_RATE = 100e9       # bits/s per optical terminal (operational-class)
DEFAULT_ISL_DUTY = 0.70        # fraction of orbit with a usable relay path

# --- Placement economics (public list prices; override as they date) ---
GS_COST_PER_MIN = 10.0            # USD/min, AWS Ground Station wideband reserved
CLOUD_GPU_USD_PER_HOUR = 1.006    # USD/hr, EC2 g5.xlarge (A10G) on-demand
CLOUD_GPU_TOPS = 250.0            # A10G INT8
LAUNCH_COST_PER_KG = 1000.0       # USD/kg to LEO (order of magnitude, 2026)
DEFAULT_MISSION_YEARS = 5.0
