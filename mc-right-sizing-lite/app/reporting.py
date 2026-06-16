import os
import time
import google.auth
import pandas as pd
from google.cloud import migrationcenter_v1

def get_gcp_context():
    """Helper to detect GCP project and location dynamically."""
    project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GCP_LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1"
    
    if location == "global":
        location = "us-central1"
        
    if not project_id:
        try:
            _, project_id = google.auth.default()
        except Exception:
            pass
            
    return project_id, location

def setup_migration_preferences() -> str:
    """Sets up the 4 standard migration preferences following right-sizing-guide.md.
    
    a) 1-year CUD like-for-like
    b) 3-year CUD like-for-like
    c) 1-year CUD right-sized
    d) 3-year CUD right-sized
    
    Returns:
        A string log of the operation.
    """
    project_id, location = get_gcp_context()
    if not project_id:
        return "Error: GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT environment variable not set."
        
    client = migrationcenter_v1.MigrationCenterClient()
    parent = f"projects/{project_id}/locations/{location}"
    
    preferences = [
        {
            "id": "iona-1yr-CUD-like-for-like",
            "display_name": "iona-1yr-CUD-like-for-like",
            "commitment_plan": migrationcenter_v1.CommitmentPlan.COMMITMENT_PLAN_ONE_YEAR,
            "sizing_strategy": migrationcenter_v1.SizingOptimizationStrategy.SIZING_OPTIMIZATION_STRATEGY_SAME_AS_SOURCE
        },
        {
            "id": "iona-3yr-CUD-like-for-like",
            "display_name": "iona-3yr-CUD-like-for-like",
            "commitment_plan": migrationcenter_v1.CommitmentPlan.COMMITMENT_PLAN_THREE_YEARS,
            "sizing_strategy": migrationcenter_v1.SizingOptimizationStrategy.SIZING_OPTIMIZATION_STRATEGY_SAME_AS_SOURCE
        },
        {
            "id": "iona-1yr-CUD-rightsized",
            "display_name": "iona-1yr-CUD-rightsized",
            "commitment_plan": migrationcenter_v1.CommitmentPlan.COMMITMENT_PLAN_ONE_YEAR,
            "sizing_strategy": migrationcenter_v1.SizingOptimizationStrategy.SIZING_OPTIMIZATION_STRATEGY_AGGRESSIVE
        },
        {
            "id": "iona-3yr-CUD-rightsized",
            "display_name": "iona-3yr-CUD-rightsized",
            "commitment_plan": migrationcenter_v1.CommitmentPlan.COMMITMENT_PLAN_THREE_YEARS,
            "sizing_strategy": migrationcenter_v1.SizingOptimizationStrategy.SIZING_OPTIMIZATION_STRATEGY_AGGRESSIVE
        }
    ]
    
    logs = [f"Using project: {project_id}, location: {location}"]
    
    for pref in preferences:
        pref_name = f"{parent}/preferenceSets/{pref['id']}"
        logs.append(f"Checking preference set {pref['id']}...")
        
        vm_pref = migrationcenter_v1.VirtualMachinePreferences(
            target_product=migrationcenter_v1.ComputeMigrationTargetProduct.COMPUTE_MIGRATION_TARGET_PRODUCT_COMPUTE_ENGINE,
            region_preferences=migrationcenter_v1.RegionPreferences(preferred_regions=[location]),
            commitment_plan=pref["commitment_plan"],
            sizing_optimization_strategy=pref["sizing_strategy"]
        )
        
        pref_set = migrationcenter_v1.PreferenceSet(
            display_name=pref["display_name"],
            description=f"Standard preference set: {pref['display_name']}",
            virtual_machine_preferences=vm_pref
        )
        
        try:
            existing = client.get_preference_set(name=pref_name)
            logs.append(f"Preference set {pref['id']} exists. Updating it...")
            req = migrationcenter_v1.UpdatePreferenceSetRequest(
                preference_set=pref_set,
                update_mask={"paths": ["virtual_machine_preferences", "display_name", "description"]}
            )
            pref_set.name = pref_name
            op = client.update_preference_set(request=req)
            res = op.result()
            logs.append(f"Preference set {pref['id']} updated successfully: {res.name}")
        except Exception:
            logs.append(f"Preference set {pref['id']} not found. Creating it...")
            try:
                req = migrationcenter_v1.CreatePreferenceSetRequest(
                    parent=parent,
                    preference_set=pref_set,
                    preference_set_id=pref["id"]
                )
                op = client.create_preference_set(request=req)
                res = op.result()
                logs.append(f"Preference set {pref['id']} created successfully: {res.name}")
            except Exception as ce:
                logs.append(f"Error creating preference set {pref['id']}: {ce}")
                
    return "\n".join(logs)

