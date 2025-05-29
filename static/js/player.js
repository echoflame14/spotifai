/**
 * AI Music Recommender JavaScript
 * Handles AI recommendation interactions and feedback
 */

document.addEventListener('DOMContentLoaded', function() {
    initializeAIRecommender();
});

function initializeAIRecommender() {
    console.log('%c🎵 SpotifAI Music Recommender Initialized', 'color: #1db954; font-size: 16px; font-weight: bold;');
    console.log('%cDiscover your next favorite song with AI', 'color: #b3b3b3; font-size: 12px;');
    console.log('%cAI recommendations powered by Google Gemini', 'color: #1db954; font-size: 12px;');

    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    const tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Add AI recommendation button handler
    const aiButton = document.getElementById('getRecommendation');
    if (aiButton) {
        aiButton.addEventListener('click', handleAIRecommendation);
    }
    
    // Setup playlist creation
    setupPlaylistCreation();
    
    // Setup session preferences
    setupSessionPreferences();

    // Auto-refresh current track info every 30 seconds
    if (document.querySelector('.now-playing')) {
        setInterval(refreshTrackInfo, 30000);
    }

    // Initialize progress bar animation if track is playing
    const progressBar = document.querySelector('.progress-bar');
    if (progressBar && isTrackPlaying()) {
        animateProgressBar();
    }
}

function addLoadingState(button) {
    const originalHTML = button.innerHTML;
    const loadingHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Loading...';
    
    button.innerHTML = loadingHTML;
    button.disabled = true;
    
    // Remove loading state after 2 seconds (or when page reloads)
    setTimeout(() => {
        button.innerHTML = originalHTML;
        button.disabled = false;
    }, 2000);
}

function refreshTrackInfo() {
    // This would typically fetch updated track info via AJAX
    // For now, we'll just reload the page to get fresh data
    // In a production app, you'd want to implement AJAX endpoints
    console.log('Refreshing track info...');
    
    // Check if we're still on the dashboard
    if (window.location.pathname === '/dashboard') {
        // You could implement an AJAX call here to update track info
        // without refreshing the entire page
        updateTrackInfoViaAjax();
    }
}

function updateTrackInfoViaAjax() {
    fetch('/api/current-track')
        .then(response => response.json())
        .then(data => {
            if (data.current_track && data.current_track.item) {
                const track = data.current_track.item;
                const playbackState = data.playback_state;
                
                // Update track name
                const trackNameEl = document.querySelector('.current-track h5');
                if (trackNameEl) trackNameEl.textContent = track.name;
                
                // Update artist names
                const artistEl = document.querySelector('.current-track p:first-of-type');
                if (artistEl) {
                    artistEl.textContent = track.artists.map(artist => artist.name).join(', ');
                }
                
                // Update album name
                const albumEl = document.querySelector('.current-track p.text-muted');
                if (albumEl) albumEl.textContent = track.album.name;
                
                // Update album artwork
                const imgEl = document.querySelector('.current-track img');
                if (imgEl && track.album.images && track.album.images.length > 0) {
                    imgEl.src = track.album.images[0].url;
                }
                
                // Update play/pause button
                const playPauseBtn = document.getElementById('playPauseBtn');
                const icon = playPauseBtn?.querySelector('i');
                if (icon && playbackState) {
                    icon.classList.remove('fa-play', 'fa-pause');
                    icon.classList.add(playbackState.is_playing ? 'fa-pause' : 'fa-play');
                }
                
                // Update progress bar
                if (playbackState && playbackState.progress_ms && track.duration_ms) {
                    const progressBar = document.querySelector('.progress-bar');
                    if (progressBar) {
                        const percentage = (playbackState.progress_ms / track.duration_ms) * 100;
                        progressBar.style.width = `${percentage}%`;
                    }
                }
            }
        })
        .catch(error => {
            console.error('Failed to update track info:', error);
        });
}

function isTrackPlaying() {
    // Check if there's a pause button (indicating music is playing)
    const pauseButton = document.querySelector('a[href*="/pause"]');
    return pauseButton !== null;
}

