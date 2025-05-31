"""
Authentication routes for Spotify OAuth.

This module handles all authentication-related routes including login,
callback, and logout functionality.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
from app import app, db
from models import User
from spotify_client import SpotifyClient
from utils.spotify_auth import generate_auth_url, exchange_code_for_token, refresh_user_token
import logging

logger = logging.getLogger(__name__)

# Create authentication blueprint
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    """Landing page - redirect to dashboard if authenticated, otherwise show login"""
    if 'user_id' in session:
        return redirect(url_for('dashboard.dashboard'))
    return render_template('login.html')

@auth_bp.route('/login')
def login():
    """Initiate Spotify OAuth flow"""
    try:
        # Generate authorization URL and state
        auth_url, state = generate_auth_url()
        
        # Session debugging
        logger.info(f"=== LOGIN SESSION DEBUG ===")
        logger.info(f"Generated state: {state}")
        logger.info(f"Session ID: {session.get('session_id', 'no session_id')}")
        logger.info(f"Session before OAuth: {dict(session)}")
        logger.info(f"Session permanent: {session.permanent}")
        logger.info(f"Cookie settings - Secure: {app.config.get('SESSION_COOKIE_SECURE')}")
        logger.info(f"Cookie settings - SameSite: {app.config.get('SESSION_COOKIE_SAMESITE')}")
        logger.info(f"Cookie settings - Domain: {app.config.get('SESSION_COOKIE_DOMAIN')}")
        logger.info("============================")
        
        # Debug: Log the parameters being used
        logger.info(f"=== OAUTH DEBUG INFO ===")
        logger.info(f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}")
        logger.info(f"Request Host: {request.host}")
        logger.info(f"Request URL: {request.url}")
        logger.info(f"State: {state}")
        logger.info(f"Full Authorization URL: {auth_url}")
        logger.info(f"========================")
        
        return redirect(auth_url)
        
    except Exception as e:
        logger.error(f"Login initialization failed: {str(e)}")
        flash('Failed to initialize login process. Please try again.', 'error')
        return redirect(url_for('auth.index'))

@auth_bp.route('/callback')
def callback():
    """Handle Spotify OAuth callback"""
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        error_description = request.args.get('error_description')
        
        logger.info(f"=== CALLBACK DEBUG INFO ===")
        logger.info(f"Callback URL accessed: {request.url}")
        logger.info(f"Received code: {'Yes' if code else 'No'}")
        logger.info(f"Code length: {len(code) if code else 0}")
        logger.info(f"Received state: {state}")
        logger.info(f"Received error: {error}")
        logger.info(f"Error description: {error_description}")
        
        # Enhanced session debugging
        logger.info(f"=== SESSION STATE DEBUG ===")
        logger.info(f"Session state: {session.get('oauth_state')}")
        logger.info(f"Full session contents: {dict(session)}")
        logger.info(f"Session permanent: {session.permanent}")
        logger.info(f"Session modified: {session.modified}")
        logger.info(f"Request cookies: {request.cookies}")
        logger.info("============================")
        
        # Check for errors from Spotify
        if error:
            error_msg = f"Spotify authorization error: {error}"
            if error_description:
                error_msg += f" - {error_description}"
            
            logger.error(error_msg)
            
            # Provide specific error messages for common issues
            if error == 'access_denied':
                flash('You denied access to Spotify. Please try again and grant permissions.', 'error')
            elif error == 'invalid_client':
                flash('Invalid client configuration. Please contact support.', 'error')
            elif error == 'invalid_request':
                flash('Invalid authorization request. Please try again.', 'error')
            else:
                flash(f'Authorization failed: {error_msg}', 'error')
            
            return redirect(url_for('auth.index'))
        
        # Check if we received an authorization code
        if not code:
            logger.error("No authorization code received from Spotify")
            flash('No authorization code received from Spotify. Please try again.', 'error')
            return redirect(url_for('auth.index'))
        
        # Exchange code for tokens
        try:
            token_data = exchange_code_for_token(code, state)
        except ValueError as e:
            logger.error(f"Token exchange validation failed: {str(e)}")
            flash(str(e), 'error')
            return redirect(url_for('auth.index'))
        except Exception as e:
            logger.error(f"Token exchange failed: {str(e)}")
            flash('Failed to authenticate with Spotify. Please try again.', 'error')
            return redirect(url_for('auth.index'))
        
        # Get user profile with the access token
        try:
            spotify_client = SpotifyClient(token_data['access_token'])
            user_profile = spotify_client.get_user_profile()
            
            if not user_profile:
                logger.error("Failed to get user profile from Spotify")
                flash('Failed to get user profile from Spotify. Please try again.', 'error')
                return redirect(url_for('auth.index'))
            
        except Exception as profile_e:
            logger.error(f"Exception during user profile retrieval: {str(profile_e)}")
            flash('Error retrieving user profile. Please try again.', 'error')
            return redirect(url_for('auth.index'))
        
        logger.info(f"Successfully retrieved user profile for: {user_profile.get('id')}")
        
        # Save or update user in database
        user = User.query.get(user_profile['id'])
        if not user:
            logger.info(f"Creating new user: {user_profile['id']}")
            user = User(id=user_profile['id'])
        else:
            logger.info(f"Updating existing user: {user_profile['id']}")
        
        user.display_name = user_profile.get('display_name', '')
        user.email = user_profile.get('email', '')
        user.image_url = user_profile['images'][0]['url'] if user_profile.get('images') and len(user_profile['images']) > 0 else None
        user.access_token = token_data['access_token']
        user.refresh_token = token_data['refresh_token']
        user.token_expires_at = token_data['expires_at']
        user.last_login = datetime.utcnow()
        
        try:
            db.session.add(user)
            db.session.commit()
            logger.info(f"User data saved to database: {user.id}")
        except Exception as e:
            logger.error(f"Failed to save user to database: {e}")
            db.session.rollback()
            flash('Failed to save user data. Please try again.', 'error')
            return redirect(url_for('auth.index'))
        
        # Store user ID in session
        session['user_id'] = user.id
        session.pop('oauth_state', None)
        
        logger.info(f"User {user.id} successfully authenticated and logged in")
        flash('Successfully logged in!', 'success')
        return redirect(url_for('dashboard.dashboard'))
        
    except Exception as e:
        logger.error(f"Callback processing failed: {str(e)}")
        flash('An unexpected error occurred during authentication. Please try again.', 'error')
        return redirect(url_for('auth.index'))

@auth_bp.route('/logout')
def logout():
    """Log out user"""
    session.pop('user_id', None)
    session.pop('oauth_state', None)
    # Clear any cached music insights to ensure no data persists
    session.pop('music_taste_profile', None)
    session.pop('profile_timestamp', None)
    session.pop('current_recommendation_id', None)
    session.pop('last_recommendation_time', None)
    # Clear analysis caches
    session.pop('cached_psychological_analysis', None)
    session.pop('cached_psychological_timestamp', None)
    session.pop('cached_detailed_psychological_analysis', None)
    session.pop('cached_detailed_psychological_timestamp', None)
    session.pop('cached_musical_analysis', None)
    session.pop('cached_musical_timestamp', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.index')) 