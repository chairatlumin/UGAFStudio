"""Source-graph reachability and choice-label audit for FMV profiles.

This report describes imported coverage only. It never claims that an edge was
played or that a testcase passed.
"""

from __future__ import annotations

from collections import deque
from typing import Any

_KNOWN_ROOTS = {"highschoolblood-demo": ("01_Prescene_S001",)}


def _case_label(case: dict[str, Any]) -> str:
    return str(case.get("choice", "")).strip()


def build_fmv_coverage_report(
    *,
    profile: str,
    scenes: dict[str, dict[str, Any]],
    testcases: dict[str, dict[str, Any]],
    scene_provenance: dict[str, dict[str, Any]] | None = None,
    roots: list[str] | None = None,
    source_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic, read-only coverage audit from the active profile graph."""
    scene_ids = set(scenes)
    if roots is None:
        selected_roots = list(_KNOWN_ROOTS.get(profile, ()))
        if not selected_roots:
            incoming = {
                str(link.get("target", ""))
                for scene in scenes.values()
                for link in scene.get("outgoing", [])
            }
            selected_roots = sorted(scene_ids - incoming)
        root_method = "profile_default" if profile in _KNOWN_ROOTS else "graph_indegree"
    else:
        selected_roots = sorted({str(root).strip() for root in roots if str(root).strip()})
        root_method = "explicit"
    missing_roots = sorted(set(selected_roots) - scene_ids)
    if not selected_roots or missing_roots:
        raise ValueError(f"Coverage roots are missing from the profile graph: {missing_roots or 'none'}")

    provenance = scene_provenance or {}
    provenance_status = {
        scene_id: str(provenance.get(scene_id, {}).get("status", "unowned"))
        for scene_id in scene_ids
    }
    source_scene_ids = {
        scene_id for scene_id, status in provenance_status.items() if status == "active"
    }
    stale_scene_ids = {
        scene_id for scene_id, status in provenance_status.items() if status == "stale"
    }
    unowned_scene_ids = scene_ids - source_scene_ids - stale_scene_ids

    edges: list[dict[str, Any]] = []
    adjacency: dict[str, list[str]] = {scene_id: [] for scene_id in scene_ids}
    undirected: dict[str, set[str]] = {scene_id: set() for scene_id in scene_ids}
    for source in sorted(scene_ids):
        for link in scenes[source].get("outgoing", []):
            target = str(link.get("target", ""))
            choice_key = str(link.get("choice_key", "")).strip()
            if target:
                adjacency[source].append(target)
                if target in scene_ids:
                    undirected[source].add(target)
                    undirected[target].add(source)
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "choice_key": choice_key,
                    "target_exists": target in scene_ids,
                }
            )

    reachable: set[str] = set()
    queue = deque(selected_roots)
    while queue:
        current = queue.popleft()
        if current in reachable or current not in scene_ids:
            continue
        reachable.add(current)
        queue.extend(adjacency[current])

    source_adjacency: dict[str, list[str]] = {scene_id: [] for scene_id in source_scene_ids}
    source_incoming: dict[str, set[str]] = {scene_id: set() for scene_id in source_scene_ids}
    edges_with_unowned_endpoint = 0
    active_source_edge_count = 0
    for edge in edges:
        source, target = edge["source"], edge["target"]
        if source not in source_scene_ids or target not in source_scene_ids:
            edges_with_unowned_endpoint += 1
        elif target in source_adjacency:
            source_adjacency[source].append(target)
            source_incoming[target].add(source)
            active_source_edge_count += 1
    source_roots = sorted(scene_id for scene_id in source_scene_ids if not source_incoming[scene_id])
    source_root_reachable: set[str] = set()
    source_root_queue = deque(source_roots)
    while source_root_queue:
        current = source_root_queue.popleft()
        if current in source_root_reachable:
            continue
        source_root_reachable.add(current)
        source_root_queue.extend(source_adjacency[current])
    source_reachable: set[str] = set()
    source_queue = deque(root for root in selected_roots if root in source_scene_ids)
    while source_queue:
        current = source_queue.popleft()
        if current in source_reachable:
            continue
        source_reachable.add(current)
        source_queue.extend(source_adjacency[current])

    components: list[list[str]] = []
    unseen = set(scene_ids)
    while unseen:
        first = min(unseen)
        component: set[str] = set()
        component_queue = deque([first])
        while component_queue:
            current = component_queue.popleft()
            if current in component:
                continue
            component.add(current)
            component_queue.extend(undirected[current] - component)
        unseen -= component
        components.append(sorted(component))
    components.sort(key=lambda component: (-len(component), component[0]))

    cases_by_scene: dict[str, list[dict[str, Any]]] = {}
    unassigned_cases: list[str] = []
    for case_id, case in sorted(testcases.items()):
        scene_id = str(case.get("scene_id", "")).strip()
        if scene_id in scene_ids:
            cases_by_scene.setdefault(scene_id, []).append({"case_id": case_id, **case})
        else:
            unassigned_cases.append(case_id)

    choice_points: list[dict[str, Any]] = []
    for source in sorted(scene_ids):
        outgoing = [edge for edge in edges if edge["source"] == source]
        if len(outgoing) < 2:
            continue
        options: list[dict[str, Any]] = []
        for edge in outgoing:
            target_cases = cases_by_scene.get(edge["target"], [])
            labels = sorted({_case_label(case) for case in target_cases if _case_label(case)})
            timeout_candidate = "nochoice" in edge["target"].casefold() or any(
                label.casefold() in {"choose nothing", "timer choice", "timeout"}
                for label in labels
            )
            options.append(
                {
                    **edge,
                    "candidate_testcase_ids": sorted(
                        str(case["case_id"]) for case in target_cases
                    ),
                    "candidate_labels": labels,
                    "label_status": (
                        "source_key"
                        if edge["choice_key"]
                        else "candidate_unverified"
                        if labels
                        else "unmapped"
                    ),
                    "timeout_candidate": timeout_candidate,
                    "execution_status": "NOT_RUN",
                }
            )
        choice_points.append(
            {
                "scene_id": source,
                "reachable_from_root": source in reachable,
                "option_count": len(outgoing),
                "options": options,
                "execution_status": "NOT_RUN",
            }
        )

    reachable_cases = sorted(
        case_id
        for scene_id in reachable
        for case_id in (str(case["case_id"]) for case in cases_by_scene.get(scene_id, []))
    )
    unreachable_cases = sorted(
        case_id
        for scene_id in scene_ids - reachable
        for case_id in (str(case["case_id"]) for case in cases_by_scene.get(scene_id, []))
    )
    missing_target_edges = sum(not edge["target_exists"] for edge in edges)
    unlabeled_edges = sum(not edge["choice_key"] for edge in edges)
    root_source_status = {root: provenance_status[root] for root in selected_roots}
    provenance_mismatch = bool(edges_with_unowned_endpoint) or any(
        status != "active" for status in root_source_status.values()
    )
    return {
        "profile": profile,
        "source_summary": source_summary or {},
        "root_selection": {"method": root_method, "roots": selected_roots},
        "summary": {
            "scene_count": len(scene_ids),
            "edge_count": len(edges),
            "reachable_scene_count": len(reachable),
            "unreachable_scene_count": len(scene_ids - reachable),
            "reachable_case_count": len(reachable_cases),
            "unreachable_case_count": len(unreachable_cases),
            "unassigned_case_count": len(unassigned_cases),
            "source_active_scene_count": len(source_scene_ids),
            "source_stale_scene_count": len(stale_scene_ids),
            "unowned_scene_count": len(unowned_scene_ids),
            "configured_root_source_reachable_count": len(source_reachable),
            "source_root_candidate_count": len(source_roots),
            "source_graph_reachable_scene_count": len(source_root_reachable),
            "source_graph_unreachable_scene_count": len(source_scene_ids - source_root_reachable),
            "active_source_edge_count": active_source_edge_count,
            "edges_with_unowned_endpoint_count": edges_with_unowned_endpoint,
            "provenance_status": "MISMATCH" if provenance_mismatch else "ALIGNED",
            "weak_component_count": len(components),
            "isolated_scene_count": sum(len(component) == 1 for component in components),
            "missing_target_edge_count": missing_target_edges,
            "unlabeled_edge_count": unlabeled_edges,
            "choice_point_count": len(choice_points),
            "source_graph_status": (
                "PARTIAL"
                if scene_ids - reachable or missing_target_edges or unlabeled_edges
                else "CONNECTED"
            ),
            "qa_status": "UNASSERTED",
        },
        "reachable_scene_ids": sorted(reachable),
        "unreachable_scene_ids": sorted(scene_ids - reachable),
        "reachable_case_ids": reachable_cases,
        "unreachable_case_ids": unreachable_cases,
        "unassigned_case_ids": unassigned_cases,
        "source_active_scene_ids": sorted(source_scene_ids),
        "source_stale_scene_ids": sorted(stale_scene_ids),
        "unowned_scene_ids": sorted(unowned_scene_ids),
        "root_source_status": root_source_status,
        "source_graph_root_candidates": source_roots,
        "source_graph_reachable_scene_ids": sorted(source_root_reachable),
        "source_scene_provenance": {
            scene_id: provenance[scene_id]
            for scene_id in sorted(source_scene_ids | stale_scene_ids)
            if scene_id in provenance
        },
        "choice_points": choice_points,
        "edges_with_missing_targets": [edge for edge in edges if not edge["target_exists"]],
        "largest_components": [
            {
                "representative": component[0],
                "size": len(component),
                "scene_ids": component[:20],
                "truncated": len(component) > 20,
            }
            for component in components[:20]
        ],
        "omitted_component_count": max(0, len(components) - 20),
        "findings": [
            "Source graph structure is not gameplay execution evidence.",
            "Blank choice keys remain unresolved even when testcase labels suggest an option name.",
            "Timeout candidates require an in-game timer observation before they can be confirmed.",
            "Reachability through unowned legacy scenes is not verified source-flow coverage.",
            "QA status remains UNASSERTED until testcase assertions and run evidence are recorded.",
        ],
    }