function animateProgressBar() {
    const progressBar = document.querySelector('.progress-bar');
    if (!progressBar) return;
    
    // Get current progress percentage
    const currentWidth = parseFloat(progressBar.style.width) || 0;
    
    // Animate progress bar slowly forward
    // This is a simple simulation - in a real app you'd get actual progress
    const interval = setInterval(() => {
        const newWidth = parseFloat(progressBar.style.width) || 0;
        if (newWidth < 100) {
            progressBar.style.width = (newWidth + 0.1) + '%';
        } else {
            clearInterval(interval);
        }
    }, 1000); // Update every second
    
    // Clear interval after 5 minutes to prevent memory leaks
    setTimeout(() => clearInterval(interval), 300000);
}

// Utility function to format time in MM:SS format
function formatTime(milliseconds) {
    const totalSeconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

// Toggle play/pause function for the main control button
function togglePlayPause() {
    const button = document.getElementById('playPauseBtn');
    const icon = button.querySelector('i');
    const isCurrentlyPlaying = icon.classList.contains('fa-pause');
    
    addLoadingState(button);
    
    const endpoint = isCurrentlyPlaying ? '/pause' : '/play';
    
    fetch(endpoint, { method: 'POST' })
        .then(response => {
            if (response.ok) {
                // Toggle the icon immediately for better UX
                if (isCurrentlyPlaying) {
                    icon.classList.remove('fa-pause');
                    icon.classList.add('fa-play');
                } else {
                    icon.classList.remove('fa-play');
                    icon.classList.add('fa-pause');
                }
                
                // Refresh track info after a short delay
                setTimeout(() => {
                    refreshTrackInfo();
                }, 500);
            } else {
                showNotification('Playback control failed', 'error');
            }
        })
        .catch(error => {
            console.error('Playback error:', error);
            showNotification('Playback control failed', 'error');
        })
        .finally(() => {
            button.classList.remove('loading');
            button.disabled = false;
        });
}

// Add keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Only activate shortcuts when not typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        return;
    }
    
    // Spacebar to play/pause
    if (e.code === 'Space') {
        e.preventDefault();
        const playButton = document.querySelector('a[href*="/play"]');
        const pauseButton = document.querySelector('a[href*="/pause"]');
        
        if (pauseButton) {
            pauseButton.click();
        } else if (playButton) {
            playButton.click();
        }
    }
});

// Add visual feedback for button interactions
function handlePlayPauseClick(button) {
    // Add loading state
    const originalHTML = button.innerHTML;
    button.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Loading...';
    button.disabled = true;
    
    // Determine the action based on the URL
    const action = button.href.includes('/play') ? 'play' : 'pause';
    
    // Make AJAX request
    fetch(`/${action}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    })
    .then(response => response.json())
    .then(data => {
        // Show success/error message
        showNotification(data.message, data.success ? 'success' : 'error');
        
        // Refresh page content after a short delay
        setTimeout(() => {
            window.location.reload();
        }, 1000);
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification('Failed to control playback', 'error');
    })
    .finally(() => {
        // Restore button
        button.innerHTML = originalHTML;
        button.disabled = false;
    });
}

function showNotification(message, type) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'error' ? 'danger' : 'success'} alert-dismissible fade show`;
    notification.style.position = 'fixed';
    notification.style.top = '20px';
    notification.style.right = '20px';
    notification.style.zIndex = '9999';
    notification.style.minWidth = '300px';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // Add to page
    document.body.appendChild(notification);
    
    // Auto-remove after 3 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 3000);
}

function addButtonFeedback() {
    const buttons = document.querySelectorAll('.btn');
    buttons.forEach(button => {
        button.addEventListener('mousedown', function() {
            this.style.transform = 'scale(0.95)';
        });
        
        button.addEventListener('mouseup', function() {
            this.style.transform = 'scale(1)';
        });
        
        button.addEventListener('mouseleave', function() {
            this.style.transform = 'scale(1)';
        });
    });
}

// Initialize button feedback
addButtonFeedback();

// Handle image loading errors
document.addEventListener('DOMContentLoaded', function() {
    const images = document.querySelectorAll('img[src*="spotify"], img[src*="i.scdn.co"]');
    images.forEach(img => {
        img.addEventListener('error', function() {
            // Replace broken images with placeholder
            const placeholder = this.nextElementSibling;
            if (placeholder && placeholder.classList.contains('placeholder')) {
                this.style.display = 'none';
                placeholder.style.display = 'flex';
            }
        });
    });
});

// Add smooth scrolling for sidebar
function addSmoothScrolling() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        sidebar.style.scrollBehavior = 'smooth';
    }
}

