"""FastMCP server for UGAFStudio QA framework.

Run: python scripts/ugaf_mcp.py
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from qa_framework.mcp_tools import (
    create_testcase_tool,
    delegate_code_task_tool,
    describe_qa_selection_tool,
    export_fmv_coverage_report_tool,
    export_game_vault_tool,
    export_testcase_report_csv_tool,
    export_testcase_report_docx_tool,
    export_testcase_report_html_tool,
    get_cost_tracker_tool,
    get_fmv_coverage_report_tool,
    get_recovery_tracker_tool,
    get_source_revision_tool,
    get_story_database_summary_tool,
    get_testcase_report_tool,
    get_unreal_performance_report_tool,
    list_checkpoints_tool,
    list_database_runs_tool,
    list_game_memory_tool,
    list_game_profiles_tool,
    list_live_runs_tool,
    list_qa_campaigns_tool,
    list_source_sheets_tool,
    list_testcases_tool,
    list_unreal_telemetry_tool,
    read_source_sheet_tool,
    record_feedback_tool,
    retry_qa_campaign_tool,
    run_qa_tool,
    run_robot_suite_tool,
    search_game_memory_tool,
    start_live_session_tool,
    start_qa_campaign_tool,
    stop_live_session_tool,
)

mcp = FastMCP("ugafstudio-qa", version="1.0.0")


@mcp.tool()
def run_qa(suite_path: str, enable_verification: bool = True) -> dict[str, Any]:
    """Run a QA suite with optional verification layer.

    Args:
        suite_path: Path to QA suite JSON file (absolute or relative)
        enable_verification: Use verification checkpoints (default: True)
    """
    return run_qa_tool(suite_path=suite_path, enable_verification=enable_verification)


@mcp.tool()
def run_robot_suite(
    suite_path: str,
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    variables: list[str] | None = None,
    output_dir: str = "",
    timeout_sec: int = 1800,
    dry_run: bool = False,
    profile: str = "",
    game_type: str = "",
    build_id: str = "",
) -> dict[str, Any]:
    """Run a Robot Framework game QA suite and return XML/HTML report locations.

    Robot status and UGAF testcase QA status are reported separately. Game
    input requires the suite to opt in and name the expected foreground title.
    """
    return run_robot_suite_tool(
        suite_path=suite_path,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
        variables=variables,
        output_dir=output_dir,
        timeout_sec=timeout_sec,
        dry_run=dry_run,
        profile=profile,
        game_type=game_type,
        build_id=build_id,
    )


@mcp.tool()
def list_checkpoints(suite_path: str) -> dict[str, Any]:
    """List all checkpoints for a QA suite without running it."""
    return list_checkpoints_tool(suite_path=suite_path)


@mcp.tool()
def get_cost_summary() -> dict[str, Any]:
    """Get cost tracking summary from the last QA run."""
    return get_cost_tracker_tool()


@mcp.tool()
def get_recovery_summary() -> dict[str, Any]:
    """Get recovery tracking summary from the last QA run."""
    return get_recovery_tracker_tool()


@mcp.tool()
def list_game_profiles() -> dict[str, Any]:
    """List locally configured games, genres, and their automation strategies."""
    return list_game_profiles_tool()


@mcp.tool()
def list_testcases(game_type: str | None = None) -> dict[str, Any]:
    """Read the local testcase catalog, optionally filtered by game type."""
    return list_testcases_tool(game_type=game_type)


@mcp.tool()
def create_testcase(
    case_id: str,
    title: str,
    game_type: str,
    category: str,
    steps: list[str],
    expected: list[str],
    setup: list[str] | None = None,
    priority: str = "P2",
    profile: str = "highschoolblood-demo",
) -> dict[str, Any]:
    """Create a local draft testcase without editing the read-only source website."""
    return create_testcase_tool(
        case_id=case_id,
        title=title,
        game_type=game_type,
        category=category,
        steps=steps,
        expected=expected,
        setup=setup,
        priority=priority,
        profile=profile,
    )


@mcp.tool()
def start_live_session(
    profile: str,
    max_steps: int = 30,
    confirm_gameplay_input: bool = False,
    confirm_eula_cleared: bool = False,
    testcase_id: str = "",
    case_ids: list[str] | None = None,
    categories: list[str] | None = None,
) -> dict[str, Any]:
    """Start one bounded local gameplay session after explicit input confirmation."""
    return start_live_session_tool(
        profile=profile,
        max_steps=max_steps,
        confirm_gameplay_input=confirm_gameplay_input,
        confirm_eula_cleared=confirm_eula_cleared,
        testcase_id=testcase_id,
        case_ids=case_ids,
        categories=categories,
    )


@mcp.tool()
def describe_qa_selection(profile: str) -> dict[str, Any]:
    """Discovery first: available categories and cases for one explicit profile."""
    return describe_qa_selection_tool(profile=profile)


@mcp.tool()
def start_qa_campaign(
    profile: str,
    case_ids: list[str] | None = None,
    categories: list[str] | None = None,
    max_steps: int = 60,
    confirm_gameplay_input: bool = False,
    confirm_eula_cleared: bool = False,
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Start a bounded campaign for a fresh profile + selected categories/cases."""
    return start_qa_campaign_tool(
        profile=profile,
        case_ids=case_ids,
        categories=categories,
        max_steps=max_steps,
        confirm_gameplay_input=confirm_gameplay_input,
        confirm_eula_cleared=confirm_eula_cleared,
        idempotency_key=idempotency_key,
    )