def create_tco_report() -> str:
    """Creates a single TCO Detailed report containing all 4 preferences for groups: all-assets, hyperv-assets, vmware-assets.
    
    Returns:
        A string log of the operations and results.
    """
    project_id, location = get_gcp_context()
    if not project_id:
        return "Error: GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT environment variable not set."
        
    client = migrationcenter_v1.MigrationCenterClient()
    parent = f"projects/{project_id}/locations/{location}"
    
    logs = [f"Using project: {project_id}, location: {location}"]
    
    group_ids = ["all-assets", "hyperv-assets", "vmware-assets"]
    group_names = []
    
    logs.append("Listing assets from Migration Center...")
    try:
        assets = list(client.list_assets(parent=parent))
        logs.append(f"Found {len(assets)} assets in Migration Center.")
    except Exception as e:
        return f"Error listing assets from Migration Center: {e}\n" + "\n".join(logs)
        
    vmware_assets = []
    hyperv_assets = []
    all_assets = [asset.name for asset in assets]
    
    tag_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "mc-data-prep-lite", "app", "data", "output", "tagInfo.csv"),
        os.path.join(os.path.dirname(__file__), "..", "..", "mc-data-prep", "app", "data", "output", "tagInfo.csv"),
        os.path.join(os.path.dirname(__file__), "..", "data", "output", "tagInfo.csv"),
        os.path.join(os.path.dirname(__file__), "tagInfo.csv"),
    ]
    
    df_tags = None
    for path in tag_paths:
        if os.path.exists(path):
            try:
                df_tags = pd.read_csv(path)
                logs.append(f"Loaded tagging information from {path}")
                break
            except Exception as e:
                logs.append(f"Warning: Failed to read {path}: {e}")
                
    if df_tags is not None:
        id_col = None
        for col in ["MachineId", "Machine Id", "Machine ID", "machine_id"]:
            if col in df_tags.columns:
                id_col = col
                break
        if not id_col:
            id_col = df_tags.columns[0]

        val_col = None
        for col in ["Value", "Tag Value", "tag_value", "value"]:
            if col in df_tags.columns:
                val_col = col
                break
        if not val_col:
            val_col = df_tags.columns[2] if len(df_tags.columns) > 2 else df_tags.columns[1]
            
        for asset in assets:
            asset_id = asset.name.split('/')[-1]
            matched = False
            for _, row in df_tags.iterrows():
                m_id = str(row[id_col])
                source = str(row[val_col]).lower()
                
                if asset_id == m_id or asset_id.lower() == m_id.lower():
                    if source == "vmware":
                        vmware_assets.append(asset.name)
                    elif source == "hyperv":
                        hyperv_assets.append(asset.name)
                    matched = True
                    break
    else:
        logs.append("No tagInfo.csv found. Will only assign general assets if present.")
        
    for gid in group_ids:
        group_name = f"{parent}/groups/{gid}"
        logs.append(f"Checking group {gid}...")
        try:
            client.get_group(name=group_name)
            logs.append(f"Group {gid} already exists.")
        except Exception:
            logs.append(f"Group {gid} not found. Creating it...")
            try:
                new_group = migrationcenter_v1.Group(display_name=gid)
                req = migrationcenter_v1.CreateGroupRequest(
                    parent=parent,
                    group=new_group,
                    group_id=gid
                )
                op = client.create_group(request=req)
                res = op.result()
                logs.append(f"Group {gid} created successfully: {res.name}")
            except Exception as ce:
                return f"Error creating group {gid}: {ce}\n" + "\n".join(logs)
                
        group_names.append(group_name)
        
        to_add = []
        if gid == "all-assets":
            to_add = all_assets
        elif gid == "vmware-assets":
            to_add = vmware_assets
        elif gid == "hyperv-assets":
            to_add = hyperv_assets
            
        if to_add:
            logs.append(f"Adding {len(to_add)} assets to group {gid}...")
            try:
                req = migrationcenter_v1.AddAssetsToGroupRequest(
                    group=group_name,
                    assets=migrationcenter_v1.AssetList(asset_ids=to_add)
                )
                op = client.add_assets_to_group(request=req)
                op.result()
                logs.append(f"Assets added successfully to {gid}.")
            except Exception as ae:
                logs.append(f"Warning: Failed to add assets to {gid}: {ae}")
                
    logs.append("Ensuring preference sets are set up...")
    pref_logs = setup_migration_preferences()
    logs.append(pref_logs)
    
    pref_ids = [
        "iona-1yr-CUD-like-for-like",
        "iona-3yr-CUD-like-for-like",
        "iona-1yr-CUD-rightsized",
        "iona-3yr-CUD-rightsized"
    ]
    
    assignments = []
    for gid in group_ids:
        gname = f"{parent}/groups/{gid}"
        for pid in pref_ids:
            pname = f"{parent}/preferenceSets/{pid}"
            assignments.append(
                migrationcenter_v1.ReportConfig.GroupPreferenceSetAssignment(
                    group=gname,
                    preference_set=pname
                )
            )
            
    report_config_id = "tco-detailed-config"
    report_config_name = f"{parent}/reportConfigs/{report_config_id}"
    
    try:
        logs.append(f"Checking if report config {report_config_id} already exists...")
        client.get_report_config(name=report_config_name)
        logs.append(f"Report config {report_config_id} exists. Deleting it to refresh configurations...")
        client.delete_report_config(name=report_config_name).result()
        logs.append(f"Successfully deleted existing report config {report_config_id}.")
    except Exception:
        pass
    
    report_config = migrationcenter_v1.ReportConfig(
        display_name="TCO Detailed Report Config",
        description="Contains comparisons across all groups and 4 standard preferences",
        group_preferenceset_assignments=assignments
    )
    
    logs.append(f"Creating Report Config {report_config_id}...")
    try:
        req = migrationcenter_v1.CreateReportConfigRequest(
            parent=parent,
            report_config_id=report_config_id,
            report_config=report_config
        )
        op = client.create_report_config(request=req)
        res = op.result()
        logs.append(f"Report Config created successfully: {res.name}")
    except Exception as rce:
        return f"Error creating Report Config: {rce}\n" + "\n".join(logs)
        
    report_id = f"tco-detailed-report-{int(time.time())}"
    report = migrationcenter_v1.Report(
        display_name="TCO Detailed Report",
        description="Point-in-time rendering of all groups and 4 preferences",
        type_=migrationcenter_v1.Report.Type.TOTAL_COST_OF_OWNERSHIP
    )
    
    logs.append(f"Creating/Running TCO Detailed Report {report_id} from {res.name}...")
    try:
        req = migrationcenter_v1.CreateReportRequest(
            parent=report_config_name,
            report_id=report_id,
            report=report
        )
        op = client.create_report(request=req)
        logs.append("Waiting for report generation operation to complete...")
        res_report = op.result()
        logs.append(f"TCO Detailed Report created successfully! Resource name: {res_report.name}")
        logs.append(f"Report state: {res_report.state}")
    except Exception as re:
        return f"Error creating TCO Detailed Report: {re}\n" + "\n".join(logs)
        
    return "\n".join(logs)