addSmoothScrolling();

// AI Recommendation Functions
function handleAIRecommendation() {
    const button = document.getElementById('getRecommendation');
    const resultDiv = document.getElementById('recommendationResult');
    const trackDiv = document.getElementById('recommendedTrack');
    
    console.log('🤖 Starting AI recommendation request...');
    
    // Show loading state
    const originalHTML = button.innerHTML;
    button.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Getting AI Recommendation...';
    button.disabled = true;
    
    // Show loading in result area
    resultDiv.style.display = 'block';
    trackDiv.innerHTML = `
        <div class="recommendation-loading">
            <div class="spinner-border" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="text-white mt-3">AI is analyzing your music taste...</p>
        </div>
    `;
    
    // Make AI recommendation request
    const customApiKey = localStorage.getItem('gemini_api_key');
    fetch('/ai-recommendation', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            session_adjustment: sessionAdjustment,
            custom_gemini_key: customApiKey
        })
    })
    .then(response => {
        console.log('📡 AI recommendation response status:', response.status);
        return response.json();
    })
    .then(data => {
        console.log('📥 AI recommendation response data:', data);
        if (data.success) {
            // Store AI interaction data globally
            lastAIData = {
                input: data.ai_input_data,
                output: data.ai_output_data,
                analysis: data.psychological_analysis
            };
            
            // Store recommendation ID for feedback
            currentRecommendationId = data.recommendation_id;
            
            displayRecommendedTrack(data.track, data.ai_reasoning);
            
            // Show and immediately load the "Why This Track?" section
            showWhyThisTrack();
            fetchTrackReasoning();
            
            // Load the "Learned from Feedback" section content
            fetchFeedbackInsights();
        } else {
            showRecommendationError(data.message);
        }
    })
    .catch(error => {
        console.error('❌ AI Recommendation Error:', error);
        showRecommendationError('Failed to get AI recommendation. Please try again.');
    })
    .finally(() => {
        // Restore button
        button.innerHTML = originalHTML;
        button.disabled = false;
    });
}

let lastAIData = null; // Store AI interaction data globally

function displayRecommendedTrack(track, reasoning) {
    const trackDiv = document.getElementById('recommendedTrack');
    
    // Stop any currently playing preview when showing new recommendation
    if (currentPreviewAudio) {
        currentPreviewAudio.pause();
        currentPreviewAudio = null;
    }
    
    console.log('AI Recommendation received:', track);
    console.log('AI Reasoning:', reasoning);
    
    trackDiv.innerHTML = `
        <div class="recommended-track-item">
            ${track.image ? `<img src="${track.image}" alt="${track.album}" class="album-cover me-3">` : 
              '<div class="album-cover-placeholder me-3"><i class="fas fa-music"></i></div>'}
            <div class="flex-grow-1">
                <h6 class="text-white mb-1">${track.name}</h6>
                <p class="text-muted mb-1">${track.artist}</p>
                <p class="text-muted small mb-0">${track.album}</p>
                <p class="text-spotify small mt-2"><i class="fas fa-robot me-1"></i>AI suggested: ${reasoning}</p>
            </div>
            <div>
                <button class="btn btn-spotify me-2" onclick="playRecommendedTrack('${track.uri}')">
                    <i class="fas fa-play me-1"></i>Play
                </button>
                <button class="btn btn-outline-secondary me-2 preview-btn" onclick="previewTrack('${track.preview_url || ''}', this)" ${!track.preview_url ? 'disabled title="No preview available"' : ''}>
                    <i class="fas fa-play-circle me-1"></i>Preview
                </button>
                <button class="btn btn-outline-light me-2" onclick="getNextRecommendation()">
                    <i class="fas fa-forward me-1"></i>Next Rec
                </button>
                <a href="${track.external_url}" target="_blank" class="btn btn-outline-spotify">
                    <i class="fab fa-spotify me-1"></i>Open in Spotify
                </a>
            </div>
        </div>
    `;
    
    // Populate AI data if available
    if (lastAIData) {
        document.getElementById('aiAnalysisData').textContent = lastAIData.analysis || 'No psychological analysis available';
        document.getElementById('aiInputData').textContent = lastAIData.input || 'No input data available';
        document.getElementById('aiOutputData').textContent = lastAIData.output || 'No output data available';
    }
    
    // Show chat feedback section
    const chatFeedback = document.getElementById('chatFeedback');
    if (chatFeedback) {
        chatFeedback.style.display = 'block';
        setupChatFeedback();
    }
}

