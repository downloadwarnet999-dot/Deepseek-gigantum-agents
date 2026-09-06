from flask import Flask, request, session, jsonify, render_template_string, redirect
import json, tomllib, httpx
import token_manager

with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)

app = Flask(__name__)
app.secret_key = "supergodmode-local-key"

# Start background refresh daemon
token_manager.start_background_refresh()

HTML = """
<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1">
<title>DeepSeek+Gigantum</title>
<style>
body{font-family:sans-serif;background:#0d1117;color:#eee;margin:0;display:flex;flex-direction:column;height:100vh}
.status{padding:6px 12px;font-size:12px;background:#0d4420;color:#9be9a8;text-align:center}
#chat{flex:1;overflow-y:auto;padding:12px}
.msg{margin:6px 0;padding:10px;border-radius:10px;max-width:85%;white-space:pre-wrap}
.user{background:#1f6feb;margin-left:auto}
.ai{background:#21262d}
#bar{display:flex;padding:10px;gap:8px;background:#161b22}
#inp{flex:1;padding:12px;border-radius:8px;border:1px solid #30363d;background:#0d1117;color:#eee}
button{padding:12px 18px;border-radius:8px;border:0;background:#238636;color:#fff;font-weight:bold}
</style></head><body>
<div class=status>🔑 Token: {{days_left}} days left | 🕐 Last refresh: {{hours_since}}h ago | 🟢 Gigantum Connected</div>
<div id=chat></div>
<form id=bar onsubmit="send(event)"><input id=inp placeholder="Ask about stocks, screeners, market data..." autocomplete=off><button>Send</button></form>
<script>
const chat=document.getElementById('chat');
function add(cls,txt){const d=document.createElement('div');d.className='msg '+cls;d.innerText=txt;chat.appendChild(d);chat.scrollTop=chat.scrollHeight;return d;}
async function send(e){e.preventDefault();const m=document.getElementById('inp').value;if(!m)return;document.getElementById('inp').value='';add('user',m);
const t=add('ai','⏳ Thinking...');
try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:m})});
const j=await r.json();t.innerText=j.reply;}catch(err){t.innerText='❌ Error: '+err;}}
</script></body></html>
"""

LOGIN = """
<!doctype html><html><body style="background:#0d1117;color:#eee;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh">
<form method=post style="background:#161b22;padding:30px;border-radius:12px">
<h2>🔐 Secure Login</h2>
<input name=u placeholder=Username style="display:block;margin:8px 0;padding:10px"><br>
<input name=p type=password placeholder=Password style="display:block;margin:8px 0;padding:10px"><br>
<button style="width:100%;padding:10px;background:#238636;color:#fff;border:0;border-radius:8px">Login</button>
{% if err %}<p style="color:#f85149">{{err}}</p>{% endif %}
</form></body></html>
"""

# ---------- DEEPSEEK VIA OPENROUTER ----------
def deepseek(messages, tools=None):
    headers = {"Authorization": f"Bearer {secrets['OPENROUTER_API_KEY']}",
               "Content-Type": "application/json",
               "HTTP-Referer": "http://localhost:5000", "X-Title": "DeepSeek Gigantum Agent"}
    payload = {"model": "deepseek/deepseek-chat", "messages": messages}
    if tools: payload["tools"] = tools
    r = httpx.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=90)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]

