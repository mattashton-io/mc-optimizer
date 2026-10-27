from collections import Counter
import os

from google.adk.tools import ToolContext
from google.cloud import migrationcenter_v1

from .app_utils.project_utils import get_project_id


async def scan_migration_center_environment(
    tool_context: ToolContext | None = None,
) -> str:
    """Scans the Google Cloud Migration Center environment for currently uploaded servers (assets), groups, sources, and high-level infrastructure metrics.

    Use this tool whenever the user asks to scan or check their current Migration Center environment, see how many VMs/servers are already imported, or view summary metrics (vCPUs, memory, storage, OS breakdown, power states, groups, or labels) in Migration Center.

    Returns:
        A formatted summary of the Migration Center environment state and high-level metrics.
    """
    project_id = get_project_id()
    location = (
        os.environ.get("GCP_LOCATION")
        or os.environ.get("GOOGLE_CLOUD_LOCATION")
        or "us-central1"
    )
    if location == "global":
        location = "us-central1"

    if not project_id:
        return "Error: GCP Project ID could not be determined."

    parent = f"projects/{project_id}/locations/{location}"

    try:
        client = migrationcenter_v1.MigrationCenterClient()
        req = migrationcenter_v1.ListAssetsRequest(parent=parent, page_size=1000)
        assets = list(client.list_assets(request=req))
    except Exception as e:
        return f"Error scanning Migration Center environment in {parent}: {e}"

    total_vms = len(assets)
    total_cores = 0
    total_memory_mb = 0
    total_disk_bytes = 0
    total_free_disk_bytes = 0

    os_families: Counter[str] = Counter()
    os_names: Counter[str] = Counter()
    power_states: Counter[str] = Counter()
    platforms: Counter[str] = Counter()
    labels_counter: Counter[str] = Counter()
    sample_vms: list[str] = []

    for asset in assets:
        asset_id = asset.name.split("/")[-1]
        md = getattr(asset, "machine_details", None)
        vm_details = getattr(asset, "virtual_machine_details", None)

        machine_name = asset_id
        cores = 0
        mem_mb = 0

        if md:
            if getattr(md, "machine_name", None):
                machine_name = md.machine_name
            cores = getattr(md, "core_count", 0) or 0
            mem_mb = getattr(md, "memory_mb", 0) or 0

            disks = getattr(md, "disks", None)
            if disks:
                total_disk_bytes += getattr(disks, "total_capacity_bytes", 0) or 0
                total_free_disk_bytes += getattr(disks, "total_free_bytes", 0) or 0

            guest_os = getattr(md, "guest_os", None)
            if guest_os:
                family_enum = getattr(guest_os, "family", None)
                family_name = (
                    family_enum.name
                    if hasattr(family_enum, "name")
                    else str(family_enum or "UNKNOWN")
                )
                family_clean = family_name.replace("OS_FAMILY_", "").title()
                os_families[family_clean] += 1

                os_name = getattr(guest_os, "os_name", "") or "Unknown OS"
                os_names[os_name] += 1
            else:
                os_families["Unknown"] += 1

            p_state = getattr(md, "power_state", None)
            p_state_name = (
                p_state.name
                if hasattr(p_state, "name")
                else str(p_state or "UNKNOWN")
            )
            power_states[p_state_name.replace("POWER_STATE_", "")] += 1

            platform = getattr(md, "platform", None)
            if platform and hasattr(platform, "_pb"):
                vendor = platform._pb.WhichOneof("vendor_details")
                if vendor:
                    platforms[vendor.replace("_details", "").upper()] += 1
                else:
                    platforms["GENERIC"] += 1
        elif vm_details:
            if getattr(vm_details, "vm_name", None):
                machine_name = vm_details.vm_name
            cores = getattr(vm_details, "core_count", 0) or 0
            mem_mb = getattr(vm_details, "memory_mb", 0) or 0
            os_name = getattr(vm_details, "guest_os", "") or "Unknown OS"
            os_names[os_name] += 1

        total_cores += cores
        total_memory_mb += mem_mb

        if getattr(asset, "labels", None):
            for k, v in asset.labels.items():
                labels_counter[f"{k}={v}"] += 1

        if len(sample_vms) < 10:
            sample_vms.append(
                f"{machine_name} (ID: {asset_id}, {cores} vCPUs, {round(mem_mb / 1024, 1)} GiB RAM)"
            )

    # Fetch Groups and Sources
    groups_summary = []
    try:
        for g in client.list_groups(parent=parent):
            g_id = g.name.split("/")[-1]
            g_size = getattr(g, "size", 0) or 0
            groups_summary.append(
                f"{g.display_name or g_id} (ID: `{g_id}`, Assets: {g_size})"
            )
    except Exception:
        pass

    sources_summary = []
    try:
        for s in client.list_sources(parent=parent):
            s_id = s.name.split("/")[-1]
            s_state = (
                s.state.name if hasattr(s.state, "name") else str(getattr(s, "state", ""))
            )
            sources_summary.append(
                f"{s.display_name or s_id} (ID: `{s_id}`, State: {s_state})"
            )
    except Exception:
        pass

    if total_vms == 0:
        return (
            f"### Migration Center Environment Scan\n"
            f"- **Project**: `{project_id}`\n"
            f"- **Location**: `{location}`\n"
            f"- **Total Uploaded VMs / Assets**: 0\n"
            f"- **Groups**: {', '.join(groups_summary) if groups_summary else 'None'}\n"
            f"- **Sources**: {', '.join(sources_summary) if sources_summary else 'None'}\n"
        )

    total_memory_gib = total_memory_mb / 1024.0
    total_disk_tib = total_disk_bytes / (1024.0**4)
    total_disk_gib = total_disk_bytes / (1024.0**3)
    used_disk_bytes = max(0, total_disk_bytes - total_free_disk_bytes)
    used_disk_tib = used_disk_bytes / (1024.0**4)

    avg_cores = total_cores / total_vms
    avg_memory_gib = total_memory_gib / total_vms
    avg_disk_gib = total_disk_gib / total_vms

    os_family_str = ", ".join(
        f"{k}: {v:,} ({v / total_vms * 100:.1f}%)"
        for k, v in os_families.most_common()
    )
    top_os_str = "\n".join(
        f"  - {name}: {count:,} ({count / total_vms * 100:.1f}%)"
        for name, count in os_names.most_common(8)
    )
    power_str = ", ".join(
        f"{k}: {v:,} ({v / total_vms * 100:.1f}%)"
        for k, v in power_states.most_common()
    )
    platform_str = (
        ", ".join(f"{k}: {v:,}" for k, v in platforms.most_common())
        if platforms
        else "Unspecified"
    )
    labels_str = (
        ", ".join(f"`{k}` ({v:,})" for k, v in labels_counter.most_common(10))
        if labels_counter
        else "No labels applied yet"
    )

    lines = [
        "### Migration Center Environment Summary",
        f"- **Project**: `{project_id}`",
        f"- **Location**: `{location}`",
        f"- **Total Imported VMs / Servers**: **{total_vms:,}**",
        "",
        "#### High-Level Resource Metrics",
        f"- **Total vCPUs / Cores**: {total_cores:,} (Avg: {avg_cores:.1f} vCPUs/VM)",
        f"- **Total Memory**: {total_memory_gib:,.1f} GiB / {total_memory_gib / 1024:.2f} TiB (Avg: {avg_memory_gib:.1f} GiB/VM)",
        f"- **Total Provisioned Storage**: {total_disk_tib:,.2f} TiB / {total_disk_gib:,.1f} GiB (Avg: {avg_disk_gib:,.1f} GiB/VM)",
        f"- **Estimated Used Storage**: {used_disk_tib:,.2f} TiB",
        "",
        "#### Workload Breakdown",
        f"- **Power States**: {power_str}",
        f"- **OS Families**: {os_family_str}",
        f"- **Source Platforms**: {platform_str}",
        "- **Top Operating Systems**:",
        top_os_str,
        "",
        "#### Organization & Metadata",
        f"- **Groups ({len(groups_summary)})**: {', '.join(groups_summary) if groups_summary else 'No groups found'}",
        f"- **Data Sources ({len(sources_summary)})**: {', '.join(sources_summary[:5]) if sources_summary else 'No sources found'}",
        f"- **Top Asset Labels**: {labels_str}",
        "",
        "#### Sample Imported Servers (First 10)",
        "\n".join(f"  - {vm}" for vm in sample_vms),
    ]

    return "\n".join(lines)
