import json
import logging
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, ValidationError
from google.generativeai.types import GenerationConfig
from flask import current_app
from llm_utils import llm_manager


class MusicTasteAnalysis(BaseModel):
    """Structured output for music taste analysis"""
    user_taste_profile: str = Field(
        description="2-3 sentences describing overall music preferences with specific data points"
    )
    recent_mood_analysis: str = Field(
        description="1-2 sentences examining recent listening patterns and trends"
    )
    analysis_ready: bool = Field(
        description="Whether full AI analysis was completed successfully"
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0, 
        description="Analysis confidence level from 0.0 to 1.0"
    )
    dominant_genres: List[str] = Field(
        description="Top 3-5 genres identified in user's taste",
        max_items=5
    )
    energy_level: Literal["high", "medium", "low"] = Field(
        description="Overall energy preference based on listening patterns"
    )


class TrackRecommendation(BaseModel):
    """Structured output for single track recommendations"""
    track_title: str = Field(
        description="Exact track title as it would appear on Spotify"
    )
    artist_name: str = Field(
        description="Primary artist name only"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Recommendation confidence score 0.0-1.0"
    )
    reasoning: str = Field(
        description="Detailed explanation of why this track fits the user's taste"
    )
    genre_tags: List[str] = Field(
        description="Primary genres for this track",
        max_items=3
    )
    energy_level: Literal["high", "medium", "low"] = Field(
        description="Energy level of the recommended track"
    )
    discovery_factor: float = Field(
        ge=0.0, le=1.0,
        description="How novel this recommendation is: 0.0=familiar artist, 1.0=new discovery"
    )


class PlaylistTrack(BaseModel):
    """Individual track in a playlist recommendation"""
    track_title: str = Field(description="Exact track title")
    artist_name: str = Field(description="Primary artist name")
    genre: str = Field(description="Primary genre")
    energy_level: Literal["high", "medium", "low"] = Field(description="Track energy")


class PlaylistRecommendation(BaseModel):
    """Structured output for playlist generation"""
    tracks: List[PlaylistTrack] = Field(
        description="List of recommended tracks for the playlist"
    )
    overall_theme: str = Field(
        description="Explanation of the playlist's coherence and theme"
    )
    variety_score: float = Field(
        ge=0.0, le=1.0,
        description="How diverse the playlist is: 0.0=very similar, 1.0=very diverse"
    )
    total_tracks: int = Field(
        description="Total number of tracks recommended"
    )


class FeedbackInsights(BaseModel):
    """Structured output for feedback analysis"""
    insights_summary: str = Field(
        description="Conversational summary of what has been learned from user feedback"
    )
    key_preferences: List[str] = Field(
        description="Key patterns identified in user likes/dislikes",
        max_items=5
    )
    improvement_areas: List[str] = Field(
        description="Areas where recommendations can be improved",
        max_items=3
    )
    confidence_in_learning: float = Field(
        ge=0.0, le=1.0,
        description="How confident the system is about learned preferences"
    )


class ParsedTrackRecommendation(BaseModel):
    """Structured output for parsing a track recommendation text"""
    track_name: str = Field(
        description="The exact track name extracted from the recommendation"
    )
    artist_name: str = Field(
        description="The exact artist name extracted from the recommendation"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in the extraction accuracy"
    )


class SpotifySearchResult(BaseModel):
    """Represents a single Spotify search result for evaluation"""
    track_id: str = Field(description="Spotify track ID")
    track_name: str = Field(description="Track name from Spotify")
    artist_name: str = Field(description="Primary artist name from Spotify")
    album_name: str = Field(description="Album name from Spotify")
    track_uri: str = Field(description="Spotify track URI")
    external_url: str = Field(description="Spotify external URL")
    preview_url: Optional[str] = Field(description="Preview URL if available")
    album_image_url: Optional[str] = Field(description="Album cover image URL")
    match_score: float = Field(
        ge=0.0, le=1.0,
        description="How well this result matches the intended recommendation"
    )
    reasoning: str = Field(
        description="Explanation of why this result was selected and how well it matches"
    )


class SpotifySearchSelection(BaseModel):
    """Structured output for selecting the best Spotify search result"""
    selected_result: SpotifySearchResult = Field(
        description="The best matching result from the search"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Overall confidence in the selection"
    )


def get_generation_config(output_class: type[BaseModel]) -> GenerationConfig:
    """Create generation config for structured output"""
    return GenerationConfig(
        response_mime_type="application/json",
        response_schema=output_class.model_json_schema()
    )


