import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import google.generativeai as genai
from difflib import SequenceMatcher

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

def fuzzy_similarity(a: str, b: str) -> float:
    """Calculate fuzzy similarity between two strings"""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

def normalize_string(s: str) -> str:
    """Normalize string for comparison"""
    return s.lower().strip().replace("'", "").replace("\"", "").replace("&", "and")

class StructuredLLM:
    """Structured LLM operations for music recommendation system"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def find_best_match_manually(self, song_title: str, artist_name: str, search_results: List[Dict[str, Any]]) -> tuple[int, float]:
        """
        Find best match using fuzzy string matching as fallback
        
        Returns:
            tuple: (best_index, confidence_score)
        """
        best_index = 0
        best_score = 0.0
        
        target_song = normalize_string(song_title)
        target_artist = normalize_string(artist_name)
        
        for i, track in enumerate(search_results):
            track_name = normalize_string(track['name'])
            track_artist = normalize_string(track['artists'][0]['name'] if track['artists'] else '')
            
            # Calculate similarity scores
            song_similarity = fuzzy_similarity(target_song, track_name)
            artist_similarity = fuzzy_similarity(target_artist, track_artist)
            
            # Weighted score (artist match is more important)
            combined_score = (song_similarity * 0.4) + (artist_similarity * 0.6)
            
            self.logger.debug(f"Track {i}: '{track_name}' by '{track_artist}' - Song: {song_similarity:.2f}, Artist: {artist_similarity:.2f}, Combined: {combined_score:.2f}")
            
            if combined_score > best_score:
                best_score = combined_score
                best_index = i
        
        return best_index, best_score
    
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
            if not search_results:
                raise ValueError("No search results provided")
            
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
            
            # Create improved prompt for LLM
            prompt = f"""
You are helping to select the best Spotify search result that matches the intended song and artist.

Target Song: "{song_title}"
Target Artist: "{artist_name}"

Available search results:
{json.dumps(results_for_analysis, indent=2)}

CRITICAL INSTRUCTIONS:
1. You MUST select an index between 0 and {len(search_results) - 1}
2. Look for EXACT matches first, then close matches
3. Artist name match is MORE important than song title match
4. Consider common variations in spelling, punctuation, and capitalization
5. If no good match exists, select the closest one but give it a low match_score

Respond with a JSON object in this EXACT format (no additional text):
{{
    "selected_index": <integer between 0 and {len(search_results) - 1}>,
    "match_score": <float between 0.0 and 1.0>,
    "confidence": <float between 0.0 and 1.0>,
    "reasoning": "<brief explanation of why this result was selected>"
}}

Example response:
{{
    "selected_index": 0,
    "match_score": 0.95,
    "confidence": 0.9,
    "reasoning": "Exact match for both song title and artist name"
}}
"""

            # Generate response
            response = model.generate_content(prompt)
            response_text = response.text.strip() if response and response.text else ""
            
            # Parse JSON response with better error handling
            analysis = None
            try:
                # Clean the response text
                response_text = response_text.strip()
                
                # Find JSON boundaries
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                
                if json_start != -1 and json_end != -1:
                    json_text = response_text[json_start:json_end]
                    analysis = json.loads(json_text)
                    
                    # Validate the analysis structure
                    required_fields = ['selected_index', 'match_score', 'confidence', 'reasoning']
                    if not all(field in analysis for field in required_fields):
                        raise ValueError(f"Missing required fields. Expected: {required_fields}, Got: {list(analysis.keys())}")
                        
                else:
                    raise ValueError("No valid JSON object found in response")
                
            except (json.JSONDecodeError, ValueError) as e:
                self.logger.warning(f"Failed to parse LLM response as JSON: {e}. Response was: {response_text[:200]}...")
                
                # Fallback to manual fuzzy matching
                self.logger.info("Using fuzzy string matching as fallback")
                fallback_index, fallback_score = self.find_best_match_manually(song_title, artist_name, search_results)
                
                analysis = {
                    "selected_index": fallback_index,
                    "match_score": fallback_score,
                    "confidence": 0.7 if fallback_score > 0.8 else 0.4,
                    "reasoning": f"Selected using fuzzy matching (LLM parse failed). Match score: {fallback_score:.2f}"
                }
            
            # Validate and sanitize selected index
            selected_index = analysis.get('selected_index', 0)
            if not isinstance(selected_index, int) or selected_index < 0 or selected_index >= len(search_results):
                self.logger.warning(f"Invalid selected index {selected_index}. Using fuzzy matching fallback.")
                fallback_index, fallback_score = self.find_best_match_manually(song_title, artist_name, search_results)
                selected_index = fallback_index
                analysis['match_score'] = fallback_score
                analysis['confidence'] = 0.6 if fallback_score > 0.7 else 0.3
                analysis['reasoning'] = f"Index validation failed, used fuzzy matching. Match score: {fallback_score:.2f}"
            
            # Get the selected track
            selected_track = search_results[selected_index]
            
            # Validate the match quality
            selected_track_name = selected_track['name']
            selected_artist_name = selected_track['artists'][0]['name'] if selected_track['artists'] else 'Unknown'
            
            # Check if this is actually a good match
            song_similarity = fuzzy_similarity(song_title, selected_track_name)
            artist_similarity = fuzzy_similarity(artist_name, selected_artist_name)
            
            if artist_similarity < 0.6:  # Poor artist match
                self.logger.warning(f"Poor artist match detected: '{artist_name}' vs '{selected_artist_name}' (similarity: {artist_similarity:.2f})")
                analysis['confidence'] = min(analysis['confidence'], 0.4)
                analysis['reasoning'] += f" [WARNING: Artist mismatch detected]"
            
            # Create structured result
            selected_track_data = SelectedTrackData(
                track_id=selected_track['id'],
                track_name=selected_track_name,
                artist_name=selected_artist_name,
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
            
            # Log similarity scores for debugging
            self.logger.info(f"Match quality - Song: {song_similarity:.2f}, Artist: {artist_similarity:.2f}")
            
            return selection_result
            
        except Exception as e:
            self.logger.error(f"Error in LLM track selection: {str(e)}")
            
            # Ultimate fallback to manual matching
            try:
                fallback_index, fallback_score = self.find_best_match_manually(song_title, artist_name, search_results)
                selected_track = search_results[fallback_index]
                
                selected_track_data = SelectedTrackData(
                    track_id=selected_track['id'],
                    track_name=selected_track['name'],
                    artist_name=selected_track['artists'][0]['name'] if selected_track['artists'] else 'Unknown',
                    album_name=selected_track['album']['name'],
                    album_image_url=selected_track['album']['images'][0]['url'] if selected_track['album']['images'] else None,
                    track_uri=selected_track['uri'],
                    external_url=selected_track['external_urls']['spotify'],
                    preview_url=selected_track.get('preview_url'),
                    match_score=fallback_score,
                    reasoning=f"Emergency fallback selection due to error: {str(e)[:100]}. Match score: {fallback_score:.2f}"
                )
                
                return SelectionResult(
                    selected_result=selected_track_data,
                    confidence=0.3
                )
                
            except Exception as fallback_error:
                self.logger.error(f"Even fallback matching failed: {fallback_error}")
                
                # Last resort - just use first result
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
                    match_score=0.1,
                    reasoning=f"Last resort fallback due to errors. Original error: {str(e)[:100]}"
                )
                
                return SelectionResult(
                    selected_result=selected_track_data,
                    confidence=0.1
                )

# Create global instance
structured_llm = StructuredLLM() 