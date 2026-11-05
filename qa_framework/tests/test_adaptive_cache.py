def test_cascade_returns_cheapest_match():
    from qa_framework.adaptive_cache import CascadeLevel, CostCascadeRetriever

    retriever = CostCascadeRetriever()
    retriever.seed("hash_abc", {"action": "play"})
    result, level = retriever.retrieve("hash_abc")
    assert result is not None
    assert result["action"] == "play"
    assert level == CascadeLevel.PERCEPTUAL_HASH


def test_cascade_falls_back_to_ocr():
    from qa_framework.adaptive_cache import CascadeLevel, CostCascadeRetriever

    retriever = CostCascadeRetriever()
    retriever.seed_ocr("PLAY START", {"action": "play"})
    result, level = retriever.retrieve("unknown_hash", ocr_words=["PLAY", "START"])
    assert result is not None
    assert level == CascadeLevel.OCR


def test_cascade_tracks_cost_savings():
    from qa_framework.adaptive_cache import CostCascadeRetriever

    retriever = CostCascadeRetriever()
    retriever.seed("hash_abc", {"action": "play"})
    retriever.retrieve("hash_abc")
    stats = retriever.stats
    assert stats.hits == 1
    assert stats.vlm_avoided == 1  # cascade hit avoided VLM call


def test_cascade_miss_returns_none():
    from qa_framework.adaptive_cache import CascadeLevel, CostCascadeRetriever

    retriever = CostCascadeRetriever()
    result, level = retriever.retrieve("unknown_hash")
    assert result is None
    assert level == CascadeLevel.NONE


def test_cascade_ocr_no_match():
    from qa_framework.adaptive_cache import CascadeLevel, CostCascadeRetriever

    retriever = CostCascadeRetriever()
    retriever.seed_ocr("PLAY START", {"action": "play"})
    result, level = retriever.retrieve("unknown", ocr_words=["STOP"])
    assert result is None
    assert level == CascadeLevel.NONE
