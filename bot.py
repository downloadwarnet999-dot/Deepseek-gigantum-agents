import json, httpx, time
import token_manager
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

def deepseek(messages, tools=None):
    s = token_manager.load_secrets()
    headers = {"Authorization": f"Bearer {s['OPENROUTER_API_KEY']}", "Content-Type": "application/json"}
    payload = {"model": "deepseek/deepseek-chat", "messages": messages}
    if tools: payload["tools"] = tools
    for attempt in range(3):
        try:
            r = httpx.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=90)
            r.raise_for_status()
            data = r.json()
            if "choices" not in data or not data["choices"]:
                err = data.get("error") if isinstance(data, dict) else None
                msg = err.get("message", "OpenRouter busy - try again") if isinstance(err, dict) else "OpenRouter busy - try again"
                raise RuntimeError(msg)
            return data["choices"][0]["message"]
        except Exception:
            if attempt == 2: raise
            time.sleep(2 ** attempt)

class GigantumMCP:
    def __init__(self):
        s = token_manager.load_secrets()
        self.url = s["GIGANTUM_MCP_URL"]; self.sid = None; self._n = 0
    def _hdr(self):
        s = token_manager.load_secrets()
        return {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
                "Authorization": f"Bearer {s.get('GIGANTUM_ACCESS_TOKEN','')}"}
    def _rpc(self, method, params=None, retry=True):
        self._n += 1
        payload = {"jsonrpc": "2.0", "id": self._n, "method": method}
        if params: payload["params"] = params
        h = self._hdr()
        if self.sid: h["Mcp-Session-Id"] = self.sid
        try:
            r = httpx.post(self.url, json=payload, headers=h, timeout=30)
            if r.status_code == 401 and retry:
                if token_manager.refresh_token(): return self._rpc(method, params, retry=False)
                return None
            self.sid = r.headers.get("Mcp-Session-Id", self.sid)
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
    def connect(self):
        ok = self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "termux-bot", "version": "3.0"}})
        self._rpc("notifications/initialized")
        return ok is not None and "error" not in ok
    def tools(self):
        return (self._rpc("tools/list") or {}).get("result", {}).get("tools", [])
    def call(self, name, args):
        res = self._rpc("tools/call", {"name": name, "arguments": args}) or {}
        return "\n".join([c.get("text", "") for c in res.get("result", {}).get("content", []) if isinstance(c, dict)])

def save_memory(prompt, ai_text, tool):
    s = token_manager.load_secrets()
    try:
        httpx.post(s["SUPABASE_URL"] + "/rest/v1/stock_agent_memory",
            headers={"apikey": s["SUPABASE_ANON_KEY"], "Authorization": f"Bearer {s['SUPABASE_ANON_KEY']}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={"user_prompt": prompt, "ai_response": ai_text, "gigantum_tool_used": tool}, timeout=20)
    except Exception:
        pass

def run_agent(prompt):
    g = GigantumMCP(); tool_used = "None"
    try:
        if g.connect():
            gt = g.tools()
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
        return f"Error: {e}", "Error"
    return deepseek([{"role": "user", "content": prompt}])["content"], tool_used

async def start(update, context):
    st_ = token_manager.get_token_status()
    await context.bot.send_message(chat_id=update.effective_chat.id,
        text=f"📈 DeepSeek + Gigantum Bot Online\n🔑 Token: {st_['access_days_left']} days left\n🔥 Auto-refresh + vault sync active")

async def handle_message(update, context):
    token_manager.ensure_fresh_token()
    msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="⏳ Analyzing market data...")
    try:
        answer, tool = run_agent(update.message.text)
        if tool != "None": answer += f"\n\n🛠️ Tool used: {tool}"
        save_memory(update.message.text, answer, tool)
    except Exception as e:
        answer = f"Error: {e}"
    await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=msg.message_id, text=answer[:4000])

if __name__ == '__main__':
    s = token_manager.load_secrets()
    token_manager.start_background_refresh()
    app = ApplicationBuilder().token(s["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()
