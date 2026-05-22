"""
Security alerter — Phase 7: the unauthorized-access notification module.

Polls the echostream_auth_events audit index on a short interval and raises a
Telegram alert when it detects an attack pattern. This is the "notification
module for unauthorized access attempts" required by the project spec.

Detection rules:
  1. Failed-login burst   — >= N login_fail from one IP within a window
  2. Account lockout      — any lockout event
  3. MFA-bypass attempt   — >= N mfa_fail for one user within a window
                            (password was correct, second factor keeps failing)
  4. IDOR attempt         — any idor_attempt event (cross-user resource access)
  5. New-IP login         — a successful login from an IP never seen before
                            for that user

Alerts are de-duplicated: each alert has a key, and the same key won't fire
again within ALERT_COOLDOWN seconds, so a sustained attack produces one alert
rather than one per poll.

Delivery: Telegram (reuses the same bot as push MFA). Set
ALERT_TELEGRAM_CHAT_ID in .env to the chat that should receive alerts.
"""
import os
import sys
import time
from datetime import datetime, timezone

# Windows' default cp1252 console can't encode the emoji in our alert text;
# force UTF-8 so prints never raise UnicodeEncodeError mid-alert.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.elasticsearch_client import ElasticsearchClient
from shared import telegram_push as tg

POLL_INTERVAL = int(os.getenv("ALERT_POLL_INTERVAL", "15"))
ALERT_COOLDOWN = int(os.getenv("ALERT_COOLDOWN", "600"))  # 10 min per unique alert
ALERT_CHAT_ID = os.getenv("ALERT_TELEGRAM_CHAT_ID", "").strip()

FAILED_BURST_THRESHOLD = int(os.getenv("ALERT_FAILED_BURST", "5"))
FAILED_BURST_WINDOW = "10m"
MFA_FAIL_THRESHOLD = int(os.getenv("ALERT_MFA_FAIL", "3"))
MFA_FAIL_WINDOW = "5m"
# Look-back for "single event" rules — must comfortably exceed POLL_INTERVAL so
# nothing slips between polls.
RECENT_WINDOW = "2m"

# alert_key -> unix timestamp last sent
_last_sent: dict[str, float] = {}


def _in_cooldown(key: str) -> bool:
    last = _last_sent.get(key, 0)
    return (time.time() - last) < ALERT_COOLDOWN


def _alert(es, key: str, text: str):
    # Dedup check WITHOUT marking yet — we only record the send after it
    # actually succeeds, so a transient failure doesn't suppress the alert.
    if _in_cooldown(key):
        return
    print(f"[Security Alerter] ALERT fired: {key}")  # ASCII-only, never the emoji text
    delivered = True
    if ALERT_CHAT_ID and tg.is_configured():
        try:
            tg.send_message(ALERT_CHAT_ID, text)
            # Telegram rate-limits ~1 msg/sec per chat. When multiple alerts
            # fire in one poll, space them out so later ones aren't dropped.
            time.sleep(1.2)
        except Exception as e:
            delivered = False
            print(f"[Security Alerter] telegram send failed: {e}")
    if delivered:
        _last_sent[key] = time.time()
        es.log_auth_event({"event_type": "alert_fired", "reason": key, "outcome": "ok"})


def _search(es, body):
    return es.client.search(index=es.auth_events_index, body=body)


def check_failed_bursts(es):
    body = {
        "size": 0,
        "query": {"bool": {"must": [
            {"term": {"event_type": "login_fail"}},
            {"range": {"timestamp": {"gte": f"now-{FAILED_BURST_WINDOW}"}}},
        ]}},
        "aggs": {"by_ip": {"terms": {"field": "ip", "size": 20, "min_doc_count": FAILED_BURST_THRESHOLD}}},
    }
    res = _search(es, body)
    for bucket in res["aggregations"]["by_ip"]["buckets"]:
        ip, count = bucket["key"], bucket["doc_count"]
        _alert(es, f"burst:{ip}",
               f"⚠️ EchoStream security alert\n\nFailed-login burst\nIP: {ip}\n"
               f"{count} failed attempts in the last {FAILED_BURST_WINDOW}.")


