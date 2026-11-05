# qa_framework/research/ltl_compiler.py
from dataclasses import dataclass
from typing import Set, List, Dict, Tuple
import re

@dataclass
class DFA:
    states: Set[str]
    alphabet: Set[str]
    transitions: Dict[Tuple[str, str], str]
    initial_state: str
    accepting_states: Set[str]
    
    def accepts(self, trace: List[str]) -> bool:
        state = self.initial_state
        for symbol in trace:
            key = (state, symbol)
            if key not in self.transitions:
                return False
            state = self.transitions[key]
        return state in self.accepting_states

def compile_ltl_to_dfa(ltl_formula: str) -> DFA:
    """Compile LTLf formula to DFA. Simplified implementation for common patterns."""
    if "G(" in ltl_formula and "->" in ltl_formula:
        match = re.search(r'G\((\w+)\s*->\s*F\s*(\w+)\)', ltl_formula)
        if match:
            a, b = match.groups()
            return _build_gf_dfa(a, b)
    raise ValueError(f"Unsupported LTLf pattern: {ltl_formula}")

def _build_gf_dfa(a: str, b: str) -> DFA:
    """Build DFA for G(a -> F b)"""
    states = {"s0", "s1", "s2"}
    alphabet = {a, b, "other"}
    transitions = {
        ("s0", a): "s1",
        ("s0", b): "s0",
        ("s0", "other"): "s0",
        ("s1", b): "s0",
        ("s1", a): "s1",
        ("s1", "other"): "s1",
        ("s2", a): "s2",
        ("s2", b): "s2",
        ("s2", "other"): "s2",
    }
    return DFA(states, alphabet, transitions, "s0", {"s0", "s1"})
