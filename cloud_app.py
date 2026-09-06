import streamlit as st
import json, httpx

S = st.secrets
st.set_page_config(page_title="DeepSeek + Gigantum Cloud", layout="wide")

# ---------- AUTH GATE (both users) ----------
if "authenticated" not in st.session_state: st.session_state.authenticated = False
if not st.session_state.authenticated:
    st.title("🔐 Secure Login")
    with st.form("login"):
        u = st.text_input("Username"); p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            a = S["auth"]
            if (u == a["account1_username"] and p == a["account1_password"]) or (u == a["account2_username"] and p == a["account2_password"]):
                st.session_state.authenticated = True; st.rerun()
            else: st.error("Invalid credentials")
    st.stop()

st.title("📈 DeepSeek + Gigantum Cloud Agent")
if st.button("Logout"):
    st.session_state.authenticated = False; st.rerun()

# ---------- LIVE TOKEN FROM SUPABASE VAULT (auto-fresh) ----------
@st.cache_data(ttl=300)
def get_vault_token():
    try:
        r = httpx.get(S["SUPABASE_URL"] + "/rest/v1/token_vault?id=eq.1&select=gigantum_access_token",
                      headers={"apikey": S["SUPABASE_ANON_KEY"],
                               "Authorization": f"Bearer {S['SUPABASE_ANON_KEY']}"},
                      timeout=10)
        rows = r.json()
        if rows and rows[0].get("gigantum_access_token"):
            return rows[0]["gigantum_access_token"]
    except Exception:
        pass
    return S.get("GIGANTUM_ACCESS_TOKEN", "")

def deepseek(messages, tools=None):
    headers = {"Authorization": f"Bearer {S['OPENROUTER_API_KEY']}", "Content-Type": "application/json"}
    payload = {"model": "deepseek/deepseek-chat", "messages": messages}
    if tools: payload["tools"] = tools
    r = httpx.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=90)
    r.raise_for_status()
    data = r.json()
    if "choices" not in data or not data["choices"]:
        err = data.get("error") if isinstance(data, dict) else None
        msg = err.get("message", "OpenRouter busy - try again") if isinstance(err, dict) else "OpenRouter busy - try again"
        raise RuntimeError(msg)
    return data["choices"][0]["message"]

def g_rpc(method, params=None):
    h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
         "Authorization": f"Bearer {get_vault_token()}"}
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params: payload["params"] = params
    try:
        r = httpx.post(S["GIGANTUM_MCP_URL"], json=payload, headers=h, timeout=30)
        if "text/event-stream" in r.headers.get("content-type", ""):
            data = None
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    try: data = json.loads(line[5:].strip())
                    except Exception: pass
            return data
        return r.json() if r.status_code < 400 else None
    except Exception:
        return None

def run_agent(prompt):
    tool_used = "None"
    init = g_rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "cloud", "version": "2.0"}})
    if init:
        tools = (g_rpc("tools/list") or {}).get("result", {}).get("tools", [])
        ot = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("inputSchema", {"type": "object", "properties": {}})}} for t in tools]
        if ot:
            msg = deepseek([{"role": "user", "content": prompt}], tools=ot)
            if msg.get("tool_calls"):
                messages = [{"role": "user", "content": prompt}, msg]
                for tc in msg["tool_calls"]:
                    tool_used = tc["function"]["name"]
                    res = g_rpc("tools/call", {"name": tool_used, "arguments": json.loads(tc["function"]["arguments"] or "{}")}) or {}
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": "\n".join([c.get("text", "") for c in res.get("result", {}).get("content", []) if isinstance(c, dict)])})
                return deepseek(messages)["content"], tool_used
            return msg["content"], tool_used
    return deepseek([{"role": "user", "content": prompt}])["content"], tool_used

def save_memory(prompt, ai_text, tool):
    try:
        httpx.post(S["SUPABASE_URL"] + "/rest/v1/stock_agent_memory",
            headers={"apikey": S["SUPABASE_ANON_KEY"], "Authorization": f"Bearer {S['SUPABASE_ANON_KEY']}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={"user_prompt": prompt, "ai_response": ai_text, "gigantum_tool_used": tool}, timeout=20)
    except Exception:
        pass

# ---------- CHAT UI ----------
if "messages" not in st.session_state: st.session_state.messages = []
for m in st.session_state.messages:
    with st.chat_message(m["role"]): st.markdown(m["content"])
if prompt := st.chat_input("Ask about stocks, screeners, market data..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Consulting Gigantum + DeepSeek..."):
            ai_text, tool = run_agent(prompt)
            st.markdown(ai_text)
            save_memory(prompt, ai_text, tool)
    st.session_state.messages.append({"role": "assistant", "content": ai_text})
