import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.browser_helper import (
    sanitize_cookies,
    persist_browser_session,
    get_li_at_expiry_days,
    close_playwright_context,
)


def test_sanitize_cookies_preserves_expires_and_filters_partitioned():
    cookies = [
        {
            "name": "li_at",
            "value": "AQEDAT_valid_cookie",
            "domain": ".www.linkedin.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "None",
            "expires": 1999999999.0,
        },
        {
            "name": "__cf_bm",
            "value": "transient",
            "domain": ".linkedin.com",
            "path": "/",
            "sameSite": "InvalidValue",
        },
        {
            "name": "part",
            "value": "dropme",
            "partitionKey": "https://linkedin.com",
        },
    ]

    cleaned_keep = sanitize_cookies(cookies, drop_transient=False)
    assert len(cleaned_keep) == 2
    assert cleaned_keep[0]["expires"] == 1999999999.0
    assert cleaned_keep[1]["sameSite"] == "Lax"

    cleaned_drop = sanitize_cookies(cookies, drop_transient=True)
    assert len(cleaned_drop) == 1
    assert cleaned_drop[0]["name"] == "li_at"
    assert cleaned_drop[0]["expires"] == 1999999999.0


def test_persist_browser_session_never_overwrites_without_valid_li_at(tmp_path):
    state_file = tmp_path / "storage_state.json"
    clean_file = tmp_path / "storage_clean.json"
    state_file.write_text('{"cookies": [{"name": "li_at", "value": "existing_valid_cookie_123"}], "origins": []}', encoding="utf-8")
    clean_file.write_text('{"cookies": [{"name": "li_at", "value": "existing_valid_cookie_123"}], "origins": []}', encoding="utf-8")

    fake_ctx = MagicMock()
    fake_ctx.cookies.return_value = [{"name": "bcookie", "value": "v=2&abc"}]

    ok = persist_browser_session(fake_ctx, storage_state_file=state_file)
    assert ok is False
    assert "existing_valid_cookie_123" in clean_file.read_text(encoding="utf-8")


def test_persist_browser_session_saves_clean_and_state_with_expires(tmp_path):
    state_file = tmp_path / "storage_state.json"
    clean_file = tmp_path / "storage_clean.json"
    future_exp = time.time() + (90 * 86400)

    sample_cookies = [
        {
            "name": "li_at",
            "value": "AQEDAT_refreshed_cookie_value",
            "domain": ".www.linkedin.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "None",
            "expires": future_exp,
        },
        {
            "name": "__cf_bm",
            "value": "transient",
            "domain": ".linkedin.com",
            "path": "/",
            "sameSite": "None",
        },
    ]
    sample_origins = [{"origin": "https://www.linkedin.com", "localStorage": [{"name": "k", "value": "v"}]}]

    fake_ctx = MagicMock()
    fake_ctx.cookies.return_value = sample_cookies

    def _write_state(path):
        Path(path).write_text(
            json.dumps({"cookies": sample_cookies, "origins": sample_origins}),
            encoding="utf-8"
        )

    fake_ctx.storage_state.side_effect = _write_state

    ok = persist_browser_session(fake_ctx, storage_state_file=state_file)
    assert ok is True
    assert state_file.exists() and clean_file.exists()

    clean_data = json.loads(clean_file.read_text(encoding="utf-8"))
    assert len(clean_data["cookies"]) == 1
    assert clean_data["cookies"][0]["name"] == "li_at"
    assert clean_data["cookies"][0]["expires"] == future_exp
    assert clean_data["origins"] == sample_origins

    days_left = get_li_at_expiry_days(storage_state_file=state_file)
    assert days_left is not None
    assert 89.0 <= days_left <= 90.5


def test_close_playwright_context_closes_both_and_persists():
    fake_ctx = MagicMock()
    fake_browser = MagicMock()
    with patch("src.browser_helper.persist_browser_session") as mock_persist:
        close_playwright_context(fake_ctx, fake_browser, persist=True)
    mock_persist.assert_called_once_with(fake_ctx, storage_state_file=None)
    fake_ctx.close.assert_called_once()
    fake_browser.close.assert_called_once()


def test_session_keeper_uses_storage_state_and_persists(tmp_path):
    from scripts import session_keeper

    state_file = tmp_path / "storage_state.json"
    clean_file = tmp_path / "storage_clean.json"
    clean_file.write_text('{"cookies": [{"name": "li_at", "value": "AQEDAT_1234567890"}]}', encoding="utf-8")

    fake_page = MagicMock()
    fake_page.url = "https://www.linkedin.com/feed/"
    fake_ctx = MagicMock()
    fake_ctx.pages = [fake_page]
    fake_ctx.cookies.return_value = [{"name": "li_at", "value": "AQEDAT_1234567890", "expires": time.time() + 86400 * 30}]
    fake_browser = MagicMock()

    fake_playwright_cm = MagicMock()
    fake_playwright_cm.__enter__.return_value = MagicMock()

    with patch.object(session_keeper, "STORAGE_STATE_FILE", state_file), \
         patch.object(session_keeper, "BROWSER_PROFILE_DIR", tmp_path / "missing_profile"), \
         patch("playwright.sync_api.sync_playwright", return_value=fake_playwright_cm), \
         patch.object(session_keeper, "get_playwright_browser_context", return_value=(fake_ctx, fake_browser)) as mock_get, \
         patch.object(session_keeper, "persist_browser_session", return_value=True) as mock_persist, \
         patch.object(session_keeper, "get_li_at_expiry_days", return_value=30.0), \
         patch.object(session_keeper, "_notify") as mock_notify:
        ok = session_keeper.run_session_heartbeat(notify_on_ok=False)

    assert ok is True
    mock_get.assert_called_once()
    mock_persist.assert_called_once_with(fake_ctx, storage_state_file=state_file)
    mock_notify.assert_not_called()
    fake_ctx.close.assert_called_once()
    fake_browser.close.assert_called_once()
