"""Memory router: dispatches queries to the correct memory tier(s)."""

from __future__ import annotations

from typing import Any

from qa_framework.memory.episodic_store import EpisodicStore
from qa_framework.memory.procedural_store import ProceduralStore
from qa_framework.memory.semantic_store import SemanticStore


class MemoryRouter:
    """Routes retrieval queries to episodic, semantic, or procedural stores
    based on query type.

    Query types:
        - "what_happened" → episodic (params: action, state_hash, or n for recent)
        - "what_is_known" → semantic (params: key_pattern)
        - "how_to"        → procedural (params: state_hash, available_actions)
        - "all"           → all three tiers
    """

    def __init__(self, db_path: str | None = None) -> None:
        self.episodic = EpisodicStore(db_path)
        self.semantic = SemanticStore(db_path)
        self.procedural = ProceduralStore(db_path)

    def record(
        self,
        session_id: str,
        state_hash: str,
        action: str,
        outcome: str,
        reward: float,
        raw_state_json: str = "",
    ) -> None:
        """Log a single interaction to episodic memory."""
        self.episodic.record(session_id, state_hash, action, outcome, reward, raw_state_json)

    def route_query(self, query_type: str, **params: Any) -> list[dict[str, Any]]:
        """Route a query to the appropriate memory tier(s).

        Returns a list of results (possibly empty). Each result dict
        includes a "_tier" key indicating the source store.
        """
        if query_type == "what_happened":
            return self._query_what_happened(**params)
        if query_type == "what_is_known":
            return self._query_what_is_known(**params)
        if query_type == "how_to":
            return self._query_how_to(**params)
        if query_type == "all":
            results: list[dict[str, Any]] = []
            results.extend(self._query_what_happened(**params))
            results.extend(self._query_what_is_known(**params))
            results.extend(self._query_how_to(**params))
            return results
        return []

    def query(self, query_type: str, **params: Any) -> list[dict[str, Any]]:
        """Alias for route_query."""
        return self.route_query(query_type, **params)

    def _query_what_happened(self, **params: Any) -> list[dict[str, Any]]:
        if params.get("action"):
            rows = self.episodic.get_by_action(params["action"], limit=params.get("limit", 20))
        elif params.get("state_hash"):
            rows = self.episodic.get_by_state(params["state_hash"])
        else:
            n = params.get("n", 50)
            rows = self.episodic.get_recent(n)
        return [{**r, "_tier": "episodic"} for r in rows]

    def _query_what_is_known(self, **params: Any) -> list[dict[str, Any]]:
        key_pattern = params.get("key_pattern", "")
        rows = self.semantic.query_facts(key_pattern)
        return [{**r, "_tier": "semantic"} for r in rows]

    def _query_how_to(self, **params: Any) -> list[dict[str, Any]]:
        state_hash = params.get("state_hash", "")
        available = params.get("available_actions")
        rows = self.procedural.find_matching_skills(state_hash, available)
        return [{**r, "_tier": "procedural"} for r in rows]

    def consolidate(self, session_id: str) -> int:
        """Run episodic→semantic consolidation for a session.
        Returns the number of facts consolidated.
        """
        return self.semantic.consolidate_from_episodic(self.episodic, session_id)

    def summarize_session(self, session_id: str) -> dict[str, Any]:
        """Produce a summary dict for a completed session."""
        records = self.episodic.get_session_records(session_id)
        unique_states = len({r["state_hash"] for r in records})
        facts = self.semantic.consolidate_from_episodic(self.episodic, session_id)
        top_skills = self.procedural.get_top_skills(3)

        return {
            "session_id": session_id,
            "total_actions": len(records),
            "unique_states": unique_states,
            "facts_learned": facts,
            "top_skills": [
                {"id": s["id"], "name": s["name"], "success_count": s["success_count"]}
                for s in top_skills
            ],
        }

    def prune(self, older_than_sessions: int = 7) -> int:
        """Prune old episodic records."""
        return self.episodic.prune(older_than_sessions)