@mcp.tool()
def list_qa_campaigns(profile: str = "", limit: int = 50) -> dict[str, Any]:
    """Read durable campaign state and linked run IDs from profile databases."""
    return list_qa_campaigns_tool(profile=profile, limit=limit)


@mcp.tool()
def retry_qa_campaign(
    campaign_id: str,
    retry_key: str,
    max_steps: int = 60,
    confirm_gameplay_input: bool = False,
    confirm_eula_cleared: bool = False,
) -> dict[str, Any]:
    """Run a new idempotent attempt for a stopped/failed campaign."""
    return retry_qa_campaign_tool(
        campaign_id=campaign_id,
        retry_key=retry_key,
        max_steps=max_steps,
        confirm_gameplay_input=confirm_gameplay_input,
        confirm_eula_cleared=confirm_eula_cleared,
    )


@mcp.tool()
def delegate_code_task(task: str, timeout_sec: int = 300) -> dict[str, Any]:
    """Delegate an explicit coding task to the local OpenCode CLI (Hermes only; OpenCode must never call this)."""
    return delegate_code_task_tool(task=task, timeout_sec=timeout_sec)


@mcp.tool()
def list_live_runs() -> dict[str, Any]:
    """Get status and artifact paths for live sessions started by this MCP server."""
    return list_live_runs_tool()


@mcp.tool()
def stop_live_session(run_id: str) -> dict[str, Any]:
    """Stop a running session by run ID; held input is released by runner cleanup."""
    return stop_live_session_tool(run_id=run_id)


@mcp.tool()
def record_qa_feedback(
    category: str,
    note: str,
    case_id: str = "",
    run_id: str = "",
    profile: str = "",
) -> dict[str, Any]:
    """Append a local QA feedback note linked to an optional case and run."""
    return record_feedback_tool(
        category=category, note=note, case_id=case_id, run_id=run_id, profile=profile
    )


@mcp.tool()
def get_story_database_summary(profile: str = "highschoolblood-demo") -> dict[str, Any]:
    """Get counts for stored scenes, subtitles, choices, links, and testcases."""
    return get_story_database_summary_tool(profile=profile)


@mcp.tool()
def get_fmv_coverage_report(
    profile: str = "highschoolblood-demo", roots: list[str] | None = None
) -> dict[str, Any]:
    """Audit source graph reachability, testcase-linked choice options, and gaps (read-only)."""
    return get_fmv_coverage_report_tool(profile=profile, roots=roots)


