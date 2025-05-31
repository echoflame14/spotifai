import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import google.generativeai as genai

# Get logger
logger = logging.getLogger(__name__)

@dataclass
class SelectedTrackData:
    """Data class for selected track information"""
    track_id: str
    track_name: str
    artist_name: str
    album_name: str
    album_image_url: Optional[str]
    track_uri: str
    external_url: str
    preview_url: Optional[str]
    match_score: float
    reasoning: str

@dataclass
class SelectionResult:
    """Data class for selection result with confidence"""
    selected_result: SelectedTrackData
    confidence: float

class StructuredLLM:
    """Structured LLM operations for music recommendation system"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def select_spotify_result(self, model, song_title: str, artist_name: str, search_results: List[Dict[str, Any]]) -> SelectionResult:
        """
        Use LLM to select the best Spotify search result that matches the intended song and artist.
        
        Args:
            model: The generative AI model to use
            song_title: The target song title
            artist_name: The target artist name
            search_results: List of Spotify track objects from search API
            
        Returns:
            SelectionResult with the best matching track and confidence score
        """
        try:
            # Prepare search results for LLM analysis
            results_for_analysis = []
            for i, track in enumerate(search_results):
                track_info = {
                    'index': i,
                    'track_id': track['id'],
                    'track_name': track['name'],
                    'artist_name': track['artists'][0]['name'] if track['artists'] else 'Unknown',
                    'album_name': track['album']['name'],
                    'album_image_url': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'track_uri': track['uri'],
                    'external_url': track['external_urls']['spotify'],
                    'preview_url': track.get('preview_url'),
                    'popularity': track.get('popularity', 0),
                    'duration_ms': track.get('duration_ms', 0)
                }
                results_for_analysis.append(track_info)
            
            # Create prompt for LLM
            prompt = f"""
You are helping to select the best Spotify search result that matches the intended song and artist.

Target Song: "{song_title}"
Target Artist: "{artist_name}"

Available search results:
{json.dumps(results_for_analysis, indent=2)}

Please analyze these results and select the one that best matches the target song and artist. Consider:
1. Exact or very close match of song title
2. Exact or very close match of artist name
3. Popularity as a tie-breaker
4. Album context if helpful

Respond with a JSON object in this exact format:
{{
    "selected_index": <index of best match>,
    "match_score": <float between 0.0 and 1.0>,
    "confidence": <float between 0.0 and 1.0>,
    "reasoning": "<brief explanation of why this result was selected>"
}}

Be strict about exact matches but allow for minor variations in spelling, capitalization, or punctuation.
"""

            # Generate response
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Parse JSON response
            try:
                # Extract JSON from response
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_text = response_text[json_start:json_end]
                    analysis = json.loads(json_text)
                else:
                    raise ValueError("No JSON found in response")
                
            except (json.JSONDecodeError, ValueError) as e:
                self.logger.warning(f"Failed to parse LLM response as JSON: {e}. Using first result as fallback.")
                analysis = {
                    "selected_index": 0,
                    "match_score": 0.5,
                    "confidence": 0.3,
                    "reasoning": "Fallback selection due to parsing error"
                }
            
            # Validate selected index
            selected_index = analysis.get('selected_index', 0)
            if selected_index < 0 or selected_index >= len(search_results):
                self.logger.warning(f"Invalid selected index {selected_index}. Using index 0.")
                selected_index = 0
            
            # Get the selected track
            selected_track = search_results[selected_index]
            
            # Create structured result
            selected_track_data = SelectedTrackData(
                track_id=selected_track['id'],
                track_name=selected_track['name'],
                artist_name=selected_track['artists'][0]['name'] if selected_track['artists'] else 'Unknown',
                album_name=selected_track['album']['name'],
                album_image_url=selected_track['album']['images'][0]['url'] if selected_track['album']['images'] else None,
                track_uri=selected_track['uri'],
                external_url=selected_track['external_urls']['spotify'],
                preview_url=selected_track.get('preview_url'),
                match_score=analysis.get('match_score', 0.5),
                reasoning=analysis.get('reasoning', 'Selected by LLM analysis')
            )
            
            selection_result = SelectionResult(
                selected_result=selected_track_data,
                confidence=analysis.get('confidence', 0.5)
            )
            
            self.logger.info(f"LLM selected track {selected_index}: '{selected_track_data.track_name}' by {selected_track_data.artist_name} (score: {selected_track_data.match_score:.2f})")
            
            return selection_result
            
        except Exception as e:
            self.logger.error(f"Error in LLM track selection: {str(e)}")
            # Fallback to first result
            first_track = search_results[0]
            selected_track_data = SelectedTrackData(
                track_id=first_track['id'],
                track_name=first_track['name'],
                artist_name=first_track['artists'][0]['name'] if first_track['artists'] else 'Unknown',
                album_name=first_track['album']['name'],
                album_image_url=first_track['album']['images'][0]['url'] if first_track['album']['images'] else None,
                track_uri=first_track['uri'],
                external_url=first_track['external_urls']['spotify'],
                preview_url=first_track.get('preview_url'),
                match_score=0.5,
                reasoning=f"Fallback selection due to error: {str(e)}"
            )
            
            return SelectionResult(
                selected_result=selected_track_data,
                confidence=0.3
            )

# Create global instance
structured_llm = StructuredLLM() 