import unittest
from rightsizing_engine import (
    calculate_required_cores,
    rightsize_cores,
    rightsize_disk,
    run_vm_assessment,
    run_airlift_estimate
)

class TestRightsizingEngine(unittest.TestCase):
    def test_example_vm_assessment(self):
        """
        Tests the calculation logic using the example in rightsizing.txt:
        Source: 16 cores, 750 passmark, US-Central-1, C4D Turin (3.05 geomean), 
        50% CPU util, 40% Disk util (20GB source disk).
        Target: C4D-Standard-4, 10GB disk.
        """
        source_cores = 16
        source_passmark = 750
        target_series = "c4d"
        cpu_util = 0.5
        disk_util = 0.4
        source_disk_gb = 20
        
        # 1. Required cores before rightsizing
        # Formula: 16 x (750 / 3.05) * 0.00139 = 5.4688...
        req_cores = calculate_required_cores(source_cores, source_passmark, target_series)
        self.assertAlmostEqual(req_cores, 5.46885, places=4)
        
        # 2. Rightsizing to 75% target utilization
        # Formula: (5.4688 x 0.5) / 0.75 = 3.6458...
        rs_cores = rightsize_cores(req_cores, cpu_util, 0.75)
        self.assertAlmostEqual(rs_cores, 3.6459, places=4)
        
        # 3. Disk rightsizing with 25% uplift (0.8 factor)
        # Formula: (20GB x 0.4) / 0.8 = 10GB
        rs_disk = rightsize_disk(source_disk_gb, disk_util, 0.8)
        self.assertEqual(rs_disk, 10.0)
        
        # 4. Full assessment
        result = run_vm_assessment(
            source_cores=source_cores,
            source_ram_gb=32,
            source_disk_gb=source_disk_gb,
            source_passmark=source_passmark,
            cpu_util=cpu_util,
            disk_util=disk_util,
            target_series=target_series
        )
        
        self.assertEqual(result["target_shape"], "C4D-Standard-4")
        self.assertEqual(result["rightsized_cores"], 3.65)
        self.assertEqual(result["rightsized_disk_gb"], 10.0)

    def test_airlift_estimate(self):
        """Tests the Airlift top-down estimation logic."""
        # Example aggregate data
        result = run_airlift_estimate(
            total_source_vcpus=1000,
            total_source_ram_gb=4000,
            total_source_disk_gb=10000
        )
        
        # CPU: (1000 * 0.2270) / 1.5 * 1.2 = 181.6
        self.assertAlmostEqual(result["estimated_gcp_vcpus"], 181.6)
        
        # RAM: (4000 * 0.3572) * 1.2 = 1714.56
        self.assertAlmostEqual(result["estimated_gcp_ram_gb"], 1714.56)
        
        # Disk: (10000 * 0.39) * 1.2 = 4680
        self.assertAlmostEqual(result["estimated_gcp_disk_gb"], 4680.0)

if __name__ == "__main__":
    unittest.main()