function showRecommendationError(message) {
    const trackDiv = document.getElementById('recommendedTrack');
    
    trackDiv.innerHTML = `
        <div class="text-center py-4">
            <i class="fas fa-exclamation-triangle fa-3x text-warning mb-3"></i>
            <h6 class="text-white mb-2">Recommendation Failed</h6>
            <p class="text-muted">${message}</p>
        </div>
    `;
}

function playRecommendedTrack(trackUri) {
    const button = event.target;
    const originalHTML = button.innerHTML;
    
    button.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Playing...';
    button.disabled = true;
    
    fetch('/play-recommendation', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ track_uri: trackUri })
    })
    .then(response => response.json())
    .then(data => {
        showNotification(data.message, data.success ? 'success' : 'error');
        
        if (data.success) {
            // Just refresh the track info without reloading the page
            setTimeout(() => {
                refreshTrackInfo();
            }, 1500);
        }
    })
    .catch(error => {
        console.error('Play Error:', error);
        showNotification('Failed to play recommended track', 'error');
    })
    .finally(() => {
        button.innerHTML = originalHTML;
        button.disabled = false;
    });
}

// Store current recommendation ID for feedback and preview audio
let currentRecommendationId = null;
let currentPreviewAudio = null;

function previewTrack(previewUrl, buttonElement) {
    console.log('Preview button clicked!', { previewUrl, buttonElement });
    
    if (!previewUrl || previewUrl === '' || previewUrl === 'null') {
        console.log('No preview URL available');
        showNotification('Preview not available for this track - Spotify doesn\'t provide previews for all songs', 'info');
        return;
    }
    
    // Stop any currently playing preview
    if (currentPreviewAudio) {
        currentPreviewAudio.pause();
        currentPreviewAudio = null;
        // Reset all preview buttons
        document.querySelectorAll('.preview-btn').forEach(btn => {
            btn.innerHTML = '<i class="fas fa-play-circle me-1"></i>Preview';
            btn.classList.remove('btn-success');
            btn.classList.add('btn-outline-secondary');
        });
    }
    
    // If clicking the same button while playing, just stop
    if (buttonElement.innerHTML.includes('Stop')) {
        return;
    }
    
    try {
        // Create and play new audio
        currentPreviewAudio = new Audio(previewUrl);
        currentPreviewAudio.volume = 0.7;
        
        // Update button to show it's playing
        buttonElement.innerHTML = '<i class="fas fa-stop me-1"></i>Stop';
        buttonElement.classList.remove('btn-outline-secondary');
        buttonElement.classList.add('btn-success');
        
        // Play the audio
        currentPreviewAudio.play().then(() => {
            showNotification('Playing 30-second preview', 'info');
        }).catch(error => {
            console.error('Preview playback failed:', error);
            showNotification('Preview playback failed', 'error');
            resetPreviewButton(buttonElement);
        });
        
        // Reset button when audio ends
        currentPreviewAudio.addEventListener('ended', () => {
            resetPreviewButton(buttonElement);
            currentPreviewAudio = null;
        });
        
        // Reset button on error
        currentPreviewAudio.addEventListener('error', () => {
            showNotification('Preview failed to load', 'error');
            resetPreviewButton(buttonElement);
            currentPreviewAudio = null;
        });
        
    } catch (error) {
        console.error('Preview error:', error);
        showNotification('Preview not available', 'error');
        resetPreviewButton(buttonElement);
    }
}

