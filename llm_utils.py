import time
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Callable, Any, Dict
from flask import current_app

class LLMCircuitBreaker:
    """Circuit breaker pattern for LLM calls to handle failures gracefully"""
    
    def __init__(self, failure_threshold: int = 3, timeout: int = 300, half_open_max_calls: int = 2):
        self.failure_threshold = failure_threshold
        self.timeout = timeout  # seconds
        self.half_open_max_calls = half_open_max_calls
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
        self.half_open_calls = 0
        
        self.logger = logging.getLogger(__name__)
    
    def call(self, llm_function: Callable, *args, **kwargs) -> Dict[str, Any]:
        """Execute LLM function with circuit breaker protection"""
        
        # Check if circuit is open
        if self.state == 'OPEN':
            if self._should_attempt_reset():
                self.state = 'HALF_OPEN'
                self.half_open_calls = 0
                self.logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                self.logger.warning("Circuit breaker is OPEN, using fallback")
                return self._get_fallback_response()
        
        # Check if we're in half-open and have exceeded max calls
        if self.state == 'HALF_OPEN' and self.half_open_calls >= self.half_open_max_calls:
            self.logger.warning("Half-open max calls exceeded, using fallback")
            return self._get_fallback_response()
        
        try:
            # Attempt the LLM call
            self.logger.info(f"Attempting LLM call, circuit state: {self.state}")
            result = llm_function(*args, **kwargs)
            
            # Success - reset failure count
            if self.state == 'HALF_OPEN':
                self.state = 'CLOSED'
                self.failure_count = 0
                self.logger.info("Circuit breaker reset to CLOSED after successful half-open call")
            
            return {
                'success': True,
                'data': result,
                'source': 'llm',
                'circuit_state': self.state
            }
            
        except Exception as e:
            self.logger.error(f"LLM call failed: {str(e)}")
            return self._handle_failure(e)
    
    def _handle_failure(self, exception: Exception) -> Dict[str, Any]:
        """Handle LLM call failure"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == 'HALF_OPEN':
            # Failed during half-open, go back to open
            self.state = 'OPEN'
            self.logger.warning("Half-open call failed, circuit breaker returning to OPEN")
        elif self.failure_count >= self.failure_threshold:
            # Exceeded failure threshold, open the circuit
            self.state = 'OPEN'
            self.logger.error(f"Circuit breaker OPENED after {self.failure_count} failures")
        
        return self._get_fallback_response(error=str(exception))
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self.last_failure_time is None:
            return True
        return time.time() - self.last_failure_time > self.timeout
    
    def _get_fallback_response(self, error: str = None) -> Dict[str, Any]:
        """Generate fallback response when LLM is unavailable"""
        return {
            'success': False,
            'data': None,
            'source': 'fallback',
            'circuit_state': self.state,
            'error': error,
            'fallback_message': 'AI analysis temporarily unavailable. Using basic recommendations.'
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status"""
        return {
            'state': self.state,
            'failure_count': self.failure_count,
            'last_failure_time': self.last_failure_time,
            'time_until_retry': max(0, self.timeout - (time.time() - (self.last_failure_time or 0)))
        }


class LLMManager:
    """Centralized manager for all LLM operations with circuit breaker protection"""
    
    def __init__(self):
        self.circuit_breakers = {
            'music_analysis': LLMCircuitBreaker(failure_threshold=2, timeout=180),
            'recommendation': LLMCircuitBreaker(failure_threshold=3, timeout=300),
            'feedback_analysis': LLMCircuitBreaker(failure_threshold=2, timeout=120),
            'playlist_generation': LLMCircuitBreaker(failure_threshold=2, timeout=240)
        }
        self.logger = logging.getLogger(__name__)
    
    def call_music_analysis(self, llm_function: Callable, *args, **kwargs) -> Dict[str, Any]:
        """Call music analysis LLM with circuit breaker protection"""
        return self.circuit_breakers['music_analysis'].call(llm_function, *args, **kwargs)
    
    def call_recommendation(self, llm_function: Callable, *args, **kwargs) -> Dict[str, Any]:
        """Call recommendation LLM with circuit breaker protection"""
        return self.circuit_breakers['recommendation'].call(llm_function, *args, **kwargs)
    
    def call_feedback_analysis(self, llm_function: Callable, *args, **kwargs) -> Dict[str, Any]:
        """Call feedback analysis LLM with circuit breaker protection"""
        return self.circuit_breakers['feedback_analysis'].call(llm_function, *args, **kwargs)
    
    def call_playlist_generation(self, llm_function: Callable, *args, **kwargs) -> Dict[str, Any]:
        """Call playlist generation LLM with circuit breaker protection"""
        return self.circuit_breakers['playlist_generation'].call(llm_function, *args, **kwargs)
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all circuit breakers"""
        return {
            name: breaker.get_status() 
            for name, breaker in self.circuit_breakers.items()
        }
    
    def reset_circuit_breaker(self, name: str) -> bool:
        """Manually reset a circuit breaker"""
        if name in self.circuit_breakers:
            breaker = self.circuit_breakers[name]
            breaker.state = 'CLOSED'
            breaker.failure_count = 0
            breaker.last_failure_time = None
            self.logger.info(f"Manually reset circuit breaker: {name}")
            return True
        return False


# Global LLM manager instance
llm_manager = LLMManager()


def get_fallback_music_insights(spotify_client) -> Dict[str, Any]:
    """Generate basic music insights without LLM when circuit is open"""
    try:
        # Get basic data
        recent_tracks = spotify_client.get_recently_played(limit=20) or {'items': []}
        top_artists = spotify_client.get_top_artists(time_range='short_term', limit=10) or {'items': []}
        
        # Simple statistics
        track_count = len(recent_tracks.get('items', []))
        artist_count = len(top_artists.get('items', []))
        
        # Extract genres
        genres = set()
        for artist in top_artists.get('items', [])[:5]:
            genres.update(artist.get('genres', []))
        
        return {
            'user_taste_profile': f"Based on {track_count} recent tracks and {artist_count} top artists. "
                                f"Your music spans {len(genres)} genres including {', '.join(list(genres)[:3])}.",
            'recent_mood_analysis': f"You've been listening to {track_count} tracks recently, "
                                  f"showing consistent engagement with your preferred artists.",
            'analysis_ready': False,
            'source': 'fallback',
            'fallback_reason': 'AI analysis temporarily unavailable'
        }
    except Exception as e:
        current_app.logger.error(f"Fallback insights failed: {e}")
        return {
            'user_taste_profile': "Unable to analyze your music taste at the moment.",
            'recent_mood_analysis': "Music analysis is temporarily unavailable.",
            'analysis_ready': False,
            'source': 'error',
            'fallback_reason': 'Data collection failed'
        }


def get_fallback_recommendation() -> Dict[str, Any]:
    """Generate fallback recommendation when LLM is unavailable"""
    return {
        'success': False,
        'message': 'AI recommendations are temporarily unavailable. Please try again in a few minutes.',
        'fallback_suggestions': [
            'Try exploring your Discover Weekly playlist',
            'Check out similar artists to your recent favorites',
            'Browse new releases in your favorite genres'
        ],
        'source': 'fallback'
    } 