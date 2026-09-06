import json, tomllib, httpx

with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)

print("=" * 60)
print("🔍 DETAILED GIGANTUM MCP DIAGNOSTIC")
print("=" * 60)

url = secrets["GIGANTUM_MCP_URL"]
email = secrets["GIGANTUM_EMAIL"]

print(f"\n📡 URL: {url}")
print(f"👤 Email: {email}")

# Test 1: Basic connectivity
print("\n" + "=" * 60)
print("TEST 1: Basic HTTP GET")
print("=" * 60)
try:
    r = httpx.get(url, timeout=10)
    print(f"✅ Status Code: {r.status_code}")
    print(f"✅ Response Headers: {dict(r.headers)}")
    print(f"✅ Response Body (first 200 chars): {r.text[:200]}")
except Exception as e:
    print(f"❌ ERROR: {type(e).__name__}: {str(e)}")

# Test 2: POST with JSON-RPC initialize
print("\n" + "=" * 60)
print("TEST 2: JSON-RPC Initialize (POST)")
print("=" * 60)
try:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "termux-agent", "version": "1.0"}
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "X-User-Email": email
    }
    r = httpx.post(url, json=payload, headers=headers, timeout=10)
    print(f"✅ Status Code: {r.status_code}")
    print(f"✅ Response Headers: {dict(r.headers)}")
    print(f"✅ Response Body: {r.text[:500]}")
    
    if r.status_code == 200:
        try:
            data = r.json()
            print(f"\n✅ Parsed JSON: {json.dumps(data, indent=2)[:500]}")
        except:
            print(f"\n⚠️ Could not parse as JSON (might be SSE stream)")
except Exception as e:
    print(f"❌ ERROR: {type(e).__name__}: {str(e)}")

# Test 3: Try with Bearer token
print("\n" + "=" * 60)
print("TEST 3: With Authorization Header")
print("=" * 60)
try:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "termux-agent", "version": "1.0"}
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "X-User-Email": email,
        "Authorization": f"Bearer {email}"  # Try email as token
    }
    r = httpx.post(url, json=payload, headers=headers, timeout=10)
    print(f"✅ Status Code: {r.status_code}")
    print(f"✅ Response Body: {r.text[:500]}")
except Exception as e:
    print(f"❌ ERROR: {type(e).__name__}: {str(e)}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
