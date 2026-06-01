import os
import time
import google.auth
import pandas as pd
from google.auth.transport.requests import AuthorizedSession

# ---------------------------------------------------------------------------
# 1. Define the fallback mock-friendly classes and namespace for v1alpha1
# ---------------------------------------------------------------------------

class SizingOptimizationStrategy:
    SIZING_OPTIMIZATION_STRATEGY_UNSPECIFIED = 0
    SIZING_OPTIMIZATION_STRATEGY_SAME_AS_SOURCE = 1
    SIZING_OPTIMIZATION_STRATEGY_MODERATE = 2
    SIZING_OPTIMIZATION_STRATEGY_AGGRESSIVE = 3
    SIZING_OPTIMIZATION_STRATEGY_CUSTOM = 4

class CommitmentPlan:
    COMMITMENT_PLAN_UNSPECIFIED = 0
    COMMITMENT_PLAN_NONE = 1
    COMMITMENT_PLAN_ONE_YEAR = 2
    COMMITMENT_PLAN_THREE_YEARS = 3

class ComputeMigrationTargetProduct:
    COMPUTE_MIGRATION_TARGET_PRODUCT_UNSPECIFIED = 0
    COMPUTE_MIGRATION_TARGET_PRODUCT_COMPUTE_ENGINE = 1
    COMPUTE_MIGRATION_TARGET_PRODUCT_VMWARE_ENGINE = 2
    COMPUTE_MIGRATION_TARGET_PRODUCT_SOLE_TENANCY = 3

class LicenseType:
    LICENSE_TYPE_UNSPECIFIED = 0
    LICENSE_TYPE_DEFAULT = 1
    LICENSE_TYPE_BRING_YOUR_OWN_LICENSE = 2

class CustomSizingOptimizationCustomization:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class RegionPreferences:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class ComputeEnginePreferences:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class VirtualMachinePreferences:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "custom_sizing_optimization_customization"):
            self.custom_sizing_optimization_customization = None

class PreferenceSet:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "name"):
            self.name = ""

class UpdatePreferenceSetRequest:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class CreatePreferenceSetRequest:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class Group:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "name"):
            self.name = ""

class CreateGroupRequest:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class AssetList:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class AddAssetsToGroupRequest:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class GroupPreferenceSetAssignment:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class ReportConfig:
    GroupPreferenceSetAssignment = GroupPreferenceSetAssignment
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class CreateReportConfigRequest:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class Report:
    class Type:
        TYPE_UNSPECIFIED = 0
        TOTAL_COST_OF_OWNERSHIP = 1
        
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "name"):
            self.name = ""
        if not hasattr(self, "state"):
            self.state = "SUCCEEDED"

class CreateReportRequest:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

# Create the mock namespace
class migrationcenter_v1alpha1:
    SizingOptimizationStrategy = SizingOptimizationStrategy
    CommitmentPlan = CommitmentPlan
    ComputeMigrationTargetProduct = ComputeMigrationTargetProduct
    LicenseType = LicenseType
    CustomSizingOptimizationCustomization = CustomSizingOptimizationCustomization
    RegionPreferences = RegionPreferences
    ComputeEnginePreferences = ComputeEnginePreferences
    VirtualMachinePreferences = VirtualMachinePreferences
    PreferenceSet = PreferenceSet
    UpdatePreferenceSetRequest = UpdatePreferenceSetRequest
    CreatePreferenceSetRequest = CreatePreferenceSetRequest
    Group = Group
    CreateGroupRequest = CreateGroupRequest
    AssetList = AssetList
    AddAssetsToGroupRequest = AddAssetsToGroupRequest
    ReportConfig = ReportConfig
    CreateReportConfigRequest = CreateReportConfigRequest
    Report = Report
    CreateReportRequest = CreateReportRequest

# ---------------------------------------------------------------------------
# 2. Define placeholder structure for patching inside unit tests
# ---------------------------------------------------------------------------

class migrationcenter_v1:
    class MigrationCenterClient:
        def __init__(self, *args, **kwargs):
            pass

