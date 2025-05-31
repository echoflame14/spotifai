"""
Dashboard and music control routes.

This module handles dashboard display and basic music control functionality.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app import app, db
from models import User
from spotify_client import SpotifyClient
from utils.spotify_auth import refresh_user_token
from utils.ai_analysis import generate_basic_insights
import logging

logger = logging.getLogger(__name__)

# Create dashboard blueprint
dashboard_bp = Blueprint('dashboard', __name__)

def require_auth():
    """Check if user is authenticated and return user object"""
    if 'user_id' not in session:
        return None
    
    user = User.query.get(session['user_id'])
    if not user:
        session.pop('user_id', None)
        return None
    
    # Check if token needs refresh
    if user.is_token_expired():
        if not refresh_user_token(user):
            return None
    
    return user

@dashboard_bp.route('/dashboard')
def dashboard():
    """Main dashboard showing user's music with comprehensive AI analysis"""
    user = require_auth()
    if not user:
        flash('Please log in to access dashboard.', 'error')
        return redirect(url_for('auth.index'))
    
    spotify_client = SpotifyClient(user.access_token)
    
    # Get currently playing track
    current_track = spotify_client.get_current_track()
    
    # Get playback state
    playback_state = spotify_client.get_playback_state()
    
    # Check if we have cached analyses
    psychological_analysis = session.get('psychological_analysis')
    musical_analysis = session.get('musical_analysis')
    
    # Generate basic music insights (full analysis will be generated client-side with user's API key)
    music_insights = generate_basic_insights(spotify_client)
    
    return render_template('dashboard.html', 
                         user=user, 
                         current_track=current_track,
                         playback_state=playback_state,
                         music_insights=music_insights,
                         psychological_analysis=psychological_analysis,
                         musical_analysis=musical_analysis)

@dashboard_bp.route('/play', methods=['GET', 'POST'])
def play():
    """Resume playback"""
    user = require_auth()
    if not user:
        if request.method == 'POST':
            return jsonify({'error': 'Not authenticated'}), 401
        return redirect(url_for('auth.index'))
    
    spotify_client = SpotifyClient(user.access_token)
    success = spotify_client.play()
    
    if request.method == 'POST':
        return jsonify({'success': success})
    
    if success:
        flash('Playback resumed', 'success')
    else:
        flash('Failed to resume playback. Make sure Spotify is open on a device.', 'error')
    
    return redirect(url_for('dashboard.dashboard'))

@dashboard_bp.route('/pause', methods=['GET', 'POST'])
def pause():
    """Pause playback"""
    user = require_auth()
    if not user:
        if request.method == 'POST':
            return jsonify({'error': 'Not authenticated'}), 401
        return redirect(url_for('auth.index'))
    
    spotify_client = SpotifyClient(user.access_token)
    success = spotify_client.pause()
    
    if request.method == 'POST':
        return jsonify({'success': success})
    
    if success:
        flash('Playback paused', 'success')
    else:
        flash('Failed to pause playback', 'error')
    
    return redirect(url_for('dashboard.dashboard'))

@dashboard_bp.route('/play-recommendation', methods=['POST'])
def play_recommendation():
    """Play the AI recommended track"""
    user = require_auth()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    track_uri = request.json.get('track_uri')
    if not track_uri:
        return jsonify({'success': False, 'message': 'Track URI required'}), 400
    
    spotify_client = SpotifyClient(user.access_token)
    
    # Check for available devices first
    devices = spotify_client.get_devices()
    if not devices or not devices.get('devices'):
        return jsonify({
            'success': False, 
            'message': 'No Spotify devices found. Please open the Spotify app on your phone, computer, or any device, then try again.'
        })
    
    success = spotify_client.play_track(track_uri)
    
    if success:
        # Mark the recommendation as played if we have the current recommendation ID
        current_rec_id = session.get('current_recommendation_id')
        if current_rec_id:
            from models import Recommendation
            recommendation = Recommendation.query.get(current_rec_id)
            if recommendation and recommendation.user_id == user.id:
                recommendation.mark_as_played()
                logger.info(f"Marked recommendation {current_rec_id} as played")
        
        return jsonify({'success': True, 'message': 'Playing recommended track'})
    else:
        return jsonify({
            'success': False, 
            'message': 'Failed to play track. Make sure you have Spotify Premium and an active device.'
        }) 