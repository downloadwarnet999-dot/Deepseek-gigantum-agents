import httpx
import json
import tomllib
import hashlib
import secrets
import base64
import webbrowser
from urllib.parse import urlencode, parse_qs
import time

# Load existing secrets
with open(".streamlit/secrets.toml", "rb") as f:
    secrets_data = tomllib.load(f)

GIGANTUM_URL = secrets_data["GIGANTUM_MCP_URL"]
GIGANTUM_EMAIL = secrets_data["GIGANTUM_EMAIL"]

print("=" * 60)
print("🔐 GIGANTUM OAUTH AUTHENTICATION")
print("=" * 60)
print(f"\n📡 MCP URL: {GIGANTUM_URL}")
print(f"👤 Email: {GIGANTUM_EMAIL}")

# Step 1: Register client
print("\n" + "=" * 60)
print("STEP 1: Registering OAuth Client")
print("=" * 60)

registration_data = {
    "client_name": "Termux DeepSeek Agent",
    "redirect_uris": ["http://127.0.0.1:8080/callback"],
    "grant_types": ["authorization_code"],
    "response_types": ["code"],
    "token_endpoint_auth_method": "none",
    "scope": "mcp:tools"
}

try:
    r = httpx.post(
        "https://api.gigantum.id/mcp/oauth/register",
        json=registration_data,
        headers={"Content-Type": "application/json"},
        timeout=10
    )
    
    if r.status_code == 201:
        client_data = r.json()
        client_id = client_data["client_id"]
        print(f"✅ Client registered successfully!")
        print(f"   Client ID: {client_id}")
    else:
        print(f"❌ Registration failed: {r.status_code}")
        print(f"   Response: {r.text}")
        exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)

# Step 2: Generate PKCE challenge
print("\n" + "=" * 60)
print("STEP 2: Generating PKCE Challenge")
print("=" * 60)

code_verifier = secrets.token_urlsafe(32)
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).rstrip(b'=').decode()

print(f"✅ PKCE generated")
print(f"   Verifier length: {len(code_verifier)}")
print(f"   Challenge length: {len(code_challenge)}")

# Step 3: Build authorization URL
print("\n" + "=" * 60)
print("STEP 3: Building Authorization URL")
print("=" * 60)

state = secrets.token_urlsafe(16)
auth_params = {
    "response_type": "code",
    "client_id": client_id,
    "redirect_uri": "http://127.0.0.1:8080/callback",
    "scope": "mcp:tools",
    "state": state,
    "code_challenge": code_challenge,
    "code_challenge_method": "S256"
}

auth_url = f"https://api.gigantum.id/mcp/oauth/authorize?{urlencode(auth_params)}"

print(f"\n🔗 Authorization URL:")
print(auth_url)
print(f"\n⚠️  IMPORTANT: Copy this URL and open it in your browser!")
print(f"   Login with your Gigantum account: {GIGANTUM_EMAIL}")
print(f"   After login, you'll be redirected to a URL that looks like:")
print(f"   http://127.0.0.1:8080/callback?code=XXXXX&state=XXXXX")
print(f"\n   Copy the FULL redirect URL and paste it below.")

input_url = input("\n📋 Paste the full redirect URL here: ").strip()

# Step 4: Extract authorization code
print("\n" + "=" * 60)
print("STEP 4: Extracting Authorization Code")
print("=" * 60)

try:
    parsed = parse_qs(input_url.split('?')[1])
    auth_code = parsed['code'][0]
    returned_state = parsed['state'][0]
    
    if returned_state != state:
        print("❌ State mismatch! Possible security issue.")
        exit(1)
    
    print(f"✅ Authorization code extracted: {auth_code[:20]}...")
except Exception as e:
    print(f"❌ Failed to parse URL: {e}")
    exit(1)

# Step 5: Exchange code for token
print("\n" + "=" * 60)
print("STEP 5: Exchanging Code for Access Token")
print("=" * 60)

token_data = {
    "grant_type": "authorization_code",
    "code": auth_code,
    "redirect_uri": "http://127.0.0.1:8080/callback",
    "client_id": client_id,
    "code_verifier": code_verifier
}

try:
    r = httpx.post(
        "https://api.gigantum.id/mcp/oauth/token",
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10
    )
    
    if r.status_code == 200:
        token_response = r.json()
        access_token = token_response["access_token"]
        expires_in = token_response.get("expires_in", 3600)
        refresh_token = token_response.get("refresh_token")
        
        print(f"✅ Access token obtained!")
        print(f"   Token: {access_token[:30]}...")
        print(f"   Expires in: {expires_in} seconds")
        
        # Step 6: Update secrets.toml
        print("\n" + "=" * 60)
        print("STEP 6: Updating secrets.toml")
        print("=" * 60)
        
        secrets_data["GIGANTUM_ACCESS_TOKEN"] = access_token
        secrets_data["GIGANTUM_CLIENT_ID"] = client_id
        secrets_data["GIGANTUM_CODE_VERIFIER"] = code_verifier
        if refresh_token:
            secrets_data["GIGANTUM_REFRESH_TOKEN"] = refresh_token
        
        # Write back to secrets.toml
        with open(".streamlit/secrets.toml", "w", encoding="utf-8") as f:
            for key, value in secrets_data.items():
                if key == "auth":
                    f.write("\n[auth]\n")
                    for auth_key, auth_value in value.items():
                        f.write(f'{auth_key} = "{auth_value}"\n')
                else:
                    f.write(f'{key} = "{value}"\n')
        
        print(f"✅ Secrets updated with OAuth token!")
        print(f"\n🎉 GIGANTUM AUTHENTICATION COMPLETE!")
        print(f"   Your app can now connect to Gigantum MCP!")
        
    else:
        print(f"❌ Token exchange failed: {r.status_code}")
        print(f"   Response: {r.text}")
        exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)

print("\n" + "=" * 60)
