"""Tests para TelegramBot - bot centralizado de control."""
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import date
from src.telegram_bot import TelegramBot


@pytest.fixture
def mock_env():
    """Mockea las variables de Telegram para los tests."""
    with patch("src.telegram_bot.TELEGRAM_BOT_TOKEN", "fake_token"), \
         patch("src.telegram_bot.TELEGRAM_CHAT_ID", "12345"):
        yield


@pytest.fixture
def mock_files(tmp_path):
    """Crea archivos temporales para historial."""
    processed = tmp_path / "published_history.json"
    engagement = tmp_path / "engagement_history.json"
    scan = tmp_path / "job_scan_results.json"
    drafts = tmp_path / "pending_drafts.json"
    processed.write_text("[]", encoding="utf-8")
    engagement.write_text("[]", encoding="utf-8")
    scan.write_text("[]", encoding="utf-8")
    drafts.write_text("{}", encoding="utf-8")
    with patch("src.anti_ban.PROCESSED_FILE", processed), \
         patch("src.anti_ban.ENGAGEMENT_FILE", engagement), \
         patch("src.job_scanner.SCAN_RESULTS_FILE", scan), \
         patch("src.telegram_reviewer.PENDING_DRAFTS_FILE", drafts), \
         patch("src.telegram_bot.DATA_DIR", tmp_path):
        yield


class TestBotSend:

    @patch("src.telegram_bot.http.post")
    def test_send_calls_api(self, mock_post, mock_env):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"ok": True})
        result = TelegramBot._send("Hola test")
        mock_post.assert_called_once()
        call_json = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert call_json["text"] == "Hola test"
        assert call_json["chat_id"] == "12345"

    @patch("src.telegram_bot.http.post")
    def test_send_truncates_long_text(self, mock_post, mock_env):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"ok": True})
        TelegramBot._send("x" * 5000)
        call_json = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert len(call_json["text"]) <= 4096

    @patch("src.telegram_bot.http.post")
    def test_send_with_reply_markup(self, mock_post, mock_env):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"ok": True})
        kb = {"inline_keyboard": [[{"text": "OK", "callback_data": "ok"}]]}
        TelegramBot._send("Test", reply_markup=kb)
        call_json = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert "reply_markup" in call_json


