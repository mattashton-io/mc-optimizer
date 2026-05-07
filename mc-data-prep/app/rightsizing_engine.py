import math

# Geomean benchmark scores per series (N1 is baseline with score of 1)
GEOMEAN_SCORES = {
    "c2": 1.41,
    "c2d": 1.45,
    "c3": 2.02,
    "c3d": 1.67,
    "c4": 2.43,
    "c4a": 3.08,
    "c4d": 3.05,
    "e2": 0.93,
    "m1": 0.88,
    "m2": 0.87,
    "m3": 1.28,
    "m4": 1.45,
    "n1": 1.0,
    "n2": 1.61,
    "n2d": 1.20,
    "n4": 2.10,
    "t2a": 1.27,
    "t2d": 1.68,
}

PASSMARK_TO_GEOMEAN_FACTOR = 0.001390

def calculate_required_cores(source_cores: float, source_passmark: float, target_series: str) -> float:
    """Calculates the required GCP cores based on performance benchmarks."""
    target_geomean = GEOMEAN_SCORES.get(target_series.lower(), 1.0)
    return source_cores * (source_passmark / target_geomean) * PASSMARK_TO_GEOMEAN_FACTOR

def rightsize_cores(required_cores: float, source_utilization: float, target_utilization: float = 0.75) -> float:
    """Adjusts cores based on utilization data and target preference."""
    if target_utilization <= 0:
        raise ValueError("Target utilization must be greater than 0")
    return (required_cores * source_utilization) / target_utilization

def rightsize_disk(source_disk_gb: float, source_utilization: float, headroom_factor: float = 0.8) -> float:
    """Adjusts disk capacity based on utilization and headroom (default 25% uplift)."""
    if headroom_factor <= 0:
        raise ValueError("Headroom factor must be greater than 0")
    return (source_disk_gb * source_utilization) / headroom_factor

def get_next_instance_shape(cores: float, ram_gb: float, series: str) -> str:
    """
    Mock function to determine the next available instance shape.
    In a real implementation, this would look up actual GCP machine types.
    """
    # Simple rounding for demonstration based on common shapes
    rounded_cores = 2 ** math.ceil(math.log2(cores)) if cores > 2 else (1 if cores <= 1 else 2)
    return f"{series.upper()}-Standard-{rounded_cores}"

def run_airlift_estimate(
    total_source_vcpus: float,
    total_source_ram_gb: float,
    total_source_disk_gb: float,
    cpu_util_factor: float = 0.2270,
    ram_util_factor: float = 0.3572,
    disk_util_factor: float = 0.39,
    headroom_percent: float = 0.20,
    vapor_benchmarking_factor: float = 1.5, # Default performance improvement
):
    """
    Performs a top-down Airlift Quick Estimate on aggregated data.
    """
    # 1. Apply Rightsizing (Utilization)
    rs_vcpus = total_source_vcpus * cpu_util_factor
    rs_ram = total_source_ram_gb * ram_util_factor
    rs_disk = total_source_disk_gb * disk_util_factor
    
    # 2. Apply Vapor Benchmarking (Performance improvement of cloud hardware)
    # Fewer cloud vCPUs are needed for the same workload
    final_vcpus = rs_vcpus / vapor_benchmarking_factor
    
    # 3. Apply Headroom
    final_vcpus *= (1 + headroom_percent)
    final_ram = rs_ram * (1 + headroom_percent)
    final_disk = rs_disk * (1 + headroom_percent)
    
    return {
        "estimated_gcp_vcpus": round(final_vcpus, 2),
        "estimated_gcp_ram_gb": round(final_ram, 2),
        "estimated_gcp_disk_gb": round(final_disk, 2),
    }

def run_vm_assessment(
    source_cores: float,
    source_ram_gb: float,
    source_disk_gb: float,
    source_passmark: float,
    cpu_util: float,
    disk_util: float,
    target_series: str,
    target_cpu_util: float = 0.75,
    smt_off: bool = False
):
    """Runs a full assessment for a single VM."""
    req_cores = calculate_required_cores(source_cores, source_passmark, target_series)
    rs_cores = rightsize_cores(req_cores, cpu_util, target_cpu_util)
    
    if smt_off:
        # 25% CPU compensation for SMT-Off
        rs_cores *= 1.25
        
    rs_disk = rightsize_disk(source_disk_gb, disk_util)
    
    # Example logic for RAM rightsizing (doc says 33% avg util, but doesn't give a specific formula)
    # We'll use a similar logic to CPU for now or just keep it like-for-like if util is not provided
    rs_ram = source_ram_gb # Placeholder
    
    shape = get_next_instance_shape(rs_cores, rs_ram, target_series)
    
    return {
        "target_shape": shape,
        "rightsized_cores": round(rs_cores, 2),
        "rightsized_disk_gb": round(rs_disk, 2),
        "required_cores_before_rs": round(req_cores, 2)
    }
