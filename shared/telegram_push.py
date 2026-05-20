"""
Telegram Bot API wrapper — Phase 5 push-notification MFA.

Why Telegram for localhost: the bot talks to Telegram's servers *outbound*
(sendMessage, getUpdates long-poll), so approve/deny works without exposing
the API to the internet. A user taps a button in Telegram; Telegram hands the
callback to our poller via getUpdates. No tunnel, no inbound webhook.

Set TELEGRAM_BOT_TOKEN in .env (from @BotFather). All helpers are no-ops that
raise RuntimeError if the token is missing, so the rest of the app degrades
gracefully when push isn't configured.
"""
import os
import requests

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
_TIMEOUT = 15


def is_configured() -> bool:
    return bool(BOT_TOKEN)


def _require():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")


def get_me() -> dict:
    """Return the bot's own profile — used to build the t.me/<username> deep link."""
    _require()
    r = requests.get(f"{_API}/getMe", timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()["result"]


def send_approval_request(chat_id: str, text: str, request_id: str, username: str) -> dict:
    """Send a message with inline Approve / Deny buttons. callback_data encodes
    decision:username:request_id so the poller can route the tap without a
    lookup (kept under Telegram's 64-byte limit)."""
    _require()
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": f"a:{username}:{request_id}"},
            {"text": "🚫 Deny", "callback_data": f"d:{username}:{request_id}"},
        ]]
    }
    r = requests.post(f"{_API}/sendMessage", timeout=_TIMEOUT, json={
        "chat_id": chat_id,
        "text": text,
        "reply_markup": keyboard,
    })
    r.raise_for_status()
    return r.json()["result"]


def send_message(chat_id: str, text: str) -> dict:
    _require()
    r = requests.post(f"{_API}/sendMessage", timeout=_TIMEOUT, json={"chat_id": chat_id, "text": text})
    r.raise_for_status()
    return r.json()["result"]


def get_updates(offset: int | None = None, timeout: int = 25) -> list[dict]:
    """Long-poll for new updates. Returns the raw update list."""
    _require()
    params = {"timeout": timeout, "allowed_updates": '["message","callback_query"]'}
    if offset is not None:
        params["offset"] = offset
    r = requests.get(f"{_API}/getUpdates", params=params, timeout=timeout + 10)
    r.raise_for_status()
    return r.json().get("result", [])


def answer_callback(callback_query_id: str, text: str) -> None:
    """Acknowledge a button tap so Telegram stops showing the loading spinner."""
    _require()
    requests.post(f"{_API}/answerCallbackQuery", timeout=_TIMEOUT,
                  json={"callback_query_id": callback_query_id, "text": text})


def edit_message_text(chat_id: str, message_id: int, text: str) -> None:
    """Replace the message text (and drop the buttons) after a decision."""
    _require()
    requests.post(f"{_API}/editMessageText", timeout=_TIMEOUT,
                  json={"chat_id": chat_id, "message_id": message_id, "text": text})
