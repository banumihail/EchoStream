"""
Telegram poller — Phase 5 push MFA.

Long-polls Telegram getUpdates and handles two kinds of events:

  /start <pairing_token>  → links the sender's chat_id to the EchoStream user
                            who generated that token (completes enrollment).
  callback_query a|d:user:reqid → records an Approve/Deny decision against the
                            user's pending push request.

Runs as its own process alongside the ML workers. All traffic is outbound to
Telegram, so this works on localhost without any inbound exposure.
"""
import os
import sys
import time
from datetime import datetime, timezone

# Load .env before importing telegram_push (which reads TELEGRAM_BOT_TOKEN at
# import time). The poller runs standalone, so it can't rely on the API's load.
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.elasticsearch_client import ElasticsearchClient
from shared import telegram_push as tg


def _now():
    return datetime.now(timezone.utc)


def handle_start(es, chat_id, pairing_token):
    user = es.find_user_by("telegram_pairing_token", pairing_token)
    if not user:
        tg.send_message(chat_id, "This pairing link is invalid or expired. Generate a new one in EchoStream → Security.")
        return
    username = user["username"]
    methods = list(user.get("mfa_methods") or [])
    if "push" not in methods:
        methods.append("push")
    es.update_user(username, {
        "telegram_chat_id": str(chat_id),
        "telegram_pairing_token": None,
        "mfa_methods": methods,
    })
    es.log_auth_event({"username": username, "event_type": "mfa_enrolled",
                       "mfa_method": "push", "outcome": "ok"})
    tg.send_message(chat_id, f"Linked to EchoStream account '{username}'. You'll get an Approve/Deny prompt here when you sign in.")
    print(f"[Telegram Poller] paired chat {chat_id} -> {username}")


def handle_callback(es, cq):
    data = cq.get("data", "")
    chat_id = cq["message"]["chat"]["id"]
    message_id = cq["message"]["message_id"]
    cq_id = cq["id"]
    try:
        decision, username, request_id = data.split(":", 2)
    except ValueError:
        tg.answer_callback(cq_id, "Malformed request.")
        return
    user = es.get_user(username)
    pending = (user or {}).get("pending_push") or {}
    if not user or pending.get("request_id") != request_id:
        tg.answer_callback(cq_id, "This request is no longer active.")
        tg.edit_message_text(chat_id, message_id, "This sign-in request has expired.")
        return
    # Check expiry
    try:
        expires = datetime.fromisoformat(pending["expires"])
        if _now() > expires:
            tg.answer_callback(cq_id, "Request expired.")
            tg.edit_message_text(chat_id, message_id, "This sign-in request expired.")
            es.update_user(username, {"pending_push": {**pending, "status": "expired"}})
            return
    except (KeyError, ValueError):
        pass

    new_status = "approved" if decision == "a" else "denied"
    es.update_user(username, {"pending_push": {**pending, "status": new_status}})
    es.log_auth_event({"username": username, "event_type": "push_decision",
                       "mfa_method": "push", "outcome": new_status})
    tg.answer_callback(cq_id, f"Sign-in {new_status}.")
    verb = "approved ✅" if new_status == "approved" else "denied 🚫"
    tg.edit_message_text(chat_id, message_id, f"Sign-in request {verb}.")
    print(f"[Telegram Poller] {username} -> {new_status}")


def main():
    if not tg.is_configured():
        print("[Telegram Poller] TELEGRAM_BOT_TOKEN not set — poller idle. Set it in .env and restart.")
        # Stay alive but idle so process management is uniform.
        while True:
            time.sleep(60)

    es = ElasticsearchClient()
    es.connect()
    me = tg.get_me()
    print(f"[Telegram Poller] bot @{me.get('username')} online, polling...")

    offset = None
    while True:
        try:
            updates = tg.get_updates(offset=offset, timeout=25)
        except Exception as e:
            print(f"[Telegram Poller] getUpdates error: {e}; retrying in 5s")
            time.sleep(5)
            continue
        for upd in updates:
            offset = upd["update_id"] + 1
            try:
                if "message" in upd:
                    msg = upd["message"]
                    text = (msg.get("text") or "").strip()
                    chat_id = msg["chat"]["id"]
                    if text.startswith("/start"):
                        parts = text.split(maxsplit=1)
                        if len(parts) == 2:
                            handle_start(es, chat_id, parts[1].strip())
                        else:
                            tg.send_message(chat_id, "Open the pairing link from EchoStream → Security to connect your account.")
                elif "callback_query" in upd:
                    handle_callback(es, upd["callback_query"])
            except Exception as e:
                print(f"[Telegram Poller] error handling update {upd.get('update_id')}: {e}")


if __name__ == "__main__":
    main()