function resetPreviewButton(buttonElement) {
    buttonElement.innerHTML = '<i class="fas fa-play-circle me-1"></i>Preview';
    buttonElement.classList.remove('btn-success');
    buttonElement.classList.add('btn-outline-secondary');
}

function setupChatFeedback() {
    const submitBtn = document.getElementById('submitFeedback');
    const quickPositive = document.getElementById('quickPositive');
    const quickNegative = document.getElementById('quickNegative');
    const feedbackText = document.getElementById('feedbackText');
    
    if (submitBtn) {
        submitBtn.onclick = () => submitFeedback();
    }
    
    if (quickPositive) {
        quickPositive.onclick = () => {
            feedbackText.value = "I love this recommendation! It's exactly my style.";
            submitFeedback();
        };
    }
    
    if (quickNegative) {
        quickNegative.onclick = () => {
            feedbackText.value = "This recommendation doesn't match my taste. Not my style.";
            submitFeedback();
        };
    }
}

function submitFeedback() {
    const feedbackText = document.getElementById('feedbackText');
    const statusDiv = document.getElementById('feedbackStatus');
    
    if (!feedbackText.value.trim()) {
        statusDiv.innerHTML = '<div class="alert alert-warning small mt-2">Please enter some feedback first.</div>';
        return;
    }
    
    // Show loading state
    statusDiv.innerHTML = '<div class="alert alert-info small mt-2"><i class="fas fa-spinner fa-spin me-2"></i>Processing your feedback...</div>';
    
    fetch('/chat_feedback', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            feedback_text: feedbackText.value.trim(),
            recommendation_id: currentRecommendationId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            statusDiv.innerHTML = `
                <div class="alert alert-success small mt-2">
                    <i class="fas fa-check me-2"></i>
                    Thanks for your feedback! I've analyzed it and will use these insights for better recommendations.
                    <br><small class="text-muted">Sentiment detected: ${data.sentiment}</small>
                </div>
            `;
            feedbackText.value = '';
            
            // Hide feedback section after a delay
            setTimeout(() => {
                const chatFeedback = document.getElementById('chatFeedback');
                if (chatFeedback) {
                    chatFeedback.style.display = 'none';
                }
            }, 5000);
        } else {
            statusDiv.innerHTML = `<div class="alert alert-danger small mt-2">Error: ${data.message}</div>`;
        }
    })
    .catch(error => {
        console.error('Error submitting feedback:', error);
        statusDiv.innerHTML = '<div class="alert alert-danger small mt-2">Failed to submit feedback. Please try again.</div>';
    });
}

function getNextRecommendation() {
    console.log('🔄 Getting next recommendation...');
    
    // Hide current chat feedback
    const chatFeedback = document.getElementById('chatFeedback');
    if (chatFeedback) {
        chatFeedback.style.display = 'none';
    }
    
    // Hide why this track section and clear content
    const whySection = document.getElementById('whyThisTrack');
    if (whySection) {
        whySection.style.display = 'none';
    }
    

    
    // Clear previous reasoning content
    const contentDiv = document.getElementById('trackReasoningContent');
    if (contentDiv) {
        contentDiv.innerHTML = `
            <div class="d-flex align-items-center justify-content-center py-3">
                <div class="spinner-border spinner-border-sm text-spotify me-2" role="status"></div>
                <span class="text-muted small">Analyzing why you'll love this track...</span>
            </div>
        `;
    }
    
    // Clear previous feedback insights content
    const feedbackContentDiv = document.getElementById('feedbackLearningContent');
    if (feedbackContentDiv) {
        feedbackContentDiv.innerHTML = `
            <div class="d-flex align-items-center justify-content-center py-3">
                <div class="spinner-border spinner-border-sm text-warning me-2" role="status"></div>
                <span class="text-muted small">Loading feedback insights...</span>
            </div>
        `;
    }
    
    // Reset the reasoning loaded flag
    const collapseElement = document.getElementById('trackReasoningCollapse');
    if (collapseElement) {
        collapseElement.classList.remove('reasoning-loaded');
    }
    
    // Clear feedback status
    const statusDiv = document.getElementById('feedbackStatus');
    if (statusDiv) {
        statusDiv.innerHTML = '';
    }
    
    // Trigger a new recommendation
    handleAIRecommendation();
}