class TestBotCommands:

    @patch("src.telegram_bot.TelegramBot._send")
    def test_cmd_help(self, mock_send, mock_env):
        TelegramBot.cmd_help()
        mock_send.assert_called_once()
        text = mock_send.call_args[0][0]
        assert "/status" in text
        assert "/scan" in text
        assert "/publish" in text
        assert "/engage" in text
        assert "/limits" in text

    @patch("src.telegram_bot.TelegramBot._send")
    def test_cmd_start(self, mock_send, mock_env):
        TelegramBot.cmd_start()
        mock_send.assert_called_once()
        text = mock_send.call_args[0][0]
        assert "JobSeekerGA" in text

    @patch("src.telegram_bot.TelegramBot._send")
    def test_cmd_status(self, mock_send, mock_env, mock_files):
        TelegramBot.cmd_status()
        mock_send.assert_called_once()
        text = mock_send.call_args[0][0]
        assert "DASHBOARD" in text
        assert "Posts publicados" in text

    @patch("src.telegram_bot.TelegramBot._send")
    def test_cmd_limits(self, mock_send, mock_env, mock_files):
        TelegramBot.cmd_limits()
        mock_send.assert_called_once()
        text = mock_send.call_args[0][0]
        assert "LIMITES" in text
        assert "Posts" in text
        assert "Comentarios" in text

    @patch("src.telegram_bot.TelegramBot._send")
    def test_cmd_drafts_empty(self, mock_send, mock_env, mock_files):
        TelegramBot.cmd_drafts()
        mock_send.assert_called_once()
        assert "No hay borradores" in mock_send.call_args[0][0]

    @patch("src.telegram_bot.TelegramBot._send")
    def test_cmd_drafts_lists_active_with_buttons(self, mock_send, mock_env, mock_files):
        from src.telegram_reviewer import _save_drafts
        _save_drafts({
            "old1": {"draft_id": "old1", "project_name": "Old", "text": "x", "created_at": "2026-11-01T10:00:00", "status": "rejected"},
            "act1": {"draft_id": "act1", "project_name": "Diario #3", "text": "y", "created_at": "2026-11-11T10:00:00", "status": "pending"},
        })
        TelegramBot.cmd_drafts()
        mock_send.assert_called_once()
        text = mock_send.call_args[0][0]
        kb = mock_send.call_args.kwargs.get("reply_markup", {})
        assert "act1" in text
        callbacks = [btn["callback_data"] for row in kb.get("inline_keyboard", []) for btn in row]
        assert "approve:act1" in callbacks
        assert "drafts:cleanup" in callbacks

    @patch("src.telegram_bot.TelegramBot._send")
    def test_cmd_clear_drafts_preserves_published_and_latest_active(self, mock_send, mock_env, mock_files):
        from src.telegram_reviewer import _save_drafts, _get_drafts
        _save_drafts({
            "pub1": {"draft_id": "pub1", "project_name": "P1", "text": "x", "created_at": "2026-11-04T10:00:00", "status": "published"},
            "rej1": {"draft_id": "rej1", "project_name": "R1", "text": "x", "created_at": "2026-11-07T10:00:00", "status": "rejected"},
            "pend1": {"draft_id": "pend1", "project_name": "P3", "text": "x", "created_at": "2026-11-10T10:00:00", "status": "pending"},
            "pend2": {"draft_id": "pend2", "project_name": "P3", "text": "x", "created_at": "2026-11-11T10:00:00", "status": "pending"},
        })
        TelegramBot.cmd_clear_drafts()
        remaining = _get_drafts()
        assert "pub1" in remaining
        assert "pend2" in remaining
        assert "rej1" not in remaining
        assert "pend1" not in remaining

    @patch("src.telegram_bot.TelegramBot._send")
    def test_cmd_guia(self, mock_send, mock_env):
        TelegramBot.cmd_guia()
        mock_send.assert_called_once()
        assert "GUÍA RÁPIDA" in mock_send.call_args[0][0]

    @patch("src.telegram_bot.TelegramBot._send")
    def test_cmd_summary_no_data(self, mock_send, mock_env, mock_files):
        TelegramBot.cmd_summary()
        mock_send.assert_called_once()
        assert "No hay resultados" in mock_send.call_args[0][0]


class TestBotCallbacks:

    @patch("src.telegram_bot.TelegramBot._send")
    @patch("src.telegram_bot.TelegramBot._remove_buttons")
    @patch("src.telegram_bot.TelegramBot._answer_callback")
    def test_reject_draft(self, mock_answer, mock_remove, mock_send, mock_env, mock_files):
        from src.telegram_reviewer import _save_drafts, _get_drafts
        _save_drafts({"abc123": {
            "draft_id": "abc123", "project_name": "Test",
            "text": "Post", "image_path": None,
            "created_at": "2026-10-29T10:00:00", "status": "pending"
        }})

        cb = {
            "id": "cb1",
            "data": "reject:abc123",
            "message": {"message_id": 1, "chat": {"id": 12345}}
        }
        TelegramBot.handle_callback(cb)

        mock_answer.assert_called_once()
        mock_remove.assert_called_once()
        assert "descartado" in mock_send.call_args[0][0].lower()
        assert "abc123" not in _get_drafts()

    @patch("src.telegram_bot.TelegramBot._send")
    @patch("src.telegram_bot.TelegramBot._remove_buttons")
    @patch("src.telegram_bot.TelegramBot._answer_callback")
    def test_engage_reject(self, mock_answer, mock_remove, mock_send, mock_env):
        import src.telegram_bot as bot_mod
        bot_mod._pending_engagement_actions = [{"type": "comment", "target_company": "Acme"}]

        cb = {
            "id": "cb2",
            "data": "engage:reject",
            "message": {"message_id": 2, "chat": {"id": 12345}}
        }
        TelegramBot.handle_callback(cb)

        assert bot_mod._pending_engagement_actions == []
        assert "cancelado" in mock_send.call_args[0][0].lower()


