from __future__ import annotations

import hashlib
import os
from enum import Enum
from typing import NamedTuple, Optional


class PBFTPhase(str, Enum):
    IDLE = "idle"
    PRE_PREPARED = "pre_prepared"
    PREPARED = "prepared"
    COMMITTED = "committed"


class PBFTMessage(NamedTuple):
    view: int
    sequence: int
    phase: PBFTPhase
    agent_id: str
    value: str
    signature: bytes


class QuorumCertificate(NamedTuple):
    view: int
    sequence: int
    value: str
    signatures: dict[str, bytes]

    @property
    def count(self) -> int:
        return len(self.signatures)


class PBFTResult(NamedTuple):
    committed: bool
    value: Optional[str]
    view: int
    certificate: Optional[QuorumCertificate]
    phase: PBFTPhase


def _derive_key(shared_seed: bytes, agent_id: str) -> bytes:
    """Derive deterministic signing key for an agent."""
    return hashlib.sha256(shared_seed + agent_id.encode()).digest()


def _sign(key: bytes, message: bytes) -> bytes:
    return hashlib.sha256(key + message).digest()


def _verify(key: bytes, message: bytes, signature: bytes) -> bool:
    expected = hashlib.sha256(key + message).digest()
    if len(expected) != len(signature):
        return False
    result = 0
    for x, y in zip(expected, signature):
        result |= x ^ y
    return result == 0


class PBFTNode:
    def __init__(self, agent_id: str, signing_key: bytes, view: int = 0):
        self.agent_id = agent_id
        self.signing_key = signing_key
        self.view = view
        self.phase = PBFTPhase.IDLE
        self.sequence = 0

    def sign_message(self, message: bytes) -> bytes:
        return _sign(self.signing_key, message)

    def verify_message(self, agent_id: str, message: bytes, signature: bytes, all_keys: dict[str, bytes]) -> bool:
        key = all_keys.get(agent_id)
        if not key:
            return False
        return _verify(key, message, signature)

    def is_primary(self, view: int, total_nodes: int) -> bool:
        return hash(self.agent_id) % total_nodes == view % total_nodes


class ByzantineNode(PBFTNode):
    """A node that lies by signing with a manipulated message."""

    def __init__(self, agent_id: str, signing_key: bytes, lie_value: str, **kwargs):
        super().__init__(agent_id, signing_key, **kwargs)
        self.lie_value = lie_value

    def sign_message(self, message: bytes) -> bytes:
        """Sign message with lie value appended — invalidates the signature for honest verification."""
        return _sign(self.signing_key, message + self.lie_value.encode())


class PBFTNetwork:
    """In-process simulation of PBFT consensus network."""

    def __init__(self, view: int = 0, f: int = 1, timeout_s: int = 10):
        self.view = view
        self.f = f
        self.quorum = 2 * f + 1
        self.timeout_s = timeout_s
        self.nodes: list[PBFTNode] = []
        self.signing_keys: dict[str, bytes] = {}  # agent_id -> signing_key
        self._sequence = 0
        self._shared_seed = os.urandom(32)

    @property
    def size(self) -> int:
        return len(self.nodes)

    def _gen_key(self, agent_id: str) -> bytes:
        return _derive_key(self._shared_seed, agent_id)

    def add_node(self, node: PBFTNode) -> None:
        self.nodes.append(node)
        self.signing_keys[node.agent_id] = node.signing_key

    def create_node(self, agent_id: str, signing_key: Optional[bytes] = None) -> PBFTNode:
        if signing_key is None:
            signing_key = self._gen_key(agent_id)
        node = PBFTNode(agent_id, signing_key, self.view)
        self.add_node(node)
        return node

    def create_byzantine_node(self, agent_id: str, lie_value: str, signing_key: Optional[bytes] = None) -> ByzantineNode:
        if signing_key is None:
            signing_key = self._gen_key(agent_id)
        node = ByzantineNode(agent_id, signing_key, lie_value, view=self.view)
        self.add_node(node)
        return node

    def propose(self, task_id: str, value: str) -> PBFTResult:
        """Run 3-phase PBFT consensus. Returns committed result or failure."""
        if len(self.nodes) < 3 * self.f + 1:
            return PBFTResult(False, None, self.view, None, PBFTPhase.IDLE)

        self._sequence += 1
        seq = self._sequence

        # Select primary
        primary_idx = self.view % len(self.nodes)
        primary = self.nodes[primary_idx]

        # Phase 1: Pre-prepare
        pre_prepare_data = f"{self.view}:{seq}:{value}".encode()
        pre_prepare = PBFTMessage(
            view=self.view,
            sequence=seq,
            phase=PBFTPhase.PRE_PREPARED,
            agent_id=primary.agent_id,
            value=value,
            signature=primary.sign_message(pre_prepare_data),
        )

        # Phase 2: Prepare (all non-primary nodes)
        prepares: list[PBFTMessage] = []
        for node in self.nodes:
            if node.agent_id == primary.agent_id:
                continue
            prepare_data = f"{self.view}:{seq}:{value}:prepare".encode()
            prepare = PBFTMessage(
                view=self.view,
                sequence=seq,
                phase=PBFTPhase.PREPARED,
                agent_id=node.agent_id,
                value=value,
                signature=node.sign_message(prepare_data),
            )
            prepares.append(prepare)

        # Phase 3: Commit (all nodes)
        commits: list[PBFTMessage] = []
        for node in self.nodes:
            commit_data = f"{self.view}:{seq}:{value}:commit".encode()
            commit = PBFTMessage(
                view=self.view,
                sequence=seq,
                phase=PBFTPhase.COMMITTED,
                agent_id=node.agent_id,
                value=value,
                signature=node.sign_message(commit_data),
            )
            commits.append(commit)

        # Verify quorum: need 2f+1 matching commit values
        commit_values: dict[str, int] = {}
        commit_sigs: dict[str, dict[str, bytes]] = {}
        for c in commits:
            commit_values[c.value] = commit_values.get(c.value, 0) + 1
            if c.value not in commit_sigs:
                commit_sigs[c.value] = {}
            commit_sigs[c.value][c.agent_id] = c.signature

        for val, count in commit_values.items():
            if count >= self.quorum:
                cert = QuorumCertificate(
                    view=self.view,
                    sequence=seq,
                    value=val,
                    signatures=commit_sigs[val],
                )
                return PBFTResult(True, val, self.view, cert, PBFTPhase.COMMITTED)

        return PBFTResult(False, None, self.view, None, PBFTPhase.IDLE)

    def verify_certificate(self, cert: QuorumCertificate) -> bool:
        """Verify a quorum certificate has valid signatures from 2f+1 nodes."""
        if cert.count < self.quorum:
            return False
        msg = f"{cert.view}:{cert.sequence}:{cert.value}:commit".encode()
        valid = 0
        for agent_id, sig in cert.signatures.items():
            if self.verify_message(agent_id, msg, sig):
                valid += 1
        return valid >= self.quorum

    def verify_message(self, agent_id: str, message: bytes, signature: bytes) -> bool:
        """Verify a message signature using stored signing keys."""
        key = self.signing_keys.get(agent_id)
        if not key:
            return False
        return _verify(key, message, signature)
