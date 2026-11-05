from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from app.database import database as database_module
from app.database.database import QADatabase
from qa_framework import mcp_tools


def test_campaign_persists_selected_cases_and_idempotency(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(database_module, "PROFILE_DB_DIR", tmp_path / "profiles")
    monkeypatch.setattr(mcp_tools, "_read_profiles", lambda: {
        "demo": {"game_type": "fmv_visual_novel"}
    })
    monkeypatch.setattr(mcp_tools, "_resolve_cases_for_profile", lambda _profile, _ids: [
        {"id": "FMV-CHOICE-01", "category": "choice"},
        {"id": "FMV-TIMEOUT-01", "category": "timeout"},
    ])
    monkeypatch.setattr(mcp_tools, "describe_qa_selection_tool", lambda _profile: {"cases": []})
    db = QADatabase.for_profile("demo")
    starts: list[dict[str, object]] = []

    def fake_start(**kwargs):
        db.register_game("demo", "Demo", "fmv_visual_novel")
        starts.append(kwargs)
        return {
            "run_id": "run-001", "profile": "demo", "status": "RUNNING",
            "qa_status": "UNASSERTED",
        }

    monkeypatch.setattr(mcp_tools, "start_live_session_tool", fake_start)
    first = mcp_tools.start_qa_campaign_tool(
        "demo", case_ids=["FMV-CHOICE-01"], confirm_gameplay_input=True,
        idempotency_key="hermes-task-77",
    )
    second = mcp_tools.start_qa_campaign_tool(
        "demo", case_ids=["FMV-CHOICE-01"], confirm_gameplay_input=True,
        idempotency_key="hermes-task-77",
    )

    assert len(starts) == 1
    assert first["campaign"]["campaign_id"] == second["campaign"]["campaign_id"]
    assert second["reused"] is True
    assert starts[0]["case_ids"] == ["FMV-CHOICE-01", "FMV-TIMEOUT-01"]
    stored = db.get_qa_campaign(profile="demo", idempotency_key="hermes-task-77")
    assert stored is not None
    assert stored["status"] == "RUNNING"
    assert stored["run_ids"] == ["run-001"]
    assert stored["selected_categories"] == ["choice", "timeout"]
    assert mcp_tools.list_qa_campaigns_tool("demo")["count"] == 1


def test_campaign_start_failure_is_durably_blocked(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(database_module, "PROFILE_DB_DIR", tmp_path / "profiles")
    monkeypatch.setattr(mcp_tools, "_read_profiles", lambda: {
        "demo": {"game_type": "fmv_visual_novel"}
    })
    monkeypatch.setattr(mcp_tools, "_resolve_cases_for_profile", lambda _profile, _ids: [
        {"id": "FMV-CHOICE-01", "category": "choice"}
    ])
    db = QADatabase.for_profile("demo")
    db.register_game("demo", "Demo", "fmv_visual_novel")
    monkeypatch.setattr(
        mcp_tools, "start_live_session_tool", lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("game lock is held")
        )
    )

    try:
        mcp_tools.start_qa_campaign_tool(
            "demo", case_ids=["FMV-CHOICE-01"], confirm_gameplay_input=True,
            idempotency_key="blocked-task",
        )
    except RuntimeError as exc:
        assert "game lock" in str(exc)
    else:
        raise AssertionError("start failure should be propagated")

    stored = db.get_qa_campaign(profile="demo", idempotency_key="blocked-task")
    assert stored is not None and stored["status"] == "BLOCKED"
    assert stored["result"]["error"] == "game lock is held"


def test_idempotency_key_cannot_be_reused_for_another_selection(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(database_module, "PROFILE_DB_DIR", tmp_path / "profiles")
    monkeypatch.setattr(mcp_tools, "_read_profiles", lambda: {
        "demo": {"game_type": "fmv_visual_novel"}
    })
    cases = {
        "FMV-CHOICE-01": {"id": "FMV-CHOICE-01", "category": "choice"},
        "FMV-TIMEOUT-01": {"id": "FMV-TIMEOUT-01", "category": "timeout"},
    }
    monkeypatch.setattr(
        mcp_tools, "_resolve_cases_for_profile",
        lambda _profile, ids: [cases[case_id] for case_id in ids],
    )
    starts: list[dict[str, object]] = []

    def fake_start(**kwargs):
        starts.append(kwargs)
        return {"run_id": "run-001", "status": "RUNNING", "qa_status": "UNASSERTED"}

    monkeypatch.setattr(mcp_tools, "start_live_session_tool", fake_start)
    mcp_tools.start_qa_campaign_tool(
        "demo", case_ids=["FMV-CHOICE-01"], idempotency_key="same-key"
    )
    try:
        mcp_tools.start_qa_campaign_tool(
            "demo", case_ids=["FMV-TIMEOUT-01"], idempotency_key="same-key"
        )
    except ValueError as exc:
        assert "different testcase selection" in str(exc)
    else:
        raise AssertionError("a key for one selection must not alias another campaign")
    assert len(starts) == 1


def test_profile_migration_copies_campaign_and_run_children(tmp_path) -> None:
    source = QADatabase(tmp_path / "source.sqlite3")
    source.register_game("demo", "Demo", "fmv_visual_novel")
    source.record_run(
        {
            "run_id": "run-001", "profile": "demo", "status": "COMPLETED",
            "qa_status": "UNASSERTED", "testcase_id": "FMV-CHOICE-01",
        },
        tmp_path / "run_manifest.json",
    )
    source.record_case_result("run-001", "FMV-CHOICE-01", "UNASSERTED", expected=["branch"])
    source.record_feedback("feedback-001", "flow", "Observed route", "run-001", "FMV-CHOICE-01")
    source.create_qa_campaign(
        campaign_id="campaign-001", profile="demo", idempotency_key="task-1",
        status="INTERRUPTED", selected_case_ids=["FMV-CHOICE-01"],
        selected_categories=["choice"], run_ids=["run-001"],
    )
    attempt = source.reserve_qa_campaign_attempt("campaign-001", "retry-1")["attempt"]
    source.update_qa_campaign_attempt(
        "campaign-001", attempt["attempt_id"],
        status="COMPLETED", run_id="run-001",
    )

    destination = QADatabase(tmp_path / "destination.sqlite3")
    destination._migrate_profile_from_shared(tmp_path / "source.sqlite3", "demo")

    campaign = destination.get_qa_campaign("campaign-001")
    assert campaign is not None and campaign["run_ids"] == ["run-001"]
    assert campaign is not None and campaign["attempts"][0]["retry_key"] == "retry-1"
    assert len(destination.list_runs(profile="demo")) == 1
    assert destination.list_testcase_results("run-001")[0]["case_id"] == "FMV-CHOICE-01"
    assert destination.list_feedback("run-001")[0]["feedback_id"] == "feedback-001"


def test_campaign_reservation_allows_one_active_run_per_profile(tmp_path) -> None:
    database = QADatabase(tmp_path / "campaign-lock.sqlite3")
    database.register_game("demo", "Demo", "fmv_visual_novel")
    database.register_game("other", "Other", "platformer")

    assert database.create_qa_campaign(
        campaign_id="demo-1", profile="demo", idempotency_key="one",
        status="STARTING", selected_case_ids=["A"], selected_categories=[], run_ids=[],
    )
    assert not database.create_qa_campaign(
        campaign_id="demo-2", profile="demo", idempotency_key="two",
        status="STARTING", selected_case_ids=["B"], selected_categories=[], run_ids=[],
    )
    assert database.create_qa_campaign(
        campaign_id="other-1", profile="other", idempotency_key="one",
        status="STARTING", selected_case_ids=["A"], selected_categories=[], run_ids=[],
    )


def test_campaign_reservation_is_atomic_across_database_connections(tmp_path) -> None:
    path = tmp_path / "campaign-race.sqlite3"
    setup = QADatabase(path)
    setup.register_game("demo", "Demo", "fmv_visual_novel")
    barrier = threading.Barrier(2)

    def reserve(campaign_id: str) -> bool:
        database = QADatabase(path)
        barrier.wait(timeout=5)
        return database.create_qa_campaign(
            campaign_id=campaign_id, profile="demo", idempotency_key=campaign_id,
            status="STARTING", selected_case_ids=[campaign_id],
            selected_categories=[], run_ids=[],
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        reservations = list(executor.map(reserve, ("race-a", "race-b")))

    assert sorted(reservations) == [False, True]
    assert len(setup.list_qa_campaigns("demo")) == 1


def test_campaign_reconciliation_marks_dead_worker_interrupted(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(database_module, "PROFILE_DB_DIR", tmp_path / "profiles")
    database = QADatabase.for_profile("demo")
    database.register_game("demo", "Demo", "fmv_visual_novel")
    database.create_qa_campaign(
        campaign_id="campaign-dead", profile="demo", idempotency_key="dead-worker",
        status="RUNNING", selected_case_ids=["A"], selected_categories=[],
        run_ids=["run-dead"],
        result={"run_id": "run-dead", "worker_pid": 93421, "worker_created_epoch": 10.0},
    )

    def missing_process(_pid):
        raise mcp_tools.psutil.NoSuchProcess(_pid)

    monkeypatch.setattr(mcp_tools.psutil, "Process", missing_process)
    result = mcp_tools.list_qa_campaigns_tool("demo")

    campaign = result["campaigns"][0]
    assert campaign["status"] == "INTERRUPTED"
    assert campaign["qa_status"] == "UNASSERTED"
    assert campaign["result"]["recovery_note"]
    assert campaign["finished_at_utc"]


def test_campaign_reconciliation_keeps_verified_worker_running(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(database_module, "PROFILE_DB_DIR", tmp_path / "profiles")
    database = QADatabase.for_profile("demo")
    database.register_game("demo", "Demo", "fmv_visual_novel")
    database.create_qa_campaign(
        campaign_id="campaign-live", profile="demo", idempotency_key="live-worker",
        status="RUNNING", selected_case_ids=["A"], selected_categories=[],
        run_ids=["run-live"],
        result={"run_id": "run-live", "worker_pid": 12345, "worker_created_epoch": 1234.5},
    )

    class LiveWorker:
        def create_time(self):
            return 1234.5

        def cmdline(self):
            return ["python.exe", "--trace-path", "C:/runs/run-live/trace.jsonl"]

    monkeypatch.setattr(mcp_tools.psutil, "Process", lambda _pid: LiveWorker())
    result = mcp_tools.list_qa_campaigns_tool("demo")

    assert result["campaigns"][0]["status"] == "RUNNING"


def test_campaign_retry_attempt_is_idempotent_and_keeps_run_history(tmp_path) -> None:
    database = QADatabase(tmp_path / "campaign-retry.sqlite3")
    database.register_game("demo", "Demo", "fmv_visual_novel")
    database.create_qa_campaign(
        campaign_id="campaign-1", profile="demo", idempotency_key="first-request",
        status="INTERRUPTED", selected_case_ids=["CASE-1"],
        selected_categories=["flow"], run_ids=["run-1"],
        result={"run_id": "run-1", "recovery_note": "worker exited"},
    )

    reservation = database.reserve_qa_campaign_attempt("campaign-1", "retry-1")
    repeated = database.reserve_qa_campaign_attempt("campaign-1", "retry-1")
    assert reservation["created"] is True
    assert repeated["reused"] is True
    attempt_id = reservation["attempt"]["attempt_id"]
    assert database.update_qa_campaign_attempt(
        "campaign-1", attempt_id, status="RUNNING", run_id="run-2",
        result={"worker_pid": 12345, "worker_created_epoch": 10.0},
    )
    active = database.get_qa_campaign("campaign-1")
    assert active is not None
    assert active["status"] == "RUNNING"
    assert active["run_ids"] == ["run-1", "run-2"]
    assert active["result"]["worker_pid"] == 12345
    assert database.update_qa_campaign_attempt(
        "campaign-1", attempt_id, status="COMPLETED", run_id="run-2",
    )
    completed = database.get_qa_campaign("campaign-1")
    assert completed is not None
    assert completed["status"] == "COMPLETED"
    assert completed["attempts"][0]["status"] == "COMPLETED"


def test_retry_campaign_uses_selected_cases_and_reuses_retry_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(database_module, "PROFILE_DB_DIR", tmp_path / "profiles")
    monkeypatch.setattr(mcp_tools, "_read_profiles", lambda: {
        "demo": {"game_type": "fmv_visual_novel"}
    })
    cases = {"CASE-1": {"id": "CASE-1", "category": "flow"}}
    monkeypatch.setattr(
        mcp_tools,
        "_resolve_cases_for_profile",
        lambda _profile, ids: [cases[case_id] for case_id in ids if case_id in cases],
    )
    database = QADatabase.for_profile("demo")
    database.register_game("demo", "Demo", "fmv_visual_novel")
    database.create_qa_campaign(
        campaign_id="campaign-retry", profile="demo", idempotency_key="original",
        status="INTERRUPTED", selected_case_ids=["CASE-1"],
        selected_categories=["flow"], run_ids=["old-run"],
    )
    calls: list[dict[str, object]] = []

    def fake_start(**kwargs):
        calls.append(kwargs)
        return {"run_id": "new-run", "status": "RUNNING", "qa_status": "UNASSERTED"}

    monkeypatch.setattr(mcp_tools, "start_live_session_tool", fake_start)
    first = mcp_tools.retry_qa_campaign_tool(
        "campaign-retry", "retry-once", confirm_gameplay_input=True
    )
    second = mcp_tools.retry_qa_campaign_tool(
        "campaign-retry", "retry-once", confirm_gameplay_input=True
    )

    assert len(calls) == 1
    assert calls[0]["case_ids"] == ["CASE-1"]
    assert calls[0]["confirm_gameplay_input"] is True
    assert first["campaign"]["run_ids"] == ["old-run", "new-run"]
    assert second["reused"] is True
    assert second["attempt"]["attempt_id"] == first["attempt"]["attempt_id"]


def test_retry_campaign_requires_input_confirmation_and_exact_case_mapping(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(database_module, "PROFILE_DB_DIR", tmp_path / "profiles")
    monkeypatch.setattr(mcp_tools, "_read_profiles", lambda: {
        "demo": {"game_type": "fmv_visual_novel"}
    })
    database = QADatabase.for_profile("demo")
    database.register_game("demo", "Demo", "fmv_visual_novel")
    database.create_qa_campaign(
        campaign_id="campaign-gated", profile="demo", idempotency_key="original",
        status="BLOCKED", selected_case_ids=["CASE-MISSING"],
        selected_categories=[], run_ids=[],
    )
    starts: list[object] = []
    monkeypatch.setattr(mcp_tools, "start_live_session_tool", lambda **kw: starts.append(kw))

    try:
        mcp_tools.retry_qa_campaign_tool("campaign-gated", "retry-1")
    except ValueError as exc:
        assert "confirm_gameplay_input" in str(exc)
    else:
        raise AssertionError("retry without explicit input confirmation must fail")

    monkeypatch.setattr(mcp_tools, "_resolve_cases_for_profile", lambda _profile, _ids: [])
    try:
        mcp_tools.retry_qa_campaign_tool(
            "campaign-gated", "retry-2", confirm_gameplay_input=True
        )
    except ValueError as exc:
        assert "no longer resolves exactly" in str(exc)
    else:
        raise AssertionError("stale case selection must fail closed")

    assert starts == []
    stored = database.get_qa_campaign("campaign-gated")
    assert stored is not None and stored["attempts"] == []