class PromptTemplates:
    """Centralized prompt management with structured output instructions"""
    
    MUSIC_ANALYSIS_PROMPT = """
Analyze this user's Spotify listening data and provide thoughtful insights about their musical preferences and patterns. Be conversational and informative while remaining positive.

MUSIC DATA:
{music_data}

Provide your analysis in the exact JSON format specified. Requirements:

- user_taste_profile: 2-3 sentences describing their overall music preferences with specific data points. Include genre patterns, favorite artists, or listening habits. Focus on what makes their taste unique and interesting.

- recent_mood_analysis: 1-2 sentences examining their recent listening patterns. Mention specific trends, energy levels, or genre shifts. Connect these patterns to their current musical journey with positive insights.

- confidence_score: Rate your confidence in this analysis from 0.0 to 1.0 based on data quality and quantity.

- dominant_genres: List the top 3-5 genres that best represent their taste.

- energy_level: Categorize their overall preference as "high", "medium", or "low" energy.

Include specific numbers and data points (e.g., "Your 15 top artists span 8 different genres"). Mention actual song titles, artists, or genres from their data. Make thoughtful connections between musical choices and personality traits.
"""

    RECOMMENDATION_PROMPT = """
Based on this comprehensive user analysis and psychological profile, recommend ONE specific song that perfectly matches this user's taste.

USER PSYCHOLOGICAL & MUSICAL ANALYSIS:
{user_analysis}

RECENT LISTENING HISTORY (DO NOT REPEAT THESE):
{recent_tracks}

RECENTLY RECOMMENDED TRACKS (DO NOT REPEAT THESE):
{recently_recommended}

SESSION PREFERENCE: {session_adjustment}

REQUIREMENTS:
1. Choose a song that matches their taste but is a fresh discovery
2. DO NOT recommend any song from the recent listening history above
3. DO NOT recommend any song from the recently recommended tracks above
4. The track should exist on Spotify with the exact title and artist provided

Provide your recommendation in the exact JSON format specified:

- track_title: Exact song title as it appears on Spotify
- artist_name: Primary artist name only  
- confidence: How well this matches their taste (0.0-1.0)
- reasoning: Detailed explanation connecting their taste analysis to this recommendation
- genre_tags: Primary genres for this track (up to 3)
- energy_level: "high", "medium", or "low"
- discovery_factor: 0.0 = safe/familiar artist, 1.0 = completely new discovery
"""

    PLAYLIST_GENERATION_PROMPT = """
Based on this user's comprehensive musical profile, create a playlist with exactly {song_count} diverse tracks.

USER MUSICAL ANALYSIS:
{user_analysis}

PLAYLIST CONTEXT:
- Title: {playlist_name}
- Description: {playlist_description}

TRACKS TO AVOID (recently recommended):
{recent_tracks}

REQUIREMENTS:
1. Recommend exactly {song_count} different songs
2. Each song should be a real, existing track on Spotify
3. Variety is important - don't repeat artists unless the user heavily favors them
4. Consider the playlist title and description for thematic guidance
5. Match the user's taste while providing some discovery
6. Avoid any tracks from the "recently recommended" list

Provide your playlist in the exact JSON format specified with all required fields.
"""

    FEEDBACK_ANALYSIS_PROMPT = """
Analyze this user's feedback history to understand their preferences and what the AI system has learned.

FEEDBACK HISTORY:
{feedback_data}

Generate insights in the exact JSON format specified:

- insights_summary: Write 2-3 sentences explaining what you've learned about their taste. Start with something like "Based on your feedback, I've learned that..." Be friendly and conversational.

- key_preferences: List specific patterns in their likes/dislikes (up to 5 items)

- improvement_areas: List areas where recommendations can be improved (up to 3 items)

- confidence_in_learning: Rate how confident you are about the learned preferences (0.0-1.0)

Focus on actionable insights that show the AI is adapting to their preferences.
"""

    TRACK_PARSING_PROMPT = """
Parse the following AI recommendation text to extract the exact track name and artist name.

RECOMMENDATION TEXT:
{recommendation_text}

Extract the track and artist information in the exact JSON format specified:

- track_name: The exact track title (remove any quotes)
- artist_name: The exact artist name (remove any quotes)  
- confidence: Rate your confidence in the extraction accuracy (0.0-1.0)

Examples:
- Input: '"Bohemian Rhapsody" by Queen' → track_name: "Bohemian Rhapsody", artist_name: "Queen"
- Input: 'The Beatles - Hey Jude' → track_name: "Hey Jude", artist_name: "The Beatles"
- Input: 'I recommend "Smells Like Teen Spirit" from Nirvana' → track_name: "Smells Like Teen Spirit", artist_name: "Nirvana"
"""

    SPOTIFY_SELECTION_PROMPT = """
Select the best matching track from these Spotify search results based on the intended recommendation.

INTENDED RECOMMENDATION:
Track: {intended_track}
Artist: {intended_artist}

SPOTIFY SEARCH RESULTS:
{search_results}

Select the best match in the exact JSON format specified:

- selected_result: The best matching track with all details and a match_score (0.0-1.0)
- confidence: Overall confidence in the selection (0.0-1.0)

Consider:
1. Exact track name match (highest priority)
2. Exact artist name match (high priority)
3. Similar track names by the same artist
4. Same track by similar/related artists
5. Cover versions or remixes as last resort

Provide detailed reasoning for your selection.
"""


