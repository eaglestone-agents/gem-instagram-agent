# -*- coding: utf-8 -*-
"""
GEM by Eaglestone — agent "Commentez BROCHURE -> DM automatique".

Webhook Meta (Instagram/Facebook) -> détecte un commentaire déclencheur sous un post GEM
-> répond en message privé (private reply) avec le lien de la brochure -> log le lead.

MVP volontairement simple : pas d'IA, pas de conversation. Un déclencheur, une réponse.

Langue : chaque post GEM (FR / NL / EN) est publié séparément, comme pour le carrousel
studios — la langue de la réponse se déduit donc de l'ID du post commenté (MEDIA_LANG_MAP),
pas d'une détection sur le texte du commentaire. Fallback FR si le post n'est pas mappé.

Limite connue (voir POUR-PAULINE.md) : l'API Send d'Instagram envoie un LIEN, pas le
fichier PDF en pièce jointe — à vérifier/adapter si Meta l'autorise pour ce compte.
"""
import os, hmac, hashlib, sqlite3, logging, threading, time
from contextlib import contextmanager
from flask import Flask, request, jsonify, abort
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gem-ig-agent")

# ---------------- CONFIG (variables d'environnement) ----------------
PAGE_TOKEN     = os.environ["PAGE_ACCESS_TOKEN"]                 # token de la page Eaglestone Belgique
APP_SECRET     = os.environ.get("APP_SECRET", "").strip()        # secret de l'app Meta (vérif signature)
VERIFY_TOKEN   = os.environ.get("WEBHOOK_VERIFY_TOKEN", "gem-verify-2026")
GRAPH          = "https://graph.facebook.com/v21.0"

BROCHURE_URL   = os.environ.get("BROCHURE_URL", "https://gembyeaglestone.be/brochure")
TRIGGER_WORDS  = [w.strip().lower() for w in os.environ.get("TRIGGER_WORDS", "brochure").split(",") if w.strip()]

# Quel post = quelle langue, ex. "17912345:FR,17912346:NL,17912347:EN" (voir POUR-PAULINE.md
# pour récupérer l'ID du post une fois publié). Fallback FR si le media_id n'est pas listé.
def _parse_media_lang_map(raw: str) -> dict:
    out = {}
    for pair in raw.split(","):
        if ":" in pair:
            media_id, lang = pair.split(":", 1)
            out[media_id.strip()] = lang.strip().upper()
    return out

MEDIA_LANG_MAP = _parse_media_lang_map(os.environ.get("MEDIA_LANG_MAP", ""))
# Le post organique GEM est publié en EN uniquement (un seul post, pas de triplication) —
# c'est donc le fallback par défaut. MEDIA_LANG_MAP sert aux 3 ad sets FR/NL/EN de la
# campagne payante en parallèle, chacun avec son propre post/langue.
DEFAULT_LANG   = os.environ.get("DEFAULT_LANG", "EN").upper()

TG_TOKEN       = os.environ.get("TELEGRAM_TOKEN", "").strip()    # optionnel : alerte Pauline/Sales
TG_CHAT        = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
TG_API         = f"https://api.telegram.org/bot{TG_TOKEN}"
TG_ENABLED     = bool(TG_TOKEN and TG_CHAT)

STATS_KEY      = os.environ.get("STATS_KEY", "").strip()         # clé du endpoint /leads ; vide = désactivé
DB_PATH        = os.environ.get("DB_PATH", "gem_ig.db")          # sur Render : /var/data/gem_ig.db (disque)

app = Flask(__name__)

MESSAGES = {
    "FR": "Merci pour votre message ! Voici la brochure GEM : " + BROCHURE_URL,
    "NL": "Bedankt voor je bericht! Hier is de GEM-brochure: " + BROCHURE_URL,
    "EN": "Thanks for reaching out! Here's the GEM brochure: " + BROCHURE_URL,
}

def message_for(media_id: str) -> str:
    lang = MEDIA_LANG_MAP.get(media_id, DEFAULT_LANG)
    return MESSAGES.get(lang, MESSAGES["FR"])

