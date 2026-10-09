from __future__ import annotations

from datetime import datetime, timezone

from scripts.update_news import waytoagi_updates_to_raw_items


NOW = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)


def test_waytoagi_latest_updates_become_community_raw_items():
    payload = {
        "root_url": "https://waytoagi.example/wiki",
        "latest_date": "2026-06-15",
        "updates_today": [
            {"date": "2026-06-15", "title": "Agent loop community writeup", "url": "https://waytoagi.example/wiki"}
        ],
    }

    items = waytoagi_updates_to_raw_items(payload, NOW)

    assert len(items) == 1
    assert items[0].site_id == "waytoagi"
    assert items[0].site_name == "WaytoAGI"
    assert items[0].source == "社区更新 · 2026-06-15"
    assert items[0].published_at == NOW