class StructuredLLMManager:
    """Manages structured LLM calls with validation and error recovery"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def generate_music_analysis(self, model, music_data: dict) -> MusicTasteAnalysis:
        """Generate music analysis with structured validation"""
        
        def _generate():
            config = get_generation_config(MusicTasteAnalysis)
            prompt = PromptTemplates.MUSIC_ANALYSIS_PROMPT.format(
                music_data=json.dumps(music_data, indent=2)
            )
            
            response = model.generate_content(prompt, generation_config=config)
            
            # Validate the response matches our schema
            try:
                return MusicTasteAnalysis.model_validate_json(response.text)
            except ValidationError as e:
                self.logger.error(f"Structured output validation failed: {e}")
                self.logger.error(f"Raw response: {response.text}")
                raise ValueError(f"Invalid response structure: {e}")
        
        # Use circuit breaker protection
        result = llm_manager.call_music_analysis(_generate)
        
        if result['success']:
            return result['data']
        else:
            # Return fallback structured response
            self.logger.warning("Using fallback music analysis due to LLM failure")
            return MusicTasteAnalysis(
                user_taste_profile="Music taste analysis is temporarily unavailable. Please try again later.",
                recent_mood_analysis="Unable to analyze recent listening patterns at this time.",
                analysis_ready=False,
                confidence_score=0.0,
                dominant_genres=["unknown"],
                energy_level="medium"
            )
    
    def generate_recommendation(
        self, 
        model, 
        user_analysis: str, 
        recent_tracks: list, 
        recently_recommended: list,
        session_adjustment: str = ""
    ) -> TrackRecommendation:
        """Generate track recommendation with structured validation"""
        
        def _generate():
            config = get_generation_config(TrackRecommendation)
            prompt = PromptTemplates.RECOMMENDATION_PROMPT.format(
                user_analysis=user_analysis,
                recent_tracks=json.dumps(recent_tracks[:20]),  # Limit for token efficiency
                recently_recommended=json.dumps(recently_recommended),
                session_adjustment=session_adjustment or "No specific preference for this session"
            )
            
            response = model.generate_content(prompt, generation_config=config)
            
            try:
                return TrackRecommendation.model_validate_json(response.text)
            except ValidationError as e:
                self.logger.error(f"Recommendation validation failed: {e}")
                self.logger.error(f"Raw response: {response.text}")
                raise ValueError(f"Invalid recommendation structure: {e}")
        
        # Use circuit breaker protection
        result = llm_manager.call_recommendation(_generate)
        
        if result['success']:
            return result['data']
        else:
            # Return fallback structured response
            self.logger.warning("Using fallback recommendation due to LLM failure")
            raise Exception("AI recommendation temporarily unavailable")
    
    def generate_playlist(
        self,
        model,
        user_analysis: str,
        playlist_name: str,
        playlist_description: str,
        song_count: int,
        recent_tracks: list
    ) -> PlaylistRecommendation:
        """Generate playlist with structured validation"""
        
        def _generate():
            config = get_generation_config(PlaylistRecommendation)
            prompt = PromptTemplates.PLAYLIST_GENERATION_PROMPT.format(
                user_analysis=user_analysis,
                playlist_name=playlist_name,
                playlist_description=playlist_description,
                song_count=song_count,
                recent_tracks=json.dumps(recent_tracks)
            )
            
            response = model.generate_content(prompt, generation_config=config)
            
            try:
                return PlaylistRecommendation.model_validate_json(response.text)
            except ValidationError as e:
                self.logger.error(f"Playlist validation failed: {e}")
                self.logger.error(f"Raw response: {response.text}")
                raise ValueError(f"Invalid playlist structure: {e}")
        
        # Use circuit breaker protection
        result = llm_manager.call_playlist_generation(_generate)
        
        if result['success']:
            return result['data']
        else:
            # Return fallback
            self.logger.warning("Using fallback playlist generation due to LLM failure")
            raise Exception("AI playlist generation temporarily unavailable")
    
    def generate_feedback_insights(self, model, feedback_data: list) -> FeedbackInsights:
        """Generate feedback insights with structured validation"""
        
        def _generate():
            config = get_generation_config(FeedbackInsights)
            prompt = PromptTemplates.FEEDBACK_ANALYSIS_PROMPT.format(
                feedback_data=json.dumps(feedback_data, indent=2)
            )
            
            response = model.generate_content(prompt, generation_config=config)
            
            try:
                return FeedbackInsights.model_validate_json(response.text)
            except ValidationError as e:
                self.logger.error(f"Feedback insights validation failed: {e}")
                self.logger.error(f"Raw response: {response.text}")
                raise ValueError(f"Invalid feedback insights structure: {e}")
        
        # Use circuit breaker protection
        result = llm_manager.call_feedback_analysis(_generate)
        
        if result['success']:
            return result['data']
        else:
            # Return fallback
            self.logger.warning("Using fallback feedback insights due to LLM failure")
            return FeedbackInsights(
                insights_summary="Feedback analysis is temporarily unavailable. Please try again later.",
                key_preferences=["Analysis pending"],
                improvement_areas=["System maintenance in progress"],
                confidence_in_learning=0.0
            )

    def parse_track_recommendation(self, model, recommendation_text: str) -> ParsedTrackRecommendation:
        """Parse a track recommendation text to extract track and artist names"""
        
        def _generate():
            config = get_generation_config(ParsedTrackRecommendation)
            prompt = PromptTemplates.TRACK_PARSING_PROMPT.format(
                recommendation_text=recommendation_text
            )
            
            response = model.generate_content(prompt, generation_config=config)
            
            try:
                return ParsedTrackRecommendation.model_validate_json(response.text)
            except ValidationError as e:
                self.logger.error(f"Track parsing validation failed: {e}")
                self.logger.error(f"Raw response: {response.text}")
                raise ValueError(f"Invalid track parsing structure: {e}")
        
        # Use circuit breaker protection  
        result = llm_manager.call_music_analysis(_generate)  # Reuse circuit breaker
        
        if result['success']:
            return result['data']
        else:
            # Return fallback - try simple parsing
            self.logger.warning("Using fallback track parsing due to LLM failure")
            if " by " in recommendation_text:
                parts = recommendation_text.replace('"', '').split(" by ", 1)
                track_name = parts[0].strip()
                artist_name = parts[1].strip()
            else:
                track_name = recommendation_text.replace('"', '').strip()
                artist_name = "Unknown Artist"
            
            return ParsedTrackRecommendation(
                track_name=track_name,
                artist_name=artist_name,
                confidence=0.5
            )

    def select_spotify_result(self, model, intended_track: str, intended_artist: str, 
                            search_results: list) -> SpotifySearchSelection:
        """Select the best Spotify search result using LLM evaluation"""
        
        def _generate():
            config = get_generation_config(SpotifySearchSelection)
            
            # Format search results for the prompt
            formatted_results = []
            for i, track in enumerate(search_results):
                formatted_result = {
                    'index': i,
                    'track_name': track['name'],
                    'artist_name': track['artists'][0]['name'],
                    'album_name': track['album']['name'],
                    'track_id': track['id'],
                    'track_uri': track['uri'],
                    'external_url': track['external_urls']['spotify'],
                    'preview_url': track.get('preview_url'),
                    'album_image_url': track['album']['images'][0]['url'] if track['album']['images'] else None
                }
                formatted_results.append(formatted_result)
            
            prompt = PromptTemplates.SPOTIFY_SELECTION_PROMPT.format(
                intended_track=intended_track,
                intended_artist=intended_artist,
                search_results=json.dumps(formatted_results, indent=2)
            )
            
            response = model.generate_content(prompt, generation_config=config)
            
            try:
                return SpotifySearchSelection.model_validate_json(response.text)
            except ValidationError as e:
                self.logger.error(f"Spotify selection validation failed: {e}")
                self.logger.error(f"Raw response: {response.text}")
                raise ValueError(f"Invalid Spotify selection structure: {e}")
        
        # Use circuit breaker protection
        result = llm_manager.call_recommendation(_generate)  # Reuse circuit breaker
        
        if result['success']:
            return result['data']
        else:
            # Return fallback - select first result
            self.logger.warning("Using fallback Spotify selection due to LLM failure")
            first_track = search_results[0]
            return SpotifySearchSelection(
                selected_result=SpotifySearchResult(
                    track_id=first_track['id'],
                    track_name=first_track['name'],
                    artist_name=first_track['artists'][0]['name'],
                    album_name=first_track['album']['name'],
                    track_uri=first_track['uri'],
                    external_url=first_track['external_urls']['spotify'],
                    preview_url=first_track.get('preview_url'),
                    album_image_url=first_track['album']['images'][0]['url'] if first_track['album']['images'] else None,
                    match_score=0.7,
                    reasoning="Fallback selection: Using first search result due to AI processing failure"
                ),
                confidence=0.5
            )


# Global structured LLM manager instance
structured_llm = StructuredLLMManager() 