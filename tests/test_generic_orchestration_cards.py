import pytest

from blastogene.generic_orchestration_cards import build_orchestration_event_card, validate_detail_url


def test_build_card_uses_status_template_and_button():
    card = build_orchestration_event_card("Runtime", "attention_required", "stale pending event", "https://example.com/detail")
    assert card["card"]["header"]["template"] == "red"
    assert card["card"]["elements"][1]["actions"][0]["url"] == "https://example.com/detail"


def test_rejects_non_https_detail_url():
    assert validate_detail_url("http://example.com") is False
    with pytest.raises(ValueError):
        build_orchestration_event_card("Runtime", "healthy", "ok", "ftp://example.com")
