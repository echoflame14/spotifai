"""
Feedback processing utilities.

This module handles feedback analysis and insights generation.
"""

import time
import logging
from utils.ai_analysis import configure_gemini
import google.generativeai as genai

logger = logging.getLogger(__name__)

def process_feedback_insights(feedbacks, gemini_api_key=None):
    """Process user feedback entries to generate AI-powered insights with memory optimization"""
    if not feedbacks:
        return "No feedback available yet. Start rating songs to get personalized insights!"
    
    # If no API key, fall back to enhanced basic insights
    if not gemini_api_key:
        return generate_enhanced_basic_feedback_insights(feedbacks)
    
    try:
        # Memory optimization: limit and chunk feedback processing
        max_feedbacks_to_process = min(len(feedbacks), 15)  # Reduced from 25 to prevent OOM
        chunk_size = 5  # Process 5 feedback entries at a time
        
        logger.info(f"Processing {max_feedbacks_to_process} feedback entries in chunks of {chunk_size}")
        
        # Configure Gemini
        if not configure_gemini(gemini_api_key):
            return generate_enhanced_basic_feedback_insights(feedbacks)
            
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        chunk_insights = []
        feedbacks_to_process = feedbacks[:max_feedbacks_to_process]
        
        # Process feedback in chunks to reduce memory usage
        for i in range(0, len(feedbacks_to_process), chunk_size):
            chunk = feedbacks_to_process[i:i + chunk_size]
            logger.info(f"Processing feedback chunk {i//chunk_size + 1}/{(len(feedbacks_to_process) + chunk_size - 1)//chunk_size}")
            
            # Prepare minimal feedback data for this chunk
            feedback_data = []
            for feedback in chunk:
                from models import Recommendation
                recommendation = Recommendation.query.get(feedback.recommendation_id)
                if recommendation:
                    feedback_entry = {
                        'track_name': recommendation.track_name,
                        'artist_name': recommendation.artist_name,
                        'sentiment': feedback.sentiment,
                        'feedback_text': feedback.feedback_text,
                        'was_played': recommendation.was_played,
                        'recommendation_method': recommendation.recommendation_method
                    }
                    feedback_data.append(feedback_entry)
            
            # Create concise prompt for chunk analysis
            chunk_prompt = f"""
Analyze this set of {len(feedback_data)} music feedback entries and provide key insights in 2-3 sentences:

FEEDBACK DATA:
{feedback_data}

Focus on:
- Musical preference patterns
- Recommendation performance
- Key learning points

Provide a concise summary in 150 words or less.
"""
            
            try:
                response = model.generate_content(chunk_prompt)
                if response and response.text:
                    chunk_insight = response.text.strip()
                    chunk_insights.append(chunk_insight)
                    logger.info(f"Generated chunk insight ({len(chunk_insight)} characters)")
                else:
                    logger.warning(f"No response for chunk {i//chunk_size + 1}")
            except Exception as e:
                logger.error(f"Error processing chunk {i//chunk_size + 1}: {e}")
                continue
        
        # If we have chunk insights, combine them into a final summary
        if chunk_insights:
            logger.info("Generating final comprehensive summary from chunk insights")
            
            # Create final summary prompt with reduced size
            final_prompt = f"""
Based on these individual feedback analysis chunks, create a comprehensive but concise music taste profile:

CHUNK INSIGHTS:
{chr(10).join([f"Chunk {i+1}: {insight}" for i, insight in enumerate(chunk_insights)])}

TOTAL FEEDBACK ANALYZED: {max_feedbacks_to_process} entries

Create a comprehensive analysis covering:
1. **Musical Taste Patterns**: Key preferences and patterns identified
2. **Recommendation Performance**: How well the AI is learning their taste
3. **Learning Insights**: Specific improvements and discoveries
4. **Future Directions**: Recommended musical exploration paths

Limit response to 400-500 words. Be specific but concise.
"""
            
            response = model.generate_content(final_prompt)
            if response and response.text:
                final_insights = response.text.strip()
                logger.info(f"Generated final comprehensive insights ({len(final_insights)} characters)")
                return final_insights
            else:
                logger.warning("Failed to generate final summary, combining chunk insights")
                return " ".join(chunk_insights)
        else:
            logger.warning("No chunk insights generated, using enhanced fallback")
            return generate_enhanced_basic_feedback_insights(feedbacks)
            
    except Exception as e:
        logger.error(f"Error generating AI feedback insights: {e}")
        return generate_enhanced_basic_feedback_insights(feedbacks)

