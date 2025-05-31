from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

# This will be initialized in app.py
db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.String(50), primary_key=True)  # Spotify user ID
    display_name = db.Column(db.String(100))
    email = db.Column(db.String(120))
    image_url = db.Column(db.String(255))
    access_token = db.Column(db.Text)
    refresh_token = db.Column(db.Text)
    token_expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    recommendations = db.relationship('Recommendation', backref='user', lazy=True)
    feedback_entries = db.relationship('UserFeedback', backref='user', lazy=True)
    
    def __repr__(self):
        return f'<User {self.display_name}>'
    
    def is_token_expired(self):
        """Check if the access token has expired"""
        if not self.token_expires_at:
            return True
        return datetime.utcnow() >= self.token_expires_at

    def get_recent_recommendations(self, hours_back=24, limit=20):
        """Get recent recommendations to prevent duplicates"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        query = Recommendation.query.filter(
            Recommendation.user_id == self.id,
            Recommendation.created_at >= cutoff_time
        ).order_by(Recommendation.created_at.desc())
        
        # Only apply limit if it's not None
        if limit is not None:
            query = query.limit(limit)
            
        return query.all()
    
    def get_recommendation_history_for_prompt(self, hours_back=24, limit=15):
        """Get formatted recommendation history for LLM prompts"""
        recent_recs = self.get_recent_recommendations(hours_back, limit)
        
        if not recent_recs:
            return []
        
        # Format for LLM with more context
        formatted_recs = []
        for rec in recent_recs:
            time_ago = datetime.utcnow() - rec.created_at
            if time_ago.total_seconds() < 3600:  # Less than 1 hour
                time_desc = f"{int(time_ago.total_seconds() / 60)} minutes ago"
            else:
                time_desc = f"{int(time_ago.total_seconds() / 3600)} hours ago"
            
            formatted_recs.append(f'"{rec.track_name}" by {rec.artist_name} ({time_desc})')
        
        return formatted_recs


class Recommendation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), db.ForeignKey('user.id'), nullable=False)
    track_name = db.Column(db.String(255), nullable=False)
    artist_name = db.Column(db.String(255), nullable=False)
    track_uri = db.Column(db.String(255), nullable=False)
    album_name = db.Column(db.String(255))
    ai_reasoning = db.Column(db.Text)
    psychological_analysis = db.Column(db.Text)
    listening_data_snapshot = db.Column(db.Text)  # JSON of user data at recommendation time
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Enhanced tracking fields
    session_adjustment = db.Column(db.Text)  # Store the session adjustment used
    recommendation_method = db.Column(db.String(50))  # 'standard', 'lightning', 'playlist'
    was_played = db.Column(db.Boolean, default=False)  # Track if user actually played this
    last_played_at = db.Column(db.DateTime)  # When it was last played
    play_count = db.Column(db.Integer, default=0)  # How many times user played it
    
    # Feedback relationship
    feedback_entries = db.relationship('UserFeedback', backref='recommendation', lazy=True)

    def __repr__(self):
        return f'<Recommendation {self.track_name} by {self.artist_name}>'
    
    def mark_as_played(self):
        """Mark this recommendation as played by the user"""
        self.was_played = True
        self.last_played_at = datetime.utcnow()
        self.play_count = (self.play_count or 0) + 1
        db.session.commit()
    
    def get_track_identifier(self):
        """Get a normalized identifier for duplicate detection"""
        return f"{self.track_name.lower().strip()} - {self.artist_name.lower().strip()}"
    
    @staticmethod
    def is_duplicate(user_id, track_name, artist_name, hours_back=24):
        """Check if this track was recently recommended"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        # Normalize track and artist names for comparison
        track_normalized = track_name.lower().strip()
        artist_normalized = artist_name.lower().strip()
        
        existing = Recommendation.query.filter(
            Recommendation.user_id == user_id,
            Recommendation.created_at >= cutoff_time,
            db.func.lower(Recommendation.track_name) == track_normalized,
            db.func.lower(Recommendation.artist_name) == artist_normalized
        ).first()
        
        return existing is not None
    
    @staticmethod
    def get_artist_recommendation_count(user_id, artist_name, hours_back=72):
        """Get how many times we've recommended this artist recently"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        artist_normalized = artist_name.lower().strip()
        
        return Recommendation.query.filter(
            Recommendation.user_id == user_id,
            Recommendation.created_at >= cutoff_time,
            db.func.lower(Recommendation.artist_name) == artist_normalized
        ).count()


class UserAnalysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), db.ForeignKey('user.id'), nullable=False)
    analysis_type = db.Column(db.String(50), nullable=False)  # 'psychological', 'musical'
    analysis_data = db.Column(db.Text, nullable=False)  # JSON data of the analysis
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship back to user
    user = db.relationship('User', backref='analyses')
    
    def __repr__(self):
        return f'<UserAnalysis {self.user_id}: {self.analysis_type}>'
    
    @staticmethod
    def get_latest_analysis(user_id, analysis_type, max_age_hours=24):
        """Get the latest analysis of a specific type for a user if it's recent enough"""
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        return UserAnalysis.query.filter(
            UserAnalysis.user_id == user_id,
            UserAnalysis.analysis_type == analysis_type,
            UserAnalysis.updated_at >= cutoff_time
        ).order_by(UserAnalysis.updated_at.desc()).first()
    
    @staticmethod
    def save_analysis(user_id, analysis_type, analysis_data):
        """Save or update an analysis for a user"""
        import json
        
        # Check if analysis already exists
        existing = UserAnalysis.query.filter(
            UserAnalysis.user_id == user_id,
            UserAnalysis.analysis_type == analysis_type
        ).first()
        
        if existing:
            # Update existing analysis
            existing.analysis_data = json.dumps(analysis_data) if isinstance(analysis_data, dict) else analysis_data
            existing.updated_at = datetime.utcnow()
            analysis = existing
        else:
            # Create new analysis
            analysis = UserAnalysis(
                user_id=user_id,
                analysis_type=analysis_type,
                analysis_data=json.dumps(analysis_data) if isinstance(analysis_data, dict) else analysis_data
            )
            db.session.add(analysis)
        
        db.session.commit()
        return analysis
    
    def get_data(self):
        """Get the analysis data as a Python object"""
        import json
        try:
            return json.loads(self.analysis_data)
        except:
            return self.analysis_data


class UserFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), db.ForeignKey('user.id'), nullable=False)
    recommendation_id = db.Column(db.Integer, db.ForeignKey('recommendation.id'), nullable=False)
    feedback_text = db.Column(db.Text, nullable=False)
    sentiment = db.Column(db.String(20))  # positive, negative, neutral
    ai_processed_feedback = db.Column(db.Text)  # AI analysis of the feedback
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<UserFeedback {self.id}: {self.sentiment}>'