// Show Why This Track section
function showWhyThisTrack() {
    const whySection = document.getElementById('whyThisTrack');
    if (whySection) {
        whySection.style.display = 'block';
        
        // Auto-expand the section to show the reasoning immediately
        const collapseElement = document.getElementById('trackReasoningCollapse');
        if (collapseElement && !collapseElement.classList.contains('show')) {
            // Use Bootstrap's collapse API to show it
            const bsCollapse = new bootstrap.Collapse(collapseElement, {
                show: true
            });
        }
    }
}

// Fetch detailed track reasoning from backend
function fetchTrackReasoning() {
    if (!currentRecommendationId) {
        console.error('No current recommendation ID available');
        return;
    }
    
    const contentDiv = document.getElementById('trackReasoningContent');
    
    fetch('/track-reasoning', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            recommendation_id: currentRecommendationId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            contentDiv.innerHTML = `
                <div class="track-reasoning-content">
                    <h6 class="text-white mb-3">
                        <i class="fas fa-lightbulb text-spotify me-2"></i>
                        Why "${data.track_info.name}" by ${data.track_info.artist}
                    </h6>
                    <div class="reasoning-text text-light" style="line-height: 1.6;">
                        ${data.reasoning.replace(/\n/g, '<br><br>')}
                    </div>
                </div>
            `;
        } else {
            contentDiv.innerHTML = `
                <div class="text-center py-3">
                    <i class="fas fa-exclamation-triangle text-warning me-2"></i>
                    <span class="text-muted">Unable to generate reasoning: ${data.message}</span>
                </div>
            `;
        }
    })
    .catch(error => {
        console.error('Error fetching track reasoning:', error);
        contentDiv.innerHTML = `
            <div class="text-center py-3">
                <i class="fas fa-exclamation-triangle text-warning me-2"></i>
                <span class="text-muted">Failed to load reasoning. Please try again.</span>
            </div>
        `;
    });
}

// Show Feedback Learning Button
function showFeedbackLearningButton() {
    const feedbackButton = document.getElementById('feedbackLearningToggle');
    if (feedbackButton) {
        feedbackButton.style.display = 'inline-block';
    }
}

// Show Learned from Feedback section
function showLearnedFeedback() {
    const learnedSection = document.getElementById('learnedFeedback');
    if (learnedSection) {
        learnedSection.style.display = 'block';
    }
}

// Fetch feedback insights from backend
function fetchFeedbackInsights() {
    const contentDiv = document.getElementById('feedbackLearningContent');
    
    fetch('/feedback-insights', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            contentDiv.innerHTML = `
                <div class="feedback-insights-content">
                    <h6 class="text-white mb-3">
                        <i class="fas fa-brain text-warning me-2"></i>
                        What I've Learned About Your Taste
                    </h6>
                    <div class="insights-text text-light" style="line-height: 1.6;">
                        ${data.insights.replace(/\n/g, '<br><br>')}
                    </div>
                    ${data.feedback_count ? `
                        <div class="mt-3">
                            <small class="text-muted">Based on ${data.feedback_count} feedback entries</small>
                        </div>
                    ` : ''}
                </div>
            `;
        } else {
            if (data.message && data.message.includes('Not authenticated')) {
                contentDiv.innerHTML = `
                    <div class="text-center py-3">
                        <i class="fas fa-sign-in-alt text-warning me-2"></i>
                        <span class="text-muted">Please refresh the page to load your feedback insights</span>
                    </div>
                `;
            } else {
                contentDiv.innerHTML = `
                    <div class="text-center py-3">
                        <i class="fas fa-info-circle text-warning me-2"></i>
                        <span class="text-muted">${data.message || 'No feedback insights available yet'}</span>
                    </div>
                `;
            }
        }
    })
    .catch(error => {
        console.error('Error fetching feedback insights:', error);
        contentDiv.innerHTML = `
            <div class="text-center py-3">
                <i class="fas fa-exclamation-triangle text-warning me-2"></i>
                <span class="text-muted">Failed to load insights. Please try again.</span>
            </div>
        `;
    });
}

