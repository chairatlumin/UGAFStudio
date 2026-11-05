from __future__ import annotations

import json
from pathlib import Path


def test_highschool_blood_case_snapshot_is_complete_and_well_formed() -> None:
    source = (
        Path(__file__).parents[2] / "qa_framework" / "testcases" / "highschool_blood_cases.json"
    )
    data = json.loads(source.read_text(encoding="utf-8"))

    cases = data["cases"]
    assert len(cases) == 409
    assert len({case["scene_id"] for case in cases}) == 408
    assert {case["final_result"] for case in cases} <= {"Pass", "Fail", "Pending"}
    assert all(case["case_id"] and case["group"] and case["scene_id"] for case in cases)
    assert data["workbook_summary_cells"] != {
        "total_scenes": data["row_level_summary"]["case_rows"],
        **data["row_level_summary"]["statuses"],
    }
