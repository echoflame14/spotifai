import os
import secrets
import base64
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, session, flash
from urllib.parse import urlencode
import requests
from app import app, db
from models import User
from spotify_client import SpotifyClient

# Spotify OAuth configuration
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '3eab9e9e7ff444e8b0a9d1c18468b555')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI = os.environ.get('SPOTIFY_REDIRECT_URI', 'https://deb2334e-2767-4af0-932d-2c07564b350b-00-3cd1k0h3k7xtx.worf.replit.dev/callback')

@app.route('/')
def index():
    """Landing page - redirect to dashboard if authenticated, otherwise show login"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login')
def login():
    """Initiate Spotify OAuth flow"""
    # Generate random state for security
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    
    # Define required scopes
    scope = 'user-read-private user-read-email playlist-read-private user-read-playback-state user-modify-playback-state user-read-currently-playing'
    
    # Build authorization URL
    auth_params = {
        'response_type': 'code',
        'client_id': SPOTIFY_CLIENT_ID,
        'scope': scope,
        'redirect_uri': SPOTIFY_REDIRECT_URI,
        'state': state
    }
    
    auth_url = 'https://accounts.spotify.com/authorize?' + urlencode(auth_params)
    return redirect(auth_url)

@app.route('/callback')
def callback():
    """Handle Spotify OAuth callback"""
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    # Check for errors
    if error:
        flash(f'Authorization failed: {error}', 'error')
        return redirect(url_for('index'))
    
    # Verify state parameter
    if not state or state != session.get('oauth_state'):
        flash('Invalid state parameter. Please try again.', 'error')
        return redirect(url_for('index'))
    
    # Exchange code for access token
    token_url = 'https://accounts.spotify.com/api/token'
    
    # Prepare authorization header
    auth_string = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    auth_bytes = auth_string.encode('utf-8')
    auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
    
    headers = {
        'Authorization': f'Basic {auth_b64}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': SPOTIFY_REDIRECT_URI
    }
    
    try:
        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()
        token_data = response.json()
        
        access_token = token_data['access_token']
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 3600)
        
        # Get user profile
        spotify_client = SpotifyClient(access_token)
        user_profile = spotify_client.get_user_profile()
        
        if not user_profile:
            flash('Failed to get user profile from Spotify', 'error')
            return redirect(url_for('index'))
        
        # Calculate token expiration
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        # Save or update user in database
        user = User.query.get(user_profile['id'])
        if not user:
            user = User(id=user_profile['id'])
        
        user.display_name = user_profile.get('display_name', '')
        user.email = user_profile.get('email', '')
        user.image_url = user_profile['images'][0]['url'] if user_profile.get('images') and len(user_profile['images']) > 0 else None
        user.access_token = access_token
        user.refresh_token = refresh_token
        user.token_expires_at = expires_at
        user.last_login = datetime.utcnow()
        
        db.session.add(user)
        db.session.commit()
        
        # Store user ID in session
        session['user_id'] = user.id
        session.pop('oauth_state', None)
        
        flash('Successfully logged in!', 'success')
        return redirect(url_for('dashboard'))
        
    except requests.RequestException as e:
        app.logger.error(f"Token exchange failed: {e}")
        flash('Failed to authenticate with Spotify. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    """Main dashboard showing user's music"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.pop('user_id', None)
        flash('User not found. Please log in again.', 'error')
        return redirect(url_for('index'))
    
    # Check if token needs refresh
    if user.is_token_expired():
        # Try to refresh token
        if not refresh_user_token(user):
            flash('Session expired. Please log in again.', 'error')
            return redirect(url_for('logout'))
    
    spotify_client = SpotifyClient(user.access_token)
    
    # Get user's playlists
    playlists = spotify_client.get_user_playlists() or []
    
    # Get currently playing track
    current_track = spotify_client.get_current_track()
    
    # Get playback state
    playback_state = spotify_client.get_playback_state()
    
    return render_template('dashboard.html', 
                         user=user, 
                         playlists=playlists, 
                         current_track=current_track,
                         playback_state=playback_state)

@app.route('/play')
def play():
    """Resume playback"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('index'))
    
    spotify_client = SpotifyClient(user.access_token)
    success = spotify_client.play()
    
    if success:
        flash('Playback resumed', 'success')
    else:
        flash('Failed to resume playback. Make sure Spotify is open on a device.', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/pause')
def pause():
    """Pause playback"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('index'))
    
    spotify_client = SpotifyClient(user.access_token)
    success = spotify_client.pause()
    
    if success:
        flash('Playback paused', 'success')
    else:
        flash('Failed to pause playback', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    """Log out user"""
    session.pop('user_id', None)
    session.pop('oauth_state', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

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
        
        db.session.commit()
        return True
        
    except requests.RequestException as e:
        app.logger.error(f"Token refresh failed: {e}")
        return False

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', 
                         error_title='Page Not Found',
                         error_message='The page you are looking for does not exist.'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html',
                         error_title='Internal Server Error',
                         error_message='Something went wrong. Please try again later.'), 500
