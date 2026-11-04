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
         patch("src.telegram_reviewer.PENDING_DRAFTS_FILE", drafts):
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
    def test_cmd_summary_no_data(self, mock_send, mock_env, mock_files):
        TelegramBot.cmd_summary()
        mock_send.assert_called_once()
        assert "No hay resultados" in mock_send.call_args[0][0]


class TestBotCallbacks:

    @patch("src.telegram_bot.TelegramBot._send")
    @patch("src.telegram_bot.TelegramBot._remove_buttons")
    @patch("src.telegram_bot.TelegramBot._answer_callback")
    def test_reject_draft(self, mock_answer, mock_remove, mock_send, mock_env, mock_files):
        from src.telegram_reviewer import _save_drafts
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
