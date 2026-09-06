import json, tomllib, httpx

with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)

class GigantumMCP:
    def __init__(self):
        self.url = secrets["GIGANTUM_MCP_URL"]; self.sid = None; self._n = 0
        self.h = {"Accept": "application/json, text/event-stream", "X-User-Email": secrets["GIGANTUM_EMAIL"]}
    def _rpc(self, method, params=None):
        self._n += 1
        payload = {"jsonrpc": "2.0", "id": self._n, "method": method}
        if params: payload["params"] = params
        h = dict(self.h); h["Content-Type"] = "application/json"
        if self.sid: h["Mcp-Session-Id"] = self.sid
        try:
            r = httpx.post(self.url, json=payload, headers=h, timeout=30)
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
            return {"error": str(e)}
    def connect(self):
        return self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "termux-agent", "version": "1.0"}})
    def tools(self):
        return self._rpc("tools/list")
    def ping(self):
        return self._rpc("ping")

print("=" * 60)
print("🔍 GIGANTUM MCP DIAGNOSTIC")
print("=" * 60)

g = GigantumMCP()
print(f"\n📡 Connecting to: {secrets['GIGANTUM_MCP_URL']}")
print(f"👤 User Email: {secrets['GIGANTUM_EMAIL']}")

# Test 1: Initialize
init_result = g.connect()
print(f"\n✅ Initialize: {'SUCCESS' if init_result and 'error' not in init_result else 'FAILED'}")
if init_result:
    print(f"   Session ID: {g.sid}")

# Test 2: Ping
ping_result = g.ping()
print(f"\n✅ Ping: {'SUCCESS' if ping_result and 'error' not in ping_result else 'FAILED'}")

# Test 3: List Tools
tools_result = g.tools()
print(f"\n✅ Tools List: {'SUCCESS' if tools_result and 'error' not in tools_result else 'FAILED'}")
if tools_result and "result" in tools_result:
    tools = tools_result["result"].get("tools", [])
    print(f"   Available Tools: {len(tools)}")
    if tools:
        print("\n   📋 Tool Names:")
        for tool in tools[:10]:  # Show first 10
            print(f"      - {tool.get('name', 'unknown')}: {tool.get('description', 'no description')[:50]}...")
        if len(tools) > 10:
            print(f"      ... and {len(tools) - 10} more")

print("\n" + "=" * 60)
