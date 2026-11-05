from qa_framework.research.ltl_compiler import compile_ltl_to_dfa

def test_compile_simple_contract():
    dfa = compile_ltl_to_dfa("G(dispatch -> F brief_exists)")
    assert dfa is not None
    assert dfa.accepts(["brief_exists", "dispatch"])
    assert not dfa.accepts(["dispatch", "report"])

def test_compile_assume_guarantee():
    dfa = compile_ltl_to_dfa("assumption: true; guarantee: G(a -> F b)")
    assert dfa is not None
