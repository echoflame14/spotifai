"""
Spotify OAuth utilities and configuration.

This module handles all Spotify authentication-related functionality.
"""

import os
import secrets
import base64
import requests
from datetime import datetime, timedelta
from flask import request, session
from urllib.parse import urlencode
import logging

logger = logging.getLogger(__name__)

# Spotify OAuth configuration
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '3eab9e9e7ff444e8b0a9d1c18468b555')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')

def get_redirect_uri():
    """Get the appropriate redirect URI - use consistent URL for all devices"""
    # Force Railway URL for production
    railway_url = 'https://spotifai.up.railway.app/callback'
    
    # Use environment variable if explicitly set
    env_redirect_uri = os.environ.get('SPOTIFY_REDIRECT_URI')
    if env_redirect_uri:
        # Clean the environment variable in case it has extra characters
        env_redirect_uri = env_redirect_uri.strip().rstrip(';').rstrip()
        logger.info(f"Using environment SPOTIFY_REDIRECT_URI: '{env_redirect_uri}'")
        return env_redirect_uri
    
    # For Railway deployment, always use the Railway URL
    if request and request.host:
        if 'railway.app' in request.host:
            logger.info(f"Detected Railway deployment, using: '{railway_url}'")
            return railway_url
        else:
            # Dynamic detection for other platforms
            scheme = request.scheme
            host = request.host
            dynamic_uri = f"{scheme}://{host}/callback"
            logger.info(f"Using dynamic URI: '{dynamic_uri}'")
            return dynamic_uri
    
    # Default fallback for Railway
    logger.info(f"Using Railway fallback: '{railway_url}'")
    return railway_url

def generate_auth_url():
    """Generate Spotify authorization URL with proper parameters"""
    # Generate random state for security
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    
    # Define required scopes
    scope = 'user-read-private user-read-email playlist-read-private playlist-modify-public playlist-modify-private user-read-playback-state user-modify-playback-state user-read-currently-playing user-read-recently-played user-top-read user-library-read'
    
    # Get dynamic redirect URI
    redirect_uri = get_redirect_uri()
    
    # Build authorization URL
    auth_params = {
        'response_type': 'code',
        'client_id': SPOTIFY_CLIENT_ID,
        'scope': scope,
        'redirect_uri': redirect_uri,
        'state': state
    }
    
    auth_url = 'https://accounts.spotify.com/authorize?' + urlencode(auth_params)
    logger.info(f"Generated authorization URL for state: {state}")
    
    return auth_url, state

def exchange_code_for_token(code, state):
    """Exchange authorization code for access token"""
    # Verify state parameter
    session_state = session.get('oauth_state')
    if not state or state != session_state:
        logger.error(f"State mismatch - Received: '{state}', Expected: '{session_state}'")
        raise ValueError("Security check failed (invalid state)")
    
    # Prepare token exchange request
    token_url = 'https://accounts.spotify.com/api/token'
    
    if not SPOTIFY_CLIENT_SECRET:
        raise ValueError("SPOTIFY_CLIENT_SECRET is not set")
    
    auth_string = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    auth_bytes = auth_string.encode('utf-8')
    auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
    
    headers = {
        'Authorization': f'Basic {auth_b64}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    redirect_uri = get_redirect_uri().strip().rstrip(';').rstrip()
    
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri
    }
    
    logger.info("Sending token exchange request to Spotify...")
    response = requests.post(token_url, headers=headers, data=data, timeout=30)
    
    if response.status_code != 200:
        logger.error(f"Token exchange failed with status {response.status_code}")
        logger.error(f"Response content: {response.text}")
        raise requests.RequestException(f"Token exchange failed: {response.text}")
    
    token_data = response.json()
    logger.info("Successfully received token data from Spotify")
    
    access_token = token_data.get('access_token')
    refresh_token = token_data.get('refresh_token')
    expires_in = token_data.get('expires_in', 3600)
    
    if not access_token:
        raise ValueError("No access token in Spotify response")
    
    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'expires_in': expires_in,
        'expires_at': datetime.utcnow() + timedelta(seconds=expires_in)
    }

def refresh_user_token(user):
    """Refresh user's access token"""
    if not user.refresh_token:
        return False
    
    token_url = 'https://accounts.spotify.com/api/token'
    
    auth_string = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    auth_bytes = auth_string.encode('utf-8')
    auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
    
    headers = {
        'Authorization': f'Basic {auth_b64}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': user.refresh_token
    }
    
    try:
        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()
        token_data = response.json()
        
        user.access_token = token_data['access_token']
        if 'refresh_token' in token_data:
            user.refresh_token = token_data['refresh_token']
        
        expires_in = token_data.get('expires_in', 3600)
        user.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        from app import db
        db.session.commit()
        return True
        
    except requests.RequestException as e:
        logger.error(f"Token refresh failed: {e}")
        return False 