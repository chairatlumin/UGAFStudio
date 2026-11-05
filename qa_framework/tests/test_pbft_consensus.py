from __future__ import annotations

import os

import pytest

from qa_framework.pbft_consensus import (
    PBFTMessage,
    PBFTNetwork,
    PBFTNode,
    PBFTPhase,
    PBFTResult,
    QuorumCertificate,
    _derive_key,
    _sign,
    _verify,
)


class TestKeyInfrastructure:
    def test_derive_key_deterministic(self):
        seed = b"test-seed-32-bytes-long-string"
        key1 = _derive_key(seed, "agent-1")
        key2 = _derive_key(seed, "agent-1")
        assert key1 == key2
        assert len(key1) == 32

    def test_derive_key_unique_per_agent(self):
        seed = b"test-seed-32-bytes-long-string"
        key1 = _derive_key(seed, "agent-1")
        key2 = _derive_key(seed, "agent-2")
        assert key1 != key2

    def test_sign_and_verify(self):
        key = os.urandom(32)
        msg = b"test message"
        sig = _sign(key, msg)
        assert _verify(key, msg, sig) is True
        assert _verify(key, b"wrong", sig) is False
        assert _verify(os.urandom(32), msg, sig) is False


class TestPBFTNode:
    def test_node_creation(self):
        key = os.urandom(32)
        node = PBFTNode("agent-1", key)
        assert node.agent_id == "agent-1"
        assert node.phase == PBFTPhase.IDLE

    def test_sign_and_verify(self):
        key = os.urandom(32)
        node = PBFTNode("agent-1", key)
        msg = b"pre-prepare:0:1:pass"
        sig = node.sign_message(msg)
        assert len(sig) == 32
        all_keys = {node.agent_id: node.signing_key}
        assert node.verify_message(node.agent_id, msg, sig, all_keys)


class TestPBFTNetwork:
    def test_add_node(self):
        net = PBFTNetwork(f=1)
        net.create_node("a1")
        assert net.size == 1
        assert "a1" in net.signing_keys

    def test_create_byzantine_node(self):
        net = PBFTNetwork(f=1)
        net.create_byzantine_node("bad", lie_value="fail")
        assert net.size == 1

    def test_basic_consensus(self):
        net = PBFTNetwork(view=0, f=1)
        for i in range(4):
            net.create_node(f"agent-{i}")
        result = net.propose("task-1", "pass")
        assert result.committed is True
        assert result.value == "pass"
        assert result.certificate is not None
        assert result.certificate.count >= 3

    def test_byzantine_tolerance(self):
        from qa_framework.pbft_consensus import ByzantineNode
        net = PBFTNetwork(view=0, f=1)
        net.create_node("agent-0")
        net.create_node("agent-1")
        net.create_node("agent-2")
        # Byzantine node with conflicting lie_value
        byz = ByzantineNode("agent-3", net._gen_key("agent-3"), lie_value="fail")
        net.add_node(byz)
        result = net.propose("task-2", "pass")
        # Even with a Byzantine node, honest majority should commit "pass"
        assert result.committed is True
        assert result.value == "pass"

    def test_quorum_certificate(self):
        net = PBFTNetwork(view=0, f=1)
        for i in range(4):
            net.create_node(f"agent-{i}")
        result = net.propose("task-3", "value")
        assert result.certificate is not None
        cert = result.certificate
        assert cert.view == 0
        assert cert.value == "value"
        assert cert.count >= 3

    def test_verify_certificate(self):
        net = PBFTNetwork(view=0, f=1)
        for i in range(4):
            net.create_node(f"agent-{i}")
        result = net.propose("task-4", "pass")
        assert result.certificate is not None
        assert net.verify_certificate(result.certificate) is True

    def test_insufficient_nodes(self):
        net = PBFTNetwork(f=1)
        net.create_node("a1")
        net.create_node("a2")
        # Need at least 3f+1 = 4 nodes for f=1
        result = net.propose("task-5", "pass")
        assert result.committed is False
        assert result.value is None

    def test_multiple_proposals(self):
        net = PBFTNetwork(view=0, f=1)
        for i in range(4):
            net.create_node(f"agent-{i}")
        r1 = net.propose("task-a", "pass")
        r2 = net.propose("task-b", "fail")
        assert r1.committed and r1.value == "pass"
        assert r2.committed and r2.value == "fail"
        assert r1.certificate.sequence < r2.certificate.sequence


class TestPBFTResult:
    def test_named_tuple_access(self):
        cert = QuorumCertificate(view=0, sequence=1, value="v", signatures={})
        result = PBFTResult(committed=True, value="v", view=0, certificate=cert, phase=PBFTPhase.COMMITTED)
        assert result.committed is True
        assert result.value == "v"
        assert result.phase == PBFTPhase.COMMITTED


class TestPBFTMessage:
    def test_named_tuple(self):
        msg = PBFTMessage(
            view=0, sequence=1, phase=PBFTPhase.PRE_PREPARED,
            agent_id="a1", value="pass", signature=b"sig"
        )
        assert msg.agent_id == "a1"
        assert msg.phase == PBFTPhase.PRE_PREPARED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
