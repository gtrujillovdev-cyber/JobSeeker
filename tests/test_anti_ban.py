"""Tests para AntiBanValidator - control de limites de publicacion y engagement."""
import json
import pytest
from unittest.mock import patch
from pathlib import Path
from src.anti_ban import AntiBanValidator


@pytest.fixture
def tmp_processed_file(tmp_path):
    """Crea un archivo temporal para historial de publicaciones."""
    f = tmp_path / "published_history.json"
    f.write_text("[]", encoding="utf-8")
    with patch("src.anti_ban.PROCESSED_FILE", f):
        yield f


@pytest.fixture
def tmp_engagement_file(tmp_path):
    """Crea un archivo temporal para historial de engagement."""
    f = tmp_path / "engagement_history.json"
    f.write_text("[]", encoding="utf-8")
    with patch("src.anti_ban.ENGAGEMENT_FILE", f):
        yield f


class TestPublicationLimits:

    def test_allows_first_post(self, tmp_processed_file):
        assert AntiBanValidator.check_daily_limit() is True

    def test_blocks_when_limit_reached(self, tmp_processed_file):
        from datetime import date
        today = date.today().isoformat()
        records = [
            {"date": today, "status": "success", "project_name": f"test{i}"}
            for i in range(5)
        ]
        tmp_processed_file.write_text(json.dumps(records), encoding="utf-8")

        with patch("src.anti_ban.MAX_DAILY_POSTS", 2):
            assert AntiBanValidator.check_daily_limit() is False

    def test_ignores_failed_posts(self, tmp_processed_file):
        from datetime import date
        today = date.today().isoformat()
        records = [
            {"date": today, "status": "failed", "project_name": "test1"},
            {"date": today, "status": "failed", "project_name": "test2"},
        ]
        tmp_processed_file.write_text(json.dumps(records), encoding="utf-8")
        assert AntiBanValidator.check_daily_limit() is True

    def test_record_publication(self, tmp_processed_file):
        AntiBanValidator.record_publication("TestProject", "Texto de prueba largo", "/img.png", status="success")
        records = json.loads(tmp_processed_file.read_text(encoding="utf-8"))
        assert len(records) == 1
        assert records[0]["project_name"] == "TestProject"
        assert records[0]["status"] == "success"
        assert len(records[0]["caption_preview"]) <= 100


class TestEngagementLimits:

    def test_allows_first_engagement(self, tmp_engagement_file):
        assert AntiBanValidator.check_engagement_limit("comment") is True
        assert AntiBanValidator.check_engagement_limit("connection") is True
        assert AntiBanValidator.check_engagement_limit("reaction") is True

    def test_blocks_comments_at_limit(self, tmp_engagement_file):
        from datetime import date
        today = date.today().isoformat()
        records = [
            {"date": today, "action": "comment", "status": "success", "target": f"co{i}"}
            for i in range(10)
        ]
        tmp_engagement_file.write_text(json.dumps(records), encoding="utf-8")

        with patch("src.anti_ban.MAX_DAILY_COMMENTS", 8):
            assert AntiBanValidator.check_engagement_limit("comment") is False

    def test_blocks_connections_at_limit(self, tmp_engagement_file):
        from datetime import date
        today = date.today().isoformat()
        records = [
            {"date": today, "action": "connection", "status": "success", "target": f"co{i}"}
            for i in range(6)
        ]
        tmp_engagement_file.write_text(json.dumps(records), encoding="utf-8")

        with patch("src.anti_ban.MAX_DAILY_CONNECTIONS", 5):
            assert AntiBanValidator.check_engagement_limit("connection") is False

    def test_different_actions_independent(self, tmp_engagement_file):
        """El limite de comments no afecta al de connections."""
        from datetime import date
        today = date.today().isoformat()
        records = [
            {"date": today, "action": "comment", "status": "success", "target": f"co{i}"}
            for i in range(10)
        ]
        tmp_engagement_file.write_text(json.dumps(records), encoding="utf-8")

        with patch("src.anti_ban.MAX_DAILY_COMMENTS", 8):
            assert AntiBanValidator.check_engagement_limit("comment") is False
            assert AntiBanValidator.check_engagement_limit("connection") is True

    def test_record_engagement(self, tmp_engagement_file):
        AntiBanValidator.record_engagement("comment", "Acme Corp", "Buen enfoque tecnico")
        records = json.loads(tmp_engagement_file.read_text(encoding="utf-8"))
        assert len(records) == 1
        assert records[0]["action"] == "comment"
        assert records[0]["target"] == "Acme Corp"
        assert records[0]["status"] == "success"

    def test_today_engagement_summary(self, tmp_engagement_file):
        AntiBanValidator.record_engagement("comment", "Acme")
        AntiBanValidator.record_engagement("comment", "Beta Inc")
        AntiBanValidator.record_engagement("connection", "Gamma")
        summary = AntiBanValidator.get_today_engagement_summary()
        assert summary["comment"] == 2
        assert summary["connection"] == 1

    def test_unknown_action_always_allowed(self, tmp_engagement_file):
        """Acciones no definidas en _ENGAGEMENT_LIMITS pasan siempre."""
        assert AntiBanValidator.check_engagement_limit("unknown_action") is True