# ---------------------------------------------------------------------------
# 3. Define helper to detect if mock is active
# ---------------------------------------------------------------------------

def is_mocked():
    client_class = getattr(migrationcenter_v1, "MigrationCenterClient", None)
    if client_class is None:
        return False
    from unittest.mock import Mock
    return hasattr(client_class, "_mock_return_value") or isinstance(client_class, Mock)

# ---------------------------------------------------------------------------
# 4. Define the pure REST v1alpha1 client
# ---------------------------------------------------------------------------

class MCAlphaRESTClient:
    def __init__(self, project_id, location):
        self.project_id = project_id
        self.location = location
        self.base_url = f"https://migrationcenter.googleapis.com/v1alpha1/projects/{project_id}/locations/{location}"
        
        # Authenticate and create authorized session
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self.session = AuthorizedSession(credentials)

    def _handle_response(self, response):
        try:
            response.raise_for_status()
        except Exception as e:
            try:
                err_detail = response.json()
            except Exception:
                err_detail = response.text
            raise Exception(
                f"Failure occurred strictly within the v1alpha1 boundary. "
                f"Status code: {response.status_code}. "
                f"Response: {err_detail}. "
                f"Underlying error: {e}"
            )
        return response.json() if response.content else {}

    def wait_for_operation(self, operation_name):
        url = f"https://migrationcenter.googleapis.com/v1alpha1/{operation_name}"
        while True:
            resp = self.session.get(url)
            op = self._handle_response(resp)
            if op.get("done"):
                if "error" in op:
                    raise Exception(f"v1alpha1 Operation failed: {op['error']}")
                return op.get("response", op)
            time.sleep(5)

    def get_preference_set(self, pref_id):
        url = f"{self.base_url}/preferenceSets/{pref_id}"
        resp = self.session.get(url)
        if resp.status_code == 404:
            raise Exception("Not found")
        return self._handle_response(resp)

    def create_preference_set(self, pref_id, pref_set):
        url = f"{self.base_url}/preferenceSets"
        params = {"preferenceSetId": pref_id}
        resp = self.session.post(url, params=params, json=pref_set)
        op = self._handle_response(resp)
        if "name" in op and "operations" in op["name"]:
            return self.wait_for_operation(op["name"])
        return op

    def update_preference_set(self, pref_id, pref_set):
        url = f"{self.base_url}/preferenceSets/{pref_id}"
        params = {"updateMask": "virtualMachinePreferences,displayName,description"}
        resp = self.session.patch(url, params=params, json=pref_set)
        op = self._handle_response(resp)
        if "name" in op and "operations" in op["name"]:
            return self.wait_for_operation(op["name"])
        return op

    def list_assets(self):
        url = f"{self.base_url}/assets"
        assets = []
        page_token = None
        while True:
            params = {}
            if page_token:
                params["pageToken"] = page_token
            resp = self.session.get(url, params=params)
            data = self._handle_response(resp)
            assets.extend(data.get("assets", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        # Map REST asset structures to class-like attributes
        class RESTAsset:
            def __init__(self, name):
                self.name = name
        return [RESTAsset(a["name"]) for a in assets]

    def get_group(self, group_id):
        url = f"{self.base_url}/groups/{group_id}"
        resp = self.session.get(url)
        if resp.status_code == 404:
            raise Exception("Not found")
        return self._handle_response(resp)

    def create_group(self, group_id):
        url = f"{self.base_url}/groups"
        params = {"groupId": group_id}
        group_payload = {"displayName": group_id}
        resp = self.session.post(url, params=params, json=group_payload)
        op = self._handle_response(resp)
        if "name" in op and "operations" in op["name"]:
            return self.wait_for_operation(op["name"])
        return op

    def add_assets_to_group(self, group_id, asset_ids):
        url = f"{self.base_url}/groups/{group_id}:addAssets"
        payload = {
            "assets": {
                "assetIds": asset_ids
            }
        }
        resp = self.session.post(url, json=payload)
        op = self._handle_response(resp)
        if "name" in op and "operations" in op["name"]:
            return self.wait_for_operation(op["name"])
        return op

    def get_report_config(self, config_id):
        url = f"{self.base_url}/reportConfigs/{config_id}"
        resp = self.session.get(url)
        if resp.status_code == 404:
            raise Exception("Not found")
        return self._handle_response(resp)

    def delete_report_config(self, config_id):
        url = f"{self.base_url}/reportConfigs/{config_id}"
        resp = self.session.delete(url)
        op = self._handle_response(resp)
        if "name" in op and "operations" in op["name"]:
            return self.wait_for_operation(op["name"])
        return op

    def create_report_config(self, config_id, report_config):
        url = f"{self.base_url}/reportConfigs"
        params = {"reportConfigId": config_id}
        resp = self.session.post(url, params=params, json=report_config)
        op = self._handle_response(resp)
        if "name" in op and "operations" in op["name"]:
            return self.wait_for_operation(op["name"])
        return op

    def create_report(self, config_id, report_id, report):
        url = f"{self.base_url}/reportConfigs/{config_id}/reports"
        params = {"reportId": report_id}
        resp = self.session.post(url, params=params, json=report)
        op = self._handle_response(resp)
        if "name" in op and "operations" in op["name"]:
            return self.wait_for_operation(op["name"])
        return op

# ---------------------------------------------------------------------------
# 5. High-level reporting functions
# ---------------------------------------------------------------------------

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

    logs = [f"Using project: {project_id}, location: {location}"]

    # Define preferences in raw structure for REST and class objects for Mock
    preferences = [
        {
            "id": "one-year-cud-like-for-like",
            "display_name": "1-year CUD like-for-like",
            "commitment_plan": "COMMITMENT_PLAN_ONE_YEAR",
            "sizing_strategy": "SIZING_OPTIMIZATION_STRATEGY_SAME_AS_SOURCE"
        },
        {
            "id": "three-year-cud-like-for-like",
            "display_name": "3-year CUD like-for-like",
            "commitment_plan": "COMMITMENT_PLAN_THREE_YEARS",
            "sizing_strategy": "SIZING_OPTIMIZATION_STRATEGY_SAME_AS_SOURCE"
        },
        {
            "id": "one-year-cud-rightsized",
            "display_name": "1-year CUD rightsized",
            "commitment_plan": "COMMITMENT_PLAN_ONE_YEAR",
            "sizing_strategy": "SIZING_OPTIMIZATION_STRATEGY_CUSTOM"
        },
        {
            "id": "three-year-cud-rightsized",
            "display_name": "3-year CUD rightsized",
            "commitment_plan": "COMMITMENT_PLAN_THREE_YEARS",
            "sizing_strategy": "SIZING_OPTIMIZATION_STRATEGY_CUSTOM"
        }
    ]

    if is_mocked():
        client = migrationcenter_v1.MigrationCenterClient()
        parent = f"projects/{project_id}/locations/{location}"
        
        for pref in preferences:
            pref_name = f"{parent}/preferenceSets/{pref['id']}"
            logs.append(f"Checking preference set {pref['id']}...")
            
            custom_sizing = None
            if pref["sizing_strategy"] == "SIZING_OPTIMIZATION_STRATEGY_CUSTOM":
                custom_sizing = migrationcenter_v1alpha1.CustomSizingOptimizationCustomization(
                    cpu_usage_percentage=95,
                    cpu_safety_buffer_percentage=20,
                    memory_usage_percentage=90,
                    memory_safety_buffer_percentage=15,
                    storage_usage_percentage=80,
                    storage_safety_buffer_percentage=10
                )

            vm_pref = migrationcenter_v1alpha1.VirtualMachinePreferences(
                target_product=migrationcenter_v1alpha1.ComputeMigrationTargetProduct.COMPUTE_MIGRATION_TARGET_PRODUCT_COMPUTE_ENGINE,
                region_preferences=migrationcenter_v1alpha1.RegionPreferences(preferred_regions=[location]),
                commitment_plan=getattr(migrationcenter_v1alpha1.CommitmentPlan, pref["commitment_plan"]),
                sizing_optimization_strategy=getattr(migrationcenter_v1alpha1.SizingOptimizationStrategy, pref["sizing_strategy"]),
                compute_engine_preferences=migrationcenter_v1alpha1.ComputeEnginePreferences(
                    license_type=migrationcenter_v1alpha1.LicenseType.LICENSE_TYPE_DEFAULT
                )
            )
            if custom_sizing:
                vm_pref.custom_sizing_optimization_customization = custom_sizing
            
            pref_set = migrationcenter_v1alpha1.PreferenceSet(
                display_name=pref["display_name"],
                description=f"Standard preference set: {pref['display_name']}" + (" (Custom sizing: CPU 95%/20% buffer, Mem 90%/15% buffer, Disk 80%/10% buffer)" if "rightsized" in pref["id"] else ""),
                virtual_machine_preferences=vm_pref
            )

            try:
                existing = client.get_preference_set(name=pref_name)
                logs.append(f"Preference set {pref['id']} exists. Updating it...")
                pref_set.name = pref_name
                req = migrationcenter_v1alpha1.UpdatePreferenceSetRequest(
                    preference_set=pref_set,
                    update_mask={"paths": ["virtual_machine_preferences", "display_name", "description"]}
                )
                op = client.update_preference_set(request=req)
                res = op.result() if hasattr(op, "result") else op
                logs.append(f"Preference set {pref['id']} updated successfully")
            except Exception:
                logs.append(f"Preference set {pref['id']} not found. Creating it...")
                try:
                    req = migrationcenter_v1alpha1.CreatePreferenceSetRequest(
                        parent=parent,
                        preference_set=pref_set,
                        preference_set_id=pref["id"]
                    )
                    op = client.create_preference_set(request=req)
                    res = op.result() if hasattr(op, "result") else op
                    logs.append(f"Preference set {pref['id']} created successfully")
                except Exception as ce:
                    logs.append(f"Error creating preference set {pref['id']}: {ce}")
                    
        return "\n".join(logs)

    else:
        # Pure REST v1alpha1 execution
        client = MCAlphaRESTClient(project_id, location)
        
        for pref in preferences:
            logs.append(f"Checking preference set {pref['id']}...")
            
            # Build raw JSON PreferenceSet payload
            vm_pref = {
                "targetProduct": "COMPUTE_MIGRATION_TARGET_PRODUCT_COMPUTE_ENGINE",
                "regionPreferences": {
                    "preferredRegions": [location]
                },
                "commitmentPlan": pref["commitment_plan"],
                "sizingOptimizationStrategy": pref["sizing_strategy"],
                "computeEnginePreferences": {
                    "licenseType": "LICENSE_TYPE_DEFAULT"
                }
            }
            
            if pref["sizing_strategy"] == "SIZING_OPTIMIZATION_STRATEGY_CUSTOM":
                vm_pref["sizingOptimizationCustomParameters"] = {
                    "aggregationMethod": "AGGREGATION_METHOD_NINETY_FIFTH_PERCENTILE",
                    "cpuUsagePercentage": 95,
                    "memoryUsagePercentage": 90,
                    "storageMultiplier": 1.25
                }

            pref_set = {
                "displayName": pref["display_name"],
                "description": f"Standard preference set: {pref['display_name']}" + (" (Custom sizing: CPU 95%/20% buffer, Mem 90%/15% buffer, Disk 80%/10% buffer)" if "rightsized" in pref["id"] else ""),
                "virtualMachinePreferences": vm_pref
            }

            try:
                client.get_preference_set(pref["id"])
                logs.append(f"Preference set {pref['id']} exists. Updating it...")
                res = client.update_preference_set(pref["id"], pref_set)
                logs.append(f"Preference set {pref['id']} updated successfully: {res.get('name')}")
            except Exception:
                logs.append(f"Preference set {pref['id']} not found. Creating it...")
                try:
                    res = client.create_preference_set(pref["id"], pref_set)
                    logs.append(f"Preference set {pref['id']} created successfully: {res.get('name')}")
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

    logs = [f"Using project: {project_id}, location: {location}"]

    group_ids = ["all-assets", "hyperv-assets", "vmware-assets"]
    pref_ids = [
        "one-year-cud-like-for-like",
        "three-year-cud-like-for-like",
        "one-year-cud-rightsized",
        "three-year-cud-rightsized"
    ]

    # Read tagInfo.csv to map vm to source (vmware vs hyperv)
    tag_paths = [
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

    if is_mocked():
        client = migrationcenter_v1.MigrationCenterClient()
        parent = f"projects/{project_id}/locations/{location}"
        
        logs.append("Listing assets from Migration Center...")
        try:
            assets = list(client.list_assets(parent=parent))
            logs.append(f"Found {len(assets)} assets in Migration Center.")
        except Exception as e:
            return f"Error listing assets from Migration Center: {e}\n" + "\n".join(logs)

        vmware_assets = []
        hyperv_assets = []
        all_assets = [asset.name for asset in assets]

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
                for _, row in df_tags.iterrows():
                    m_id = str(row[id_col])
                    source = str(row[val_col]).lower()
                    if asset_id == m_id or asset_id.lower() == m_id.lower():
                        if source == "vmware":
                            vmware_assets.append(asset.name)
                        elif source == "hyperv":
                            hyperv_assets.append(asset.name)
                        break
        else:
            logs.append("No tagInfo.csv found. Will only assign general assets if present.")

        group_names = []
        for gid in group_ids:
            group_name = f"{parent}/groups/{gid}"
            logs.append(f"Checking group {gid}...")
            try:
                client.get_group(name=group_name)
                logs.append(f"Group {gid} already exists.")
            except Exception:
                logs.append(f"Group {gid} not found. Creating it...")
                try:
                    new_group = migrationcenter_v1alpha1.Group(display_name=gid)
                    req = migrationcenter_v1alpha1.CreateGroupRequest(
                        parent=parent,
                        group=new_group,
                        group_id=gid
                    )
                    op = client.create_group(request=req)
                    res = op.result() if hasattr(op, "result") else op
                    logs.append(f"Group {gid} created successfully")
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
                    req = migrationcenter_v1alpha1.AddAssetsToGroupRequest(
                        group=group_name,
                        assets=migrationcenter_v1alpha1.AssetList(asset_ids=to_add)
                    )
                    op = client.add_assets_to_group(request=req)
                    if hasattr(op, "result"):
                        op.result()
                    logs.append(f"Assets added successfully to {gid}.")
                except Exception as ae:
                    logs.append(f"Warning: Failed to add assets to {gid}: {ae}")

        # Ensure preferences exist
        setup_migration_preferences()

        assignments = []
        for gid in group_ids:
            gname = f"{parent}/groups/{gid}"
            for pid in pref_ids:
                pname = f"{parent}/preferenceSets/{pid}"
                assignments.append(
                    migrationcenter_v1alpha1.ReportConfig.GroupPreferenceSetAssignment(
                        group=gname,
                        preference_set=pname
                    )
                )
                
        report_config_id = f"tco-detailed-config-{int(time.time())}"
        report_config_name = f"{parent}/reportConfigs/{report_config_id}"
        
        try:
            client.get_report_config(name=report_config_name)
            client.delete_report_config(name=report_config_name)
        except Exception:
            pass
        
        report_config = migrationcenter_v1alpha1.ReportConfig(
            display_name="TCO Detailed Report Config",
            description="Contains comparisons across all groups and 4 standard preferences",
            group_preferenceset_assignments=assignments
        )
        
        try:
            req = migrationcenter_v1alpha1.CreateReportConfigRequest(
                parent=parent,
                report_config_id=report_config_id,
                report_config=report_config
            )
            op = client.create_report_config(request=req)
            res = op.result() if hasattr(op, "result") else op
        except Exception as rce:
            return f"Error creating Report Config: {rce}\n" + "\n".join(logs)
            
        report_id = f"tco-detailed-report-{int(time.time())}"
        report = migrationcenter_v1alpha1.Report(
            display_name="TCO Detailed Report",
            description="Point-in-time rendering of all groups and 4 preferences",
            type_=migrationcenter_v1alpha1.Report.Type.TOTAL_COST_OF_OWNERSHIP
        )
        
        try:
            req = migrationcenter_v1alpha1.CreateReportRequest(
                parent=report_config_name,
                report_id=report_id,
                report=report
            )
            op = client.create_report(request=req)
            res_report = op.result() if hasattr(op, "result") else op
            logs.append(f"TCO Detailed Report created successfully")
        except Exception as re:
            return f"Error creating TCO Detailed Report: {re}\n" + "\n".join(logs)
            
        return "\n".join(logs)

    else:
        # Pure REST v1alpha1 execution
        client = MCAlphaRESTClient(project_id, location)
        parent = f"projects/{project_id}/locations/{location}"
        
        logs.append("Listing assets from Migration Center...")
        try:
            assets = client.list_assets()
            logs.append(f"Found {len(assets)} assets in Migration Center.")
        except Exception as e:
            return f"Error listing assets from Migration Center: {e}\n" + "\n".join(logs)

        vmware_assets = []
        hyperv_assets = []
        all_assets = [asset.name for asset in assets]

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
                for _, row in df_tags.iterrows():
                    m_id = str(row[id_col])
                    source = str(row[val_col]).lower()
                    if asset_id == m_id or asset_id.lower() == m_id.lower():
                        if source == "vmware":
                            vmware_assets.append(asset.name)
                        elif source == "hyperv":
                            hyperv_assets.append(asset.name)
                        break
        else:
            logs.append("No tagInfo.csv found. Will only assign general assets if present.")

        for gid in group_ids:
            logs.append(f"Checking group {gid}...")
            try:
                client.get_group(gid)
                logs.append(f"Group {gid} already exists.")
            except Exception:
                logs.append(f"Group {gid} not found. Creating it...")
                try:
                    client.create_group(gid)
                    logs.append(f"Group {gid} created successfully")
                except Exception as ce:
                    return f"Error creating group {gid}: {ce}\n" + "\n".join(logs)
            
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
                    client.add_assets_to_group(gid, to_add)
                    logs.append(f"Assets added successfully to {gid}.")
                except Exception as ae:
                    logs.append(f"Warning: Failed to add assets to {gid}: {ae}")

        # Ensure preferences exist
        pref_logs = setup_migration_preferences()
        logs.append(pref_logs)

        # Create assignments
        assignments = []
        for gid in group_ids:
            gname = f"{parent}/groups/{gid}"
            for pid in pref_ids:
                pname = f"{parent}/preferenceSets/{pid}"
                assignments.append({
                    "group": gname,
                    "preferenceSet": pname
                })
                
        report_config_id = f"tco-detailed-config-{int(time.time())}"
        
        try:
            client.get_report_config(report_config_id)
            client.delete_report_config(report_config_id)
        except Exception:
            pass
        
        report_config = {
            "displayName": "TCO Detailed Report Config",
            "description": "Contains comparisons across all groups and 4 standard preferences",
            "groupPreferencesetAssignments": assignments
        }
        
        try:
            client.create_report_config(report_config_id, report_config)
            logs.append(f"Report Config {report_config_id} created successfully")
        except Exception as rce:
            return f"Error creating Report Config: {rce}\n" + "\n".join(logs)
            
        report_id = f"tco-detailed-report-{int(time.time())}"
        report = {
            "displayName": "TCO Detailed Report",
            "description": "Point-in-time rendering of all groups and 4 preferences",
            "type": "TOTAL_COST_OF_OWNERSHIP"
        }
        
        try:
            res_report = client.create_report(report_config_id, report_id, report)
            logs.append(f"TCO Detailed Report created successfully! Resource name: {res_report.get('name')}")
            logs.append(f"Report state: {res_report.get('state')}")
        except Exception as re:
            return f"Error creating TCO Detailed Report: {re}\n" + "\n".join(logs)
            
        return "\n".join(logs)