def generate_enhanced_basic_feedback_insights(feedbacks):
    """Generate enhanced detailed feedback insights when AI is not available"""
    if not feedbacks:
        return "No feedback available yet. Start rating songs to get personalized insights!"
    
    # Comprehensive statistical analysis
    positive_count = sum(1 for f in feedbacks if f.sentiment and 'positive' in f.sentiment.lower())
    negative_count = sum(1 for f in feedbacks if f.sentiment and 'negative' in f.sentiment.lower())
    neutral_count = len(feedbacks) - positive_count - negative_count
    total_feedback = len(feedbacks)
    
    # Analyze artists and tracks
    artists_mentioned = {}
    tracks_with_feedback = []
    recent_feedback_trends = []
    
    for feedback in feedbacks[-10:]:  # Last 10 feedback entries
        from models import Recommendation
        recommendation = Recommendation.query.get(feedback.recommendation_id)
        if recommendation:
            artist = recommendation.artist_name
            artists_mentioned[artist] = artists_mentioned.get(artist, 0) + 1
            tracks_with_feedback.append({
                'track': recommendation.track_name,
                'artist': artist,
                'sentiment': feedback.sentiment,
                'played': recommendation.was_played
            })
            recent_feedback_trends.append(feedback.sentiment or 'neutral')
    
    # Generate comprehensive insights
    insights = []
    
    # Overall feedback patterns
    if total_feedback >= 5:
        feedback_ratio = positive_count / total_feedback
        if feedback_ratio > 0.7:
            insights.append(f"**Excellent Recommendation Success Rate**: You've expressed positive sentiment on {positive_count} out of {total_feedback} recommendations ({feedback_ratio:.1%} success rate), indicating the AI is learning your taste exceptionally well.")
        elif feedback_ratio > 0.5:
            insights.append(f"**Good Learning Progress**: With {positive_count} positive responses out of {total_feedback} total feedback entries ({feedback_ratio:.1%}), the system is steadily improving at understanding your musical preferences.")
        else:
            insights.append(f"**Calibration Phase**: The AI is still learning your unique taste profile. Out of {total_feedback} feedback entries, {positive_count} were positive, {negative_count} were negative, and {neutral_count} were neutral. This feedback is crucial for improvement.")
    
    # Artist preference analysis
    if artists_mentioned:
        favorite_artists = sorted(artists_mentioned.items(), key=lambda x: x[1], reverse=True)[:3]
        if len(favorite_artists) >= 2:
            insights.append(f"**Artist Preference Patterns**: Based on your feedback, you've engaged most with recommendations featuring {', '.join([f'{artist} ({count} times)' for artist, count in favorite_artists])}. This helps the AI understand your artist affinity patterns.")
    
    # Recent trends analysis
    if len(recent_feedback_trends) >= 5:
        recent_positive = recent_feedback_trends.count('positive')
        recent_negative = recent_feedback_trends.count('negative')
        if recent_positive > recent_negative:
            insights.append(f"**Recent Improvement Trend**: Your last {len(recent_feedback_trends)} feedback entries show {recent_positive} positive responses, suggesting the recommendation system is getting significantly better at matching your taste preferences.")
        elif recent_negative > recent_positive:
            insights.append(f"**Learning Opportunity Detected**: Your recent feedback shows {recent_negative} negative responses out of {len(recent_feedback_trends)} entries. This pattern indicates the system needs to adjust its approach to better align with your current musical preferences.")
    
    # Engagement analysis
    played_tracks = sum(1 for track in tracks_with_feedback if track['played'])
    if played_tracks > 0:
        play_rate = played_tracks / len(tracks_with_feedback)
        insights.append(f"**Listening Engagement Analysis**: You've actually played {played_tracks} out of {len(tracks_with_feedback)} recently recommended tracks ({play_rate:.1%} play rate), which provides valuable behavioral data beyond just sentiment feedback.")
    
    # Learning and improvement notes
    insights.append(f"**Comprehensive Learning Profile**: With {total_feedback} total feedback entries analyzed, the system has built a detailed preference profile including sentiment patterns, artist affinities, and listening behaviors. Each piece of feedback helps refine future recommendations to better match your evolving musical taste.")
    
    # Future recommendations guidance
    if negative_count > 0:
        insights.append(f"**Adaptive Learning Focus**: The {negative_count} negative feedback entries provide crucial information about musical directions to avoid, helping the AI eliminate unsuitable recommendation patterns and focus on styles that resonate with your preferences.")
    
    return " ".join(insights)

def generate_basic_feedback_insights(feedbacks):
    """Generate basic feedback insights when AI is not available (kept for compatibility)"""
    return generate_enhanced_basic_feedback_insights(feedbacks) 