# ---------- GIGANTUM MCP (Bearer Token + Auto-Refresh) ----------
class GigantumMCP:
    def __init__(self):
        self.url = secrets["GIGANTUM_MCP_URL"]; self.sid = None; self._n = 0
    def _hdr(self):
        # Always read fresh secrets (token may have been refreshed)
        fresh = token_manager.load_secrets()
        return {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {fresh.get('GIGANTUM_ACCESS_TOKEN', '')}"
        }
    def _rpc(self, method, params=None, retry=True):
        self._n += 1
        payload = {"jsonrpc": "2.0", "id": self._n, "method": method}
        if params: payload["params"] = params
        h = self._hdr()
        if self.sid: h["Mcp-Session-Id"] = self.sid
        try:
            r = httpx.post(self.url, json=payload, headers=h, timeout=30)
            # Auto-refresh on 401
            if r.status_code == 401 and retry:
                print("🔄 Token expired, refreshing...")
                if token_manager.refresh_token():
                    return self._rpc(method, params, retry=False)
                return None
            if r.status_code == 403:
                return {"error": "subscription_lapsed"}
            self.sid = r.headers.get("Mcp-Session-Id", self.sid)
            if "text/event-stream" in r.headers.get("content-type", ""):
                data = None
                for line in r.text.splitlines():
                    if line.startswith("data:"):
                        try: data = json.loads(line[5:].strip())
                        except Exception: pass
                return data
            return r.json() if r.status_code < 400 else None
        except Exception as e:
            print(f"⚠️ Gigantum RPC error: {e}")
            return None
    def connect(self):
        ok = self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "termux-agent", "version": "2.0"}})
        self._rpc("notifications/initialized")
        return ok is not None and "error" not in ok
    def tools(self):
        return (self._rpc("tools/list") or {}).get("result", {}).get("tools", [])
    def call(self, name, args):
        res = self._rpc("tools/call", {"name": name, "arguments": args}) or {}
        return "\n".join([c.get("text", "") for c in res.get("result", {}).get("content", []) if isinstance(c, dict)])

# ---------- SUPABASE MEMORY ----------
def save_memory(prompt, ai_text, tool):
    try:
        httpx.post(secrets["SUPABASE_URL"] + "/rest/v1/stock_agent_memory",
            headers={"apikey": secrets["SUPABASE_ANON_KEY"], "Authorization": f"Bearer {secrets['SUPABASE_ANON_KEY']}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={"user_prompt": prompt, "ai_response": ai_text, "gigantum_tool_used": tool}, timeout=20)
    except Exception:
        pass

# ---------- AGENTIC LOOP ----------
def run_agent(prompt):
    g = GigantumMCP(); tool_used = "None"
    try:
        if g.connect():
            gt = g.tools()
            if isinstance(gt, dict) and gt.get("error") == "subscription_lapsed":
                return "⚠️ Your Gigantum subscription may have lapsed. Renew at gigantum.id and re-run OAuth.", "Error"
            ot = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                   "parameters": t.get("inputSchema", {"type": "object", "properties": {}})}} for t in gt]
            if ot:
                msg = deepseek([{"role": "user", "content": prompt}], tools=ot)
                if msg.get("tool_calls"):
                    messages = [{"role": "user", "content": prompt}, msg]
                    for tc in msg["tool_calls"]:
                        tool_used = tc["function"]["name"]
                        args = json.loads(tc["function"]["arguments"] or "{}")
                        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": g.call(tool_used, args)})
                    return deepseek(messages)["content"], tool_used
                return msg["content"], tool_used
    except Exception as e:
        return f"Gigantum bridge notice: {e}", "Error"
    return deepseek([{"role": "user", "content": prompt}])["content"], tool_used

# ---------- ROUTES ----------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        a = secrets.get("auth", {})
        u, p = request.form.get("u"), request.form.get("p")
        if (u == a.get("account1_username") and p == a.get("account1_password")) or \
           (u == a.get("account2_username") and p == a.get("account2_password")):
            session["user"] = u
            return redirect("/")
        return render_template_string(LOGIN, err="Invalid credentials")
    if not session.get("user"):
        return render_template_string(LOGIN, err=None)
    # Proactive refresh check on every page load
    token_manager.ensure_fresh_token()
    status = token_manager.get_token_status()
    return render_template_string(HTML,
        days_left=status.get("access_days_left", "?"),
        hours_since=status.get("hours_since_refresh", "?"))

@app.route("/api/chat", methods=["POST"])
def chat():
    if not session.get("user"): return jsonify({"reply": "🔐 Login required"}), 401
    prompt = request.json.get("message", "")
    reply, tool = run_agent(prompt)
    save_memory(prompt, reply, tool)
    return jsonify({"reply": reply})

@app.route("/status")
def status():
    return jsonify(token_manager.get_token_status())

@app.route("/force-refresh")
def force_refresh():
    if token_manager.refresh_token():
        return jsonify({"status": "ok", "message": "Token refreshed!"})
    return jsonify({"status": "error", "message": "Refresh failed"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