// Setup feedback learning button click handler
document.addEventListener('DOMContentLoaded', function() {
    const feedbackCollapse = document.getElementById('feedbackLearningCollapse');
    
    if (feedbackCollapse) {
        feedbackCollapse.addEventListener('show.bs.collapse', function() {
            // Load feedback insights when the section is opened
            fetchFeedbackInsights();
        });
    }
});

// Session preferences functionality
let sessionAdjustment = null;

function setupSessionPreferences() {
    const applyButton = document.getElementById('applySessionAdjustment');
    const clearButton = document.getElementById('clearSessionAdjustment');
    const textArea = document.getElementById('sessionAdjustmentText');
    
    if (applyButton) {
        applyButton.addEventListener('click', function() {
            const adjustment = textArea.value.trim();
            if (adjustment) {
                applySessionAdjustment(adjustment);
            }
        });
    }
    
    if (clearButton) {
        clearButton.addEventListener('click', function() {
            clearSessionAdjustment();
        });
    }
    
    // Enable pressing Enter to apply adjustment
    if (textArea) {
        textArea.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                const adjustment = textArea.value.trim();
                if (adjustment) {
                    applySessionAdjustment(adjustment);
                }
            }
        });
    }
}

function applySessionAdjustment(adjustment) {
    sessionAdjustment = adjustment;
    
    const statusDiv = document.getElementById('sessionAdjustmentStatus');
    const messageSpan = document.getElementById('sessionAdjustmentMessage');
    
    statusDiv.style.display = 'block';
    statusDiv.className = 'alert alert-success';
    messageSpan.textContent = `Session preference applied: "${adjustment}"`;
    
    console.log('🎛️ Session adjustment applied:', adjustment);
}

function clearSessionAdjustment() {
    sessionAdjustment = null;
    
    const textArea = document.getElementById('sessionAdjustmentText');
    const statusDiv = document.getElementById('sessionAdjustmentStatus');
    
    textArea.value = '';
    statusDiv.style.display = 'none';
    
    console.log('🎛️ Session adjustment cleared');
}

function setupAISettings() {
    const saveBtn = document.getElementById('saveApiKey');
    const clearBtn = document.getElementById('clearApiKey');
    const apiKeyInput = document.getElementById('geminiApiKey');
    const currentModelSpan = document.getElementById('currentModel');
    
    // Load saved API key if exists
    const savedKey = localStorage.getItem('gemini_api_key');
    if (savedKey) {
        apiKeyInput.value = savedKey;
        currentModelSpan.textContent = 'Gemini 2.5 Flash Preview';
        clearBtn.style.display = 'inline-block';
    }
    
    saveBtn.addEventListener('click', function() {
        const apiKey = apiKeyInput.value.trim();
        if (apiKey) {
            localStorage.setItem('gemini_api_key', apiKey);
            currentModelSpan.textContent = 'Gemini 2.5 Flash Preview';
            clearBtn.style.display = 'inline-block';
            showNotification('API key saved! Using Gemini 2.5 Flash Preview', 'success');
        } else {
            showNotification('Please enter a valid API key', 'error');
        }
    });
    
    clearBtn.addEventListener('click', function() {
        localStorage.removeItem('gemini_api_key');
        apiKeyInput.value = '';
        currentModelSpan.textContent = 'Gemini 1.5 Flash';
        clearBtn.style.display = 'none';
        showNotification('API key cleared! Using default Gemini 1.5 Flash', 'info');
    });
    
    // Allow saving with Enter key
    apiKeyInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            saveBtn.click();
        }
    });
}