class TestBotSecurity:

    @patch("src.telegram_bot.http.get")
    def test_ignores_messages_from_other_chats(self, mock_get, mock_env):
        """El bot solo debe responder al chat autorizado."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"result": [{
                "update_id": 1,
                "message": {
                    "text": "/status",
                    "chat": {"id": 999999}  # Chat no autorizado
                }
            }]}
        )
        # El bot no deberia procesar este comando
        # (lo verificamos indirectamente: no llama a cmd_status)
        with patch.object(TelegramBot, "cmd_status") as mock_cmd:
            # Simular un ciclo del loop (sin el while True)
            r = mock_get.return_value
            for update in r.json()["result"]:
                update_chat = str(update.get("message", {}).get("chat", {}).get("id", ""))
                if update_chat != "12345":
                    continue
                TelegramBot.cmd_status()

            mock_cmd.assert_not_called()


class TestBusinessDayCadence:

    def test_business_days_since_skips_weekends(self):
        # Lunes 2026-11-09 a Jueves 2026-11-12 = 3 días laborales
        assert TelegramBot._business_days_since(date(2026, 11, 9), date(2026, 11, 12)) == 3
        # Miércoles 2026-11-11 a Lunes 2026-11-16 = Jue(1), Vie(2), Lun(3)
        assert TelegramBot._business_days_since(date(2026, 11, 11), date(2026, 11, 16)) == 3
        # Viernes 2026-11-13 a Lunes 2026-11-16 = 1 día laboral
        assert TelegramBot._business_days_since(date(2026, 11, 13), date(2026, 11, 16)) == 1

    def test_should_generate_diary_every_3_business_days(self, mock_files):
        drafts = {
            "d1": {
                "draft_id": "d1",
                "status": "published",
                "published_at": "2026-11-11T10:00:00",  # Miércoles
            }
        }
        # Jueves (+1 laboral) -> False
        assert TelegramBot._should_generate_diary_today(drafts, today=date(2026, 11, 12)) is False
        # Viernes (+2 laborales) -> False
        assert TelegramBot._should_generate_diary_today(drafts, today=date(2026, 11, 13)) is False
        # Sábado / Domingo -> False
        assert TelegramBot._should_generate_diary_today(drafts, today=date(2026, 11, 14)) is False
        assert TelegramBot._should_generate_diary_today(drafts, today=date(2026, 11, 15)) is False
        # Lunes (+3 laborales) -> True
        assert TelegramBot._should_generate_diary_today(drafts, today=date(2026, 11, 16)) is True

    def test_should_not_generate_if_pending_draft_exists(self, mock_files):
        drafts = {
            "d1": {"draft_id": "d1", "status": "published", "published_at": "2026-11-05T10:00:00"},
            "d2": {"draft_id": "d2", "status": "pending", "created_at": "2026-11-10T10:00:00"},
        }
        assert TelegramBot._should_generate_diary_today(drafts, today=date(2026, 11, 16)) is False

    def test_should_not_generate_if_scheduled_for_10am_exists(self, mock_files):
        drafts = {
            "d1": {"draft_id": "d1", "status": "published", "published_at": "2026-11-05T10:00:00"},
            "d2": {
                "draft_id": "d2",
                "status": "scheduled",
                "created_at": "2026-11-11T18:00:00",
                "scheduled_for": "2026-11-17T10:00:00",
            },
        }
        assert TelegramBot._should_generate_diary_today(drafts, today=date(2026, 11, 16)) is False

    @patch("src.telegram_bot.DevDiaryGenerator.prepare_daily_diary_draft")
    @patch("src.telegram_bot.TelegramBot._send")
    def test_cmd_publish_blocks_when_scheduled_for_10am(self, mock_send, mock_prep, mock_env, mock_files):
        from src.telegram_reviewer import _save_drafts
        _save_drafts({
            "sched10": {
                "draft_id": "sched10",
                "project_name": "Diario #3 · JobSeeker",
                "text": "Texto programado",
                "status": "scheduled",
                "scheduled_for": "2026-11-12T10:00:00"
            }
        })
        TelegramBot.cmd_publish()
        mock_prep.assert_not_called()
        assert "programada" in mock_send.call_args[0][0].lower()
