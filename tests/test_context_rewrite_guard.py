from blastogene.context_rewrite_guard import compact_for_alert, evaluate_rewrite


def test_rewrite_rejects_dropped_link_and_term():
    decision = evaluate_rewrite("join https://x task42", "join", ["task42"])
    assert decision.accepted is False
    assert "dropped link" in decision.reasons


def test_compact_for_alert_is_bounded():
    assert compact_for_alert("a " * 100, 20).endswith("…")
