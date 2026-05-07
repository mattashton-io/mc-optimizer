import os
import logging
import time
import argparse
from typing import List
from dotenv import load_dotenv
from google.cloud import migrationcenter_v1
from google.api_core import exceptions
import rightsizing_engine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def generate_tco_reports():
    # 1. Environment Configuration
    load_dotenv()
    
    project_id = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_LOCATION")
    group_id = os.getenv("MIGRATION_CENTER_GROUP_ID")
    preference_set_ids_raw = os.getenv("PREFERENCE_SET_IDS", "")
    
    if not all([project_id, location, group_id, preference_set_ids_raw]):
        logger.error("Missing required environment variables in .env file (GCP_PROJECT_ID, GCP_LOCATION, MIGRATION_CENTER_GROUP_ID, PREFERENCE_SET_IDS).")
        return

    preference_set_ids = [pid.strip() for pid in preference_set_ids_raw.split(",") if pid.strip()]
    
    # Initialize Migration Center Client
    try:
        client = migrationcenter_v1.MigrationCenterClient()
    except Exception as e:
        logger.error(f"Failed to initialize Migration Center client: {e}")
        return

    parent = f"projects/{project_id}/locations/{location}"
    group_path = f"{parent}/groups/{group_id}"

    logger.info(f"Starting TCO report generation for Group: {group_id}")
    logger.info(f"Preference Sets to process: {preference_set_ids}")

    for pref_id in preference_set_ids:
        pref_id_clean = pref_id.lower().replace("_", "-")
        pref_set_path = f"{parent}/preferenceSets/{pref_id_clean}"
        timestamp = int(time.time())
        report_config_id = f"tco-config-{pref_id_clean}-{timestamp}"
        report_id = f"tco-report-{pref_id_clean}-{timestamp}"

        try:
            # 2. Report Configuration: Create dynamic ReportConfig
            logger.info(f"Creating ReportConfig: {report_config_id} using Preference Set: {pref_id}")
            
            report_config = migrationcenter_v1.ReportConfig(
                display_name=f"TCO Config for {pref_id}",
                group_preferenceset_assignments=[
                    migrationcenter_v1.ReportConfig.GroupPreferenceSetAssignment(
                        group=group_path,
                        preference_set=pref_set_path
                    )
                ]
            )

            config_operation = client.create_report_config(
                request={
                    "parent": parent,
                    "report_config_id": report_config_id,
                    "report_config": report_config,
                }
            )
            
            # Wait for ReportConfig creation LRO
            logger.info(f"Waiting for ReportConfig {report_config_id} to be created...")
            config_result = config_operation.result()
            config_name = config_result.name

            # 3. Report Generation: Trigger Report creation
            logger.info(f"Triggering Report generation: {report_id}")
            
            report = migrationcenter_v1.Report(
                display_name=f"TCO Report for {pref_id}",
                description=f"Automated TCO report for preference set {pref_id}",
                type_=migrationcenter_v1.Report.Type.TOTAL_COST_OF_OWNERSHIP
            )

            report_operation = client.create_report(
                request={
                    "parent": config_name,
                    "report_id": report_id,
                    "report": report,
                }
            )

            # Handle Long-Running Operations (LROs) gracefully
            logger.info(f"Waiting for Report {report_id} to finish computing...")
            report_result = report_operation.result()
            report_name = report_result.name

            # 4. Output Summary: Fetch ReportSummary
            logger.info(f"Fetching summary for report: {report_id}")
            
            # The summary is part of the Report object after it finishes computing
            summary = report_result.summary
            
            def format_money(m):
                # Google Money type: units is int64, nanos is int32
                amount = m.units + (m.nanos / 1_000_000_000)
                return f"{amount:,.2f} {m.currency_code}"

            print("\n" + "="*60)
            print(f"REPORT SUMMARY: {pref_id}")
            print(f"Report Path: {report_name}")
            print("-" * 60)
            
            # Iterate through group findings and preference set findings
            found_data = False
            for group_finding in summary.group_findings:
                for ps_finding in group_finding.preference_set_findings:
                    print(f"Variant: {ps_finding.display_name}")
                    print(f"Monthly Total TCO:    {format_money(ps_finding.monthly_cost_total)}")
                    print(f"Monthly Compute Cost: {format_money(ps_finding.monthly_cost_compute)}")
                    print(f"Monthly Storage Cost: {format_money(ps_finding.monthly_cost_storage)}")
                    print("-" * 60)
                    found_data = True
            
            if not found_data:
                logger.warning(f"No cost data found in report summary for {pref_id}")
            
            print("="*60 + "\n")

        except exceptions.GoogleAPICallError as e:
            logger.error(f"Google API error for preference set {pref_id}: {e}")
        except exceptions.RetryError as e:
            logger.error(f"Retry error for preference set {pref_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error for preference set {pref_id}: {e}")

def main():
    parser = argparse.ArgumentParser(description="GCP Migration Center TCO and Rightsizing Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: mc-report
    subparsers.add_parser("mc-report", help="Trigger TCO reports in Migration Center (requires .env config)")

    # Command: assessment
    assess_parser = subparsers.add_parser("assessment", help="Perform manual VM assessment using benchmark logic")
    assess_parser.add_argument("--cores", type=float, default=16, help="Source vCPUs")
    assess_parser.add_argument("--ram", type=float, default=32, help="Source RAM (GiB)")
    assess_parser.add_argument("--disk", type=float, default=20, help="Source Disk (GB)")
    assess_parser.add_argument("--passmark", type=float, default=750, help="Source CPU Passmark score")
    assess_parser.add_argument("--cpu-util", type=float, default=0.5, help="Source CPU utilization (0.0 - 1.0)")
    assess_parser.add_argument("--disk-util", type=float, default=0.4, help="Source Disk utilization (0.0 - 1.0)")
    assess_parser.add_argument("--target-series", type=str, default="c4d", help="Target GCE machine series (e.g. c4d, n2, c3)")
    assess_parser.add_argument("--smt-off", action="store_true", help="Apply SMT-Off optimization (25% CPU compensation)")

    # Command: airlift
    airlift_parser = subparsers.add_parser("airlift", help="Perform top-down Airlift Quick Estimate on aggregate data")
    airlift_parser.add_argument("--total-vcpus", type=float, required=True, help="Total source vCPUs")
    airlift_parser.add_argument("--total-ram", type=float, required=True, help="Total source RAM (GiB)")
    airlift_parser.add_argument("--total-disk", type=float, required=True, help="Total source Disk (GB)")

    args = parser.parse_args()

    if args.command == "mc-report":
        generate_tco_reports()
    elif args.command == "assessment":
        result = rightsizing_engine.run_vm_assessment(
            source_cores=args.cores,
            source_ram_gb=args.ram,
            source_disk_gb=args.disk,
            source_passmark=args.passmark,
            cpu_util=args.cpu_util,
            disk_util=args.disk_util,
            target_series=args.target_series,
            smt_off=args.smt_off
        )
        print("\n" + "="*40)
        print("MANUAL VM ASSESSMENT RESULTS")
        print("-" * 40)
        for k, v in result.items():
            print(f"{k:25}: {v}")
        print("="*40 + "\n")
    elif args.command == "airlift":
        result = rightsizing_engine.run_airlift_estimate(
            total_source_vcpus=args.total_vcpus,
            total_source_ram_gb=args.total_ram,
            total_source_disk_gb=args.total_disk
        )
        print("\n" + "="*40)
        print("AIRLIFT QUICK ESTIMATE RESULTS")
        print("-" * 40)
        for k, v in result.items():
            print(f"{k:25}: {v}")
        print("="*40 + "\n")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
