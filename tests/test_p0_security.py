from __future__ import annotations

import json
from pathlib import Path

from scripts.quality_gate import walk_sensitive
from scripts.safe_io import atomic_write_json
from scripts.update_news import (
    filter_waytoagi_payload,
    is_content_blocked,
    load_content_blocklist,
    sanitize_public_payload,
    sanitize_public_url,
)




ROOT = Path(__file__).resolve().parents[1]


def test_public_url_removes_sensitive_parameters():
    cleaned = sanitize_public_url(
        "https://example.com/note?id=1&xsec_token=secret-value&utm_source=test&signature=abc"
    )
    assert "xsec_token" not in cleaned
    assert "signature" not in cleaned
    assert "id=1" in cleaned


def test_public_payload_redacts_sensitive_fields_and_url_tokens():
    payload = sanitize_public_payload(
        {
            "url": "https://example.com/?access_token=secret&id=2",
            "api_key": "secret",
            "X-API-Key": "secret-too",
            "nested": {"authorization": "Bearer secret-value-123456"},
        }
    )
    assert payload["api_key"] is None
    assert payload["X-API-Key"] is None
    assert payload["nested"]["authorization"] is None
    assert "access_token" not in payload["url"]


def test_public_url_normalizes_case_and_removes_credentials_and_fragment():
    cleaned = sanitize_public_url("  HTTPS://user:password@example.com/path?id=1#private")
    assert cleaned == "https://example.com/path?id=1"


def test_quality_gate_detects_sensitive_url_parameter():
    issues = walk_sensitive({"url": "https://example.com/?xsec_token=secret"})
    assert issues


def test_quality_gate_detects_noncanonical_url_credentials_and_x_api_key():
    issues = walk_sensitive(
        {
            "url": " HTTPS://user:password@example.com/path#private",
            "X_API_KEY": "ordinary-secret-value",
        }
    )
    assert any("credentials" in issue for issue in issues)
    assert any("fragment" in issue for issue in issues)
    assert any("sensitive field" in issue for issue in issues)


def test_atomic_write_json_replaces_complete_document(tmp_path):
    path = tmp_path / "payload.json"
    path.write_text('{"old": true}', encoding="utf-8")
    atomic_write_json(path, {"new": [1, 2, 3]}, indent=2)
    assert json.loads(path.read_text(encoding="utf-8")) == {"new": [1, 2, 3]}
    assert not list(tmp_path.glob("*.tmp"))


def test_content_blocklist_supports_ids_urls_and_sources(tmp_path):
    path = tmp_path / "blocklist.txt"
    path.write_text("# removal\nitem-1\nhttps://example.com/story\nBlocked Source\n", encoding="utf-8")
    blocked = load_content_blocklist(path)
    assert is_content_blocked("item-1", "https://other.example", "Other", blocked)
    assert is_content_blocked("item-2", "https://example.com/story/", "Other", blocked)
    assert is_content_blocked("item-3", "https://other.example", "Blocked Source", blocked)


def test_waytoagi_payload_applies_blocklist_to_all_public_updates():
    payload = {
        "root_url": "https://example.com/root",
        "updates_7d": [
            {"date": "2026-08-06", "title": "Blocked", "url": "https://example.com/blocked"},
            {"date": "2026-08-05", "title": "Kept", "url": "https://example.com/kept"},
        ],
    }
    filtered = filter_waytoagi_payload(payload, {"https://example.com/blocked"})
    assert filtered["count_7d"] == 1
    assert filtered["count_today"] == 1
    assert filtered["latest_date"] == "2026-08-05"
    assert filtered["updates_today"][0]["title"] == "Kept"


def test_frontends_do_not_interpolate_external_errors_or_source_names_into_html():

    for relative in ("assets/app.js", "classic/assets/app.js"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "${newsResult.reason.message}" not in text
        assert "${waytoagiResult.reason.message}" not in text
        assert "${site.site_name || site.site_id}" not in text
        assert "titleEl.href = item.url" not in text


def test_remote_data_source_is_allowlisted_in_both_frontends():
    for relative in ("assets/app.js", "classic/assets/app.js"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "TRUSTED_DATA_HOSTS" in text
        assert "safeDataBaseUrl" in text
        assert "safeExternalUrl" in text
