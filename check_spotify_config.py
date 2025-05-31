#!/usr/bin/env python3
"""
Spotify OAuth Configuration Checker
This script helps verify your Spotify app configuration and tests the OAuth flow.
"""

import os
import requests
import base64
from urllib.parse import urlencode

def check_spotify_config():
    """Check Spotify application configuration"""
    
    print("🔍 Spotify OAuth Configuration Checker")
    print("=" * 50)
    
    # Check environment variables
    client_id = os.environ.get('SPOTIFY_CLIENT_ID', '3eab9e9e7ff444e8b0a9d1c18468b555')
    client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
    
    print(f"✅ Client ID: {client_id}")
    print(f"{'✅' if client_secret else '❌'} Client Secret: {'Present' if client_secret else 'Missing'}")
    
    if not client_secret:
        print("❌ SPOTIFY_CLIENT_SECRET environment variable is not set!")
        return False
    
    # Test redirect URIs
    redirect_uris = [
        'https://spotifai.up.railway.app/callback',
        'http://localhost:5000/callback',
        'http://127.0.0.1:5000/callback'
    ]
    
    print("\n🔗 Expected Redirect URIs in Spotify Dashboard:")
    for uri in redirect_uris:
        print(f"   - {uri}")
    
    # Test authorization URL generation
    print("\n🧪 Testing Authorization URL Generation:")
    state = "test_state_123"
    scope = 'user-read-private user-read-email playlist-read-private playlist-modify-public playlist-modify-private user-read-playback-state user-modify-playback-state user-read-currently-playing user-read-recently-played user-top-read user-library-read'
    
    for redirect_uri in redirect_uris:
        auth_params = {
            'response_type': 'code',
            'client_id': client_id,
            'scope': scope,
            'redirect_uri': redirect_uri,
            'state': state
        }
        auth_url = 'https://accounts.spotify.com/authorize?' + urlencode(auth_params)
        print(f"\n📍 {redirect_uri}:")
        print(f"   {auth_url}")
    
    # Test basic client credentials
    print("\n🔐 Testing Client Credentials:")
    auth_string = f"{client_id}:{client_secret}"
    auth_bytes = auth_string.encode('utf-8')
    auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
    
    headers = {
        'Authorization': f'Basic {auth_b64}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    # Test client credentials grant (doesn't require user authorization)
    token_url = 'https://accounts.spotify.com/api/token'
    data = {
        'grant_type': 'client_credentials'
    }
    
    try:
        response = requests.post(token_url, headers=headers, data=data, timeout=10)
        if response.status_code == 200:
            print("✅ Client credentials are valid")
            token_data = response.json()
            print(f"   Access token received (length: {len(token_data.get('access_token', ''))})")
        else:
            print(f"❌ Client credentials test failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Client credentials test error: {e}")
        return False
    
    print("\n📋 Next Steps:")
    print("1. Verify your Spotify Developer Dashboard settings:")
    print("   https://developer.spotify.com/dashboard")
    print("2. Ensure these redirect URIs are registered EXACTLY:")
    for uri in redirect_uris:
        print(f"   - {uri}")
    print("3. Test the OAuth flow using: https://spotifai.up.railway.app/debug-oauth")
    print("4. Check callback accessibility: https://spotifai.up.railway.app/test-callback")
    
    return True

if __name__ == "__main__":
    check_spotify_config() 