@mcp.tool()
def export_fmv_coverage_report(
    profile: str = "highschoolblood-demo", destination: str = ""
) -> dict[str, Any]:
    """Save a timestamped JSON report for source-flow reachability and choice gaps."""
    return export_fmv_coverage_report_tool(profile=profile, destination=destination)


@mcp.tool()
def get_game_memory(profile: str, query: str = "", limit: int = 50) -> dict[str, Any]:
    """Recall user requirements and learned game facts for one isolated game profile."""
    return list_game_memory_tool(profile=profile, query=query, limit=limit)


@mcp.tool()
def search_game_memory(profile: str, query: str, limit: int = 20) -> dict[str, Any]:
    """Full-text search a game profile and return snippets with source/run citations."""
    return search_game_memory_tool(profile=profile, query=query, limit=limit)


@mcp.tool()
def export_game_vault(profile: str, destination: str = "") -> dict[str, Any]:
    """Export an Obsidian-compatible Markdown vault for one isolated game profile."""
    return export_game_vault_tool(profile=profile, destination=destination)


@mcp.tool()
def list_source_sheets(profile: str) -> dict[str, Any]:
    """List all read-only spreadsheet tabs and linked documents imported for a game."""
    return list_source_sheets_tool(profile=profile)


@mcp.tool()
def read_source_sheet(profile: str, source_id: str, sheet_name: str) -> dict[str, Any]:
    """Read the archived rows and hyperlinks from one source worksheet."""
    return read_source_sheet_tool(profile=profile, source_id=source_id, sheet_name=sheet_name)


@mcp.tool()
def get_source_revision(profile: str, source_id: str, revision_hash: str = "") -> dict[str, Any]:
    """Get source revision rows and provenance citations, including localization conflicts."""
    return get_source_revision_tool(
        profile=profile, source_id=source_id, revision_hash=revision_hash
    )


@mcp.tool()
def list_unreal_telemetry(profile: str, session_id: str = "", limit: int = 100) -> dict[str, Any]:
    """Read persisted Unreal bridge events for one game profile and QA session."""
    return list_unreal_telemetry_tool(profile=profile, session_id=session_id, limit=limit)


@mcp.tool()
def get_unreal_performance_report(
    profile: str,
    session_id: str = "",
    limit: int = 1000,
    target_fps: float = 60.0,
    scenario_id: str = "",
    baseline_session_id: str = "",
) -> dict[str, Any]:
    """Analyze stored Unreal frame-time, CPU/GPU, memory and streaming stress samples."""
    return get_unreal_performance_report_tool(
        profile=profile,
        session_id=session_id,
        limit=limit,
        target_fps=target_fps,
        scenario_id=scenario_id,
        baseline_session_id=baseline_session_id,
    )


@mcp.tool()
def list_database_runs(profile: str = "", limit: int = 25) -> dict[str, Any]:
    """List stored QA run manifests and report/evidence paths."""
    return list_database_runs_tool(profile=profile, limit=limit)


@mcp.tool()
def get_testcase_report(run_id: str, profile: str = "") -> dict[str, Any]:
    """Read testcase outcomes and linked evidence for one stored run."""
    return get_testcase_report_tool(run_id=run_id, profile=profile)


@mcp.tool()
def export_testcase_report_docx(run_id: str, profile: str = "") -> dict[str, Any]:
    """Export one stored run as an editable Word report under reports/qa_reports/."""
    return export_testcase_report_docx_tool(run_id=run_id, profile=profile)


@mcp.tool()
def export_testcase_report_html(run_id: str, profile: str = "") -> dict[str, Any]:
    """Export one stored run as an offline HTML report with verified evidence links."""
    return export_testcase_report_html_tool(run_id=run_id, profile=profile)


@mcp.tool()
def export_testcase_report_csv(run_id: str, profile: str = "") -> dict[str, Any]:
    """Export one stored run as UTF-8 CSV with source/evidence status columns."""
    return export_testcase_report_csv_tool(run_id=run_id, profile=profile)


def main() -> None:
    """Run the MCP server over stdio for OpenCode and Hermes local clients."""
    mcp.run()


if __name__ == "__main__":
    main()
