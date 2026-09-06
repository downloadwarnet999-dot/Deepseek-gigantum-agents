import httpx, json

print("=" * 60)
print("🔍 CHECKING OAUTH CONFIGURATION")
print("=" * 60)

# Check the OAuth metadata
metadata_url = "https://api.gigantum.id/.well-known/oauth-protected-resource"
print(f"\n📡 Fetching: {metadata_url}")

try:
    r = httpx.get(metadata_url, timeout=10)
    print(f"✅ Status: {r.status_code}")
    
    if r.status_code == 200:
        data = r.json()
        print("\n📋 OAuth Metadata:")
        print(json.dumps(data, indent=2))
        
        # Check if there's an authorization server
        if "authorization_servers" in data:
            print(f"\n🔑 Authorization Servers: {data['authorization_servers']}")
            
            # Try to fetch the auth server metadata
            for auth_server in data['authorization_servers']:
                print(f"\n📡 Fetching auth server: {auth_server}")
                try:
                    auth_r = httpx.get(auth_server + "/.well-known/oauth-authorization-server", timeout=10)
                    if auth_r.status_code == 200:
                        print("✅ Auth Server Metadata:")
                        print(json.dumps(auth_r.json(), indent=2))
                except Exception as e:
                    print(f"⚠️ Could not fetch: {e}")
    else:
        print(f"❌ Response: {r.text[:500]}")
except Exception as e:
    print(f"❌ ERROR: {type(e).__name__}: {str(e)}")

print("\n" + "=" * 60)
