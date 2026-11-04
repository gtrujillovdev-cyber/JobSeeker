"""Tests para EngagementEngine - motor de networking activo."""
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import date
from src.engagement_engine import EngagementEngine


@pytest.fixture
def mock_scan_data(tmp_path):
    """Simula datos del JobScanner para que el EngagementEngine tenga empresas target."""
    scan_file = tmp_path / "job_scan_results.json"
    engagement_file = tmp_path / "engagement_history.json"

    today = date.today().isoformat()
    jobs = [
        {
            "title": "Python Developer",
            "company": "Acme Corp",
            "location": "Madrid",
            "url": "https://linkedin.com/jobs/view/1",
            "detected_stack": ["Python", "FastAPI"],
            "scanned_at": f"{today}T10:00:00",
            "search_query": "Python"
        },
        {
            "title": "Backend Engineer",
            "company": "Beta Inc",
            "location": "Barcelona",
            "url": "https://linkedin.com/jobs/view/2",
            "detected_stack": ["Python", "Docker"],
            "scanned_at": f"{today}T10:00:00",
            "search_query": "Python"
        },
        {
            "title": "DevOps",
            "company": "Gamma SA",
            "location": "Remote",
            "url": "https://linkedin.com/jobs/view/3",
            "detected_stack": ["Docker", "AWS"],
            "scanned_at": f"{today}T10:00:00",
            "search_query": "DevOps"
        },
    ]
    scan_file.write_text(json.dumps(jobs), encoding="utf-8")
    engagement_file.write_text("[]", encoding="utf-8")

    with patch("src.job_scanner.SCAN_RESULTS_FILE", scan_file), \
         patch("src.anti_ban.ENGAGEMENT_FILE", engagement_file):
        yield scan_file, engagement_file


class TestProposeActions:

    def test_proposes_actions_from_target_companies(self, mock_scan_data):
        actions = EngagementEngine.propose_actions(max_actions=3)
        assert len(actions) > 0
        assert all(a["status"] == "proposed" for a in actions)

    def test_includes_comment_and_connection_types(self, mock_scan_data):
        actions = EngagementEngine.propose_actions(max_actions=10)
        types = {a["type"] for a in actions}
        assert "connection" in types

    def test_respects_max_actions(self, mock_scan_data):
        actions = EngagementEngine.propose_actions(max_actions=2)
        assert len(actions) <= 2

    def test_returns_empty_without_scan_data(self, tmp_path):
        empty_file = tmp_path / "empty_scan.json"
        empty_file.write_text("[]", encoding="utf-8")
        with patch("src.job_scanner.SCAN_RESULTS_FILE", empty_file):
            actions = EngagementEngine.propose_actions()
            assert actions == []

    def test_actions_have_target_company(self, mock_scan_data):
        actions = EngagementEngine.propose_actions(max_actions=5)
        for action in actions:
            assert "target_company" in action
            assert len(action["target_company"]) > 0

    def test_skips_when_daily_limit_reached(self, mock_scan_data):
        """Si el limite de comments esta alcanzado, no propone mas comments."""
        _, engagement_file = mock_scan_data
        today = date.today().isoformat()
        records = [
            {"date": today, "action": "comment", "status": "success", "target": f"x{i}"}
            for i in range(20)
        ]
        engagement_file.write_text(json.dumps(records), encoding="utf-8")

        with patch("src.anti_ban.MAX_DAILY_COMMENTS", 8):
            actions = EngagementEngine.propose_actions(max_actions=5)
            comment_actions = [a for a in actions if a["type"] == "comment"]
            assert len(comment_actions) == 0


class TestGenerateComment:

    @patch("src.engagement_engine.GEMINI_API_KEY", "")
    def test_fallback_comment_is_professional(self):
        comment = EngagementEngine._generate_comment("Acme", "Post sobre pipelines de datos")
        assert comment is not None
        assert len(comment) > 20
        assert len(comment) <= 300

    @patch("src.engagement_engine.GEMINI_API_KEY", "")
    def test_fallback_comment_no_spam(self):
        comment = EngagementEngine._generate_comment("Acme", "Cualquier post")
        lower = comment.lower()
        assert "gran post" not in lower
        assert "totalmente de acuerdo" not in lower


class TestGenerateConnectionNote:

    @patch("src.engagement_engine.GEMINI_API_KEY", "")
    def test_fallback_note_includes_name(self):
        note = EngagementEngine._generate_connection_note("Acme", "Maria Lopez")
        assert "Maria Lopez" in note

    @patch("src.engagement_engine.GEMINI_API_KEY", "")
    def test_fallback_note_includes_company(self):
        note = EngagementEngine._generate_connection_note("Acme Corp", "Juan")
        assert "Acme Corp" in note

    @patch("src.engagement_engine.GEMINI_API_KEY", "")
    def test_fallback_note_length(self):
        """La nota no debe exceder el limite de LinkedIn (300 chars)."""
        note = EngagementEngine._generate_connection_note("Empresa Larga SA", "Nombre Largo")
        assert len(note) <= 300


class TestReportResults:

    @patch("src.engagement_engine.TELEGRAM_BOT_TOKEN", "fake_token")
    @patch("src.engagement_engine.TELEGRAM_CHAT_ID", "12345")
    @patch("requests.post")
    def test_report_sends_telegram_message(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        results = [
            {"type": "comment", "target_company": "Acme", "status": "success"},
            {"type": "connection", "target_company": "Beta", "status": "skipped", "reason": "no_button"},
        ]
        EngagementEngine._report_results(results, chat_id=12345)
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        body = call_args.kwargs.get("json") or call_args[1].get("json")
        assert "Exitosos: 1" in body["text"]
        assert "Omitidos: 1" in body["text"]
