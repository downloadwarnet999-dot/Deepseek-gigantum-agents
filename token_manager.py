import json, base64, time, re, httpx, tomllib, threading
from pathlib import Path

SECRETS_PATH = Path.home() / "ai_supabase_hub" / ".streamlit" / "secrets.toml"
_refresh_lock = threading.Lock()

def decode_jwt(token):
    if not token: return {}
    try:
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}

def load_secrets():
    with open(SECRETS_PATH, "rb") as f:
        return tomllib.load(f)

def save_secrets(updates):
    """Update existing keys OR add missing keys at TOP level (above [auth])"""
    with open(SECRETS_PATH, "r") as f:
        content = f.read()
    for key, value in updates.items():
        pattern = rf'^{re.escape(key)} = ".*?"$'
        if re.search(pattern, content, flags=re.M):
            content = re.sub(pattern, f'{key} = "{value}"', content, flags=re.M)
        else:
            lines = content.splitlines(keepends=True)
            idx = next((i for i, l in enumerate(lines) if l.strip().startswith("[")), len(lines))
            lines.insert(idx, f'{key} = "{value}"\n')
            content = "".join(lines)
    with open(SECRETS_PATH, "w") as f:
        f.write(content)

def days_until_expiry(token):
    if not token: return -1
    payload = decode_jwt(token)
    exp = payload.get('exp', 0)
    return (exp - time.time()) / 86400

def should_refresh():
    secrets = load_secrets()
    access_token = secrets.get("GIGANTUM_ACCESS_TOKEN")
    last_refresh = secrets.get("GIGANTUM_LAST_REFRESH", "0")
    if not access_token: return True
    days_left = days_until_expiry(access_token)
    hours_since = (time.time() - float(last_refresh)) / 3600
    return days_left < 7 or hours_since > 12

def refresh_token():
    with _refresh_lock:
        secrets = load_secrets()
        if not secrets.get("GIGANTUM_REFRESH_TOKEN"):
            print("No refresh token in secrets")
            return False
        try:
            r = httpx.post("https://api.gigantum.id/mcp/oauth/token",
                data={"grant_type": "refresh_token",
                      "refresh_token": secrets["GIGANTUM_REFRESH_TOKEN"],
                      "client_id": secrets["GIGANTUM_CLIENT_ID"]},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15)
            if r.status_code == 200:
                d = r.json()
                updates = {
                    "GIGANTUM_ACCESS_TOKEN": d["access_token"],
                    "GIGANTUM_LAST_REFRESH": str(int(time.time()))
                }
                if d.get("refresh_token"):
                    updates["GIGANTUM_REFRESH_TOKEN"] = d["refresh_token"]
                save_secrets(updates)
                days_left = days_until_expiry(d["access_token"])
                print(f"Token refreshed! Valid for {days_left:.1f} more days")
                return True
            elif r.status_code == 401:
                print("Refresh token expired - need full OAuth re-auth")
                return False
            elif r.status_code == 403:
                print("Subscription may have lapsed - renew at gigantum.id")
                return False
            else:
                print(f"Refresh failed: {r.status_code}")
                return False
        except Exception as e:
            print(f"Refresh error: {e}")
            return False

def ensure_fresh_token():
    if should_refresh():
        return refresh_token()
    return True

def get_token_status():
    secrets = load_secrets()
    access = secrets.get("GIGANTUM_ACCESS_TOKEN")
    refresh = secrets.get("GIGANTUM_REFRESH_TOKEN")
    last = secrets.get("GIGANTUM_LAST_REFRESH", "0")
    if not access: return "NO TOKEN"
    days_left = days_until_expiry(access)
    hours_since = (time.time() - float(last)) / 3600
    return {
        "access_days_left": round(days_left, 1),
        "hours_since_refresh": round(hours_since, 1),
        "needs_refresh": should_refresh(),
        "has_refresh_token": bool(refresh)
    }

def background_refresh_loop():
    while True:
        try: ensure_fresh_token()
        except Exception as e: print(f"Background refresh error: {e}")
        time.sleep(6 * 3600)

def start_background_refresh():
    t = threading.Thread(target=background_refresh_loop, daemon=True)
    t.start()
    print("Background token refresh daemon started (checks every 6h)")