function setupPlaylistCreation() {
    const createPlaylistBtn = document.getElementById('createPlaylistBtn');
    const modal = document.getElementById('createPlaylistModal');
    const confirmBtn = document.getElementById('createPlaylistConfirm');
    
    if (!createPlaylistBtn || !modal || !confirmBtn) {
        console.log('Playlist creation elements not found');
        return;
    }
    
    // Show modal when button is clicked
    createPlaylistBtn.addEventListener('click', function() {
        console.log('Create playlist button clicked');
        const bootstrapModal = new bootstrap.Modal(modal);
        bootstrapModal.show();
    });
    
    // Handle playlist creation confirmation
    confirmBtn.addEventListener('click', function() {
        console.log('Create playlist confirm clicked');
        handlePlaylistCreation();
    });
    
    // Clean up when modal is hidden (for any reason)
    modal.addEventListener('hidden.bs.modal', function() {
        console.log('Modal hidden, cleaning up...');
        // Force cleanup of any remaining modal artifacts
        setTimeout(() => {
            const backdrop = document.querySelector('.modal-backdrop');
            if (backdrop) {
                backdrop.remove();
            }
            document.body.classList.remove('modal-open');
            document.body.style.overflow = '';
            document.body.style.paddingRight = '';
        }, 50);
    });
}

function handlePlaylistCreation() {
    const playlistName = document.getElementById('playlistName').value.trim() || 'AI Generated Playlist';
    const playlistDescription = document.getElementById('playlistDescription').value.trim() || 'A personalized playlist created by AI based on your music taste';
    const songCount = parseInt(document.getElementById('songCount').value);
    const useSessionAdjustment = document.getElementById('useSessionAdjustment').checked;
    const customApiKey = localStorage.getItem('gemini_api_key');
    
    console.log('Creating playlist:', { playlistName, songCount, useSessionAdjustment });
    
    if (!customApiKey) {
        showNotification('Please add your Gemini API key in AI Settings to create playlists', 'error');
        return;
    }
    
    // Show loading state
    const confirmBtn = document.getElementById('createPlaylistConfirm');
    const originalText = confirmBtn.innerHTML;
    confirmBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Creating Playlist...';
    confirmBtn.disabled = true;
    
    // Make API request to create playlist
    fetch('/create-ai-playlist', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            name: playlistName,
            description: playlistDescription,
            song_count: songCount,
            use_session_adjustment: useSessionAdjustment,
            custom_gemini_key: customApiKey
        })
    })
    .then(response => response.json())
    .then(data => {
        console.log('Playlist creation response:', data);
        
        if (data.success) {
            showNotification(`Successfully created playlist "${data.playlist_name}" with ${data.tracks_added} songs!`, 'success');
            // Close modal properly
            const modalElement = document.getElementById('createPlaylistModal');
            const modal = bootstrap.Modal.getInstance(modalElement);
            if (modal) {
                modal.hide();
            }
            
            // Clean up any remaining backdrop
            setTimeout(() => {
                const backdrop = document.querySelector('.modal-backdrop');
                if (backdrop) {
                    backdrop.remove();
                }
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
                document.body.style.paddingRight = '';
            }, 150);
            
            // Reset form
            document.getElementById('playlistName').value = '';
            document.getElementById('playlistDescription').value = '';
        } else {
            showNotification(`Failed to create playlist: ${data.message}`, 'error');
        }
    })
    .catch(error => {
        console.error('Error creating playlist:', error);
        showNotification('Error creating playlist. Please try again.', 'error');
    })
    .finally(() => {
        // Reset button state
        confirmBtn.innerHTML = originalText;
        confirmBtn.disabled = false;
    });
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    initializeAIRecommender();
    setupChatFeedback();
    setupSessionPreferences();
    setupAISettings();
    addButtonFeedback();
    addSmoothScrolling();
});

// Console welcome message
console.log('%c🎵 Spotify Clone Player Initialized', 'color: #1db954; font-size: 16px; font-weight: bold;');
console.log('%cUse spacebar to play/pause music', 'color: #b3b3b3; font-size: 12px;');
console.log('%cAI recommendations powered by Google Gemini', 'color: #1db954; font-size: 12px;');
