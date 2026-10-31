"""Tests for the scoring backtest comparison core."""

from __future__ import annotations

from scripts.backtest_scoring import compare_scoring


class TestCompareScoring:
    def test_reports_flips_and_keep_rates(self):
        items = [
            {"site_id": "s1", "title": "item one", "url": "https://e.com/1"},
            {"site_id": "s1", "title": "item two", "url": "https://e.com/2"},
            {"site_id": "s2", "title": "item three", "url": "https://e.com/3"},
        ]

        def baseline(record):
            return {"is_ai_related": True, "label": "ai_general", "score": 0.7}

        def candidate(record):
            keep = record["title"] != "item two"
            return {"is_ai_related": keep, "label": "model_release" if keep else "not_ai", "score": 0.8 if keep else 0.1}

        report = compare_scoring(items, baseline, candidate)
        assert report["total_items"] == 3
        assert report["kept_baseline"] == 3
        assert report["kept_candidate"] == 2
        assert report["flips_to_drop_count"] == 1
        assert report["flips_to_drop_samples"][0]["title"] == "item two"
        assert report["label_moves"] == {"ai_general -> model_release": 2}
        assert report["per_site"]["s1"]["kept_candidate"] == 1
