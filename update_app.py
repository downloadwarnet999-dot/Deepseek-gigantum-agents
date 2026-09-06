import tomllib

# Read current app.py
with open("app.py", "r") as f:
    app_code = f.read()

# Load secrets to get the token
with open(".streamlit/secrets.toml", "rb") as f:
    secrets_data = tomllib.load(f)

access_token = secrets_data.get("GIGANTUM_ACCESS_TOKEN")

if not access_token:
    print("❌ No access token found in secrets!")
    exit(1)

# Update the GigantumMCP class to use Bearer token
old_init = '''class GigantumMCP:
    def __init__(self):
        self.url = secrets["GIGANTUM_MCP_URL"]; self.sid = None; self._n = 0
        self.h = {"Accept": "application/json, text/event-stream", "X-User-Email": secrets["GIGANTUM_EMAIL"]}'''

new_init = f'''class GigantumMCP:
    def __init__(self):
        self.url = secrets["GIGANTUM_MCP_URL"]; self.sid = None; self._n = 0
        self.h = {{"Accept": "application/json, text/event-stream", "Authorization": "Bearer {access_token}"}}'''

app_code = app_code.replace(old_init, new_init)

# Write updated app
with open("app.py", "w") as f:
    f.write(app_code)

print(f"✅ App updated with OAuth token: {access_token[:30]}...")
print(f"   Restart Flask to apply changes!")