def check_mfa_bypass(es):
    body = {
        "size": 0,
        "query": {"bool": {"must": [
            {"term": {"event_type": "mfa_fail"}},
            {"range": {"timestamp": {"gte": f"now-{MFA_FAIL_WINDOW}"}}},
        ]}},
        "aggs": {"by_user": {"terms": {"field": "username", "size": 20, "min_doc_count": MFA_FAIL_THRESHOLD}}},
    }
    res = _search(es, body)
    for bucket in res["aggregations"]["by_user"]["buckets"]:
        user, count = bucket["key"], bucket["doc_count"]
        _alert(es, f"mfabypass:{user}",
               f"⚠️ EchoStream security alert\n\nPossible MFA-bypass attempt\nUser: {user}\n"
               f"Password was accepted but the second factor failed {count}× in {MFA_FAIL_WINDOW}.")


def check_recent_singletons(es):
    """Lockouts and IDOR attempts — alert on each occurrence (deduped by key)."""
    body = {
        "size": 50,
        "query": {"bool": {"must": [
            {"terms": {"event_type": ["lockout", "idor_attempt"]}},
            {"range": {"timestamp": {"gte": f"now-{RECENT_WINDOW}"}}},
        ]}},
        "sort": [{"timestamp": {"order": "desc"}}],
    }
    res = _search(es, body)
    for hit in res["hits"]["hits"]:
        e = hit["_source"]
        et = e.get("event_type")
        user = e.get("username", "?")
        ip = e.get("ip", "?")
        ts = e.get("timestamp", "")
        if et == "lockout":
            _alert(es, f"lockout:{user}:{ts}",
                   f"🔒 EchoStream security alert\n\nAccount locked\nUser: {user}\nIP: {ip}\n"
                   f"Triggered by repeated failed logins.")
        elif et == "idor_attempt":
            _alert(es, f"idor:{user}:{ts}",
                   f"🚨 EchoStream security alert\n\nUnauthorized resource access (IDOR)\n"
                   f"User: {user}\nIP: {ip}\n{e.get('reason','')}")


def check_new_ip_logins(es):
    """A successful login from an IP we've never seen for that user before."""
    body = {
        "size": 50,
        "query": {"bool": {"must": [
            {"term": {"event_type": "login_success"}},
            {"range": {"timestamp": {"gte": f"now-{RECENT_WINDOW}"}}},
        ]}},
        "sort": [{"timestamp": {"order": "desc"}}],
    }
    res = _search(es, body)
    for hit in res["hits"]["hits"]:
        e = hit["_source"]
        user, ip, ts = e.get("username"), e.get("ip"), e.get("timestamp", "")
        if not user or not ip:
            continue
        # Has this (user, ip) pair ever succeeded before this event?
        prior = _search(es, {
            "size": 0,
            "query": {"bool": {"must": [
                {"term": {"event_type": "login_success"}},
                {"term": {"username": user}},
                {"term": {"ip": ip}},
                {"range": {"timestamp": {"lt": ts}}},
            ]}},
        })
        if prior["hits"]["total"]["value"] == 0:
            _alert(es, f"newip:{user}:{ip}",
                   f"📍 EchoStream security alert\n\nLogin from a new IP\nUser: {user}\nIP: {ip}\n"
                   f"First successful login seen from this address.")


def main():
    if not ALERT_CHAT_ID:
        print("[Security Alerter] ALERT_TELEGRAM_CHAT_ID not set — alerts will only be logged, not sent.")
    es = ElasticsearchClient()
    es.connect()
    print(f"[Security Alerter] watching {es.auth_events_index} every {POLL_INTERVAL}s "
          f"(alerts -> {'telegram ' + ALERT_CHAT_ID if ALERT_CHAT_ID else 'log only'})")
    while True:
        try:
            check_failed_bursts(es)
            check_mfa_bypass(es)
            check_recent_singletons(es)
            check_new_ip_logins(es)
        except Exception as e:
            print(f"[Security Alerter] poll error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