# ---------------- Base de données (SQLite) — log des déclenchements ----------------
_db_lock = threading.Lock()

@contextmanager
def db():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    try:
        yield c
        c.commit()
    finally:
        c.close()

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS triggers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comment_id TEXT UNIQUE,
            media_id TEXT,
            from_username TEXT,
            comment_text TEXT,
            sent_ok INTEGER,
            error TEXT,
            created_at INTEGER
        );
        """)

init_db()

# ---------------- Sécurité webhook (signature Meta) ----------------
def verify_signature(raw_body: bytes, signature_header: str) -> bool:
    if not APP_SECRET:
        return True  # pas de secret configuré (dev) — à activer en prod
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.split("sha256=", 1)[1])

# ---------------- Telegram (alerte optionnelle) ----------------
def notify_telegram(text: str):
    if not TG_ENABLED:
        return
    try:
        requests.post(f"{TG_API}/sendMessage", json={"chat_id": TG_CHAT, "text": text}, timeout=10)
    except Exception as e:
        log.warning("Notification Telegram échouée : %s", e)

# ---------------- Meta Graph API ----------------
def send_private_reply(comment_id: str, media_id: str) -> tuple[bool, str]:
    try:
        r = requests.post(
            f"{GRAPH}/{comment_id}/private_replies",
            params={"access_token": PAGE_TOKEN},
            json={"message": message_for(media_id)},
            timeout=15,
        )
        if r.status_code == 200:
            return True, ""
        return False, f"{r.status_code} {r.text[:300]}"
    except Exception as e:
        return False, str(e)

def is_trigger(text: str) -> bool:
    low = (text or "").lower()
    return any(w in low for w in TRIGGER_WORDS)

# ---------------- Webhook Meta ----------------
@app.get("/webhook")
def webhook_verify():
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == VERIFY_TOKEN):
        return request.args.get("hub.challenge", ""), 200
    abort(403)

@app.post("/webhook")
def webhook_receive():
    if not verify_signature(request.get_data(), request.headers.get("X-Hub-Signature-256", "")):
        log.warning("Signature webhook invalide — payload rejeté.")
        abort(403)

    payload = request.get_json(silent=True) or {}
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") not in ("comments", "feed"):
                continue
            value = change.get("value", {})
            comment_id = value.get("id")
            text = value.get("text", "")
            media_id = (value.get("media") or {}).get("id", "")
            username = (value.get("from") or {}).get("username", "") or (value.get("from") or {}).get("id", "")

            if not comment_id or not is_trigger(text):
                continue

            with db() as c:
                already = c.execute("SELECT 1 FROM triggers WHERE comment_id=?", (comment_id,)).fetchone()
            if already:
                continue  # déjà traité (Meta peut renvoyer le même événement plusieurs fois)

            ok, err = send_private_reply(comment_id, media_id)
            with db() as c:
                c.execute(
                    "INSERT OR IGNORE INTO triggers(comment_id, media_id, from_username, comment_text, sent_ok, error, created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (comment_id, media_id, username, text, int(ok), err, int(time.time())),
                )
            log.info("Trigger comment %s (@%s) -> envoi %s", comment_id, username, "OK" if ok else f"ECHEC ({err})")
            if ok:
                notify_telegram(f"GEM · brochure envoyée à @{username} (commentaire : “{text[:120]}”)")
            else:
                notify_telegram(f"GEM · ECHEC envoi brochure à @{username} — {err[:200]}")

    return jsonify(status="ok"), 200

# ---------------- Lecture des leads (reporting) ----------------
@app.get("/leads")
def leads():
    if not STATS_KEY or request.args.get("key") != STATS_KEY:
        abort(403)
    with db() as c:
        rows = c.execute(
            "SELECT comment_id, from_username, comment_text, sent_ok, error, created_at "
            "FROM triggers ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.get("/")
def health():
    return "GEM Instagram agent OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
