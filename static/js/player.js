/**
 * AI Music Recommender JavaScript
 * Handles AI recommendation interactions and feedback
 */

let isInitialized = false;
let sessionAdjustment = null;

// Custom logging function with truncation
function log(message, level = 'info') {
    const MAX_LENGTH = 100;
    let truncatedMessage = message;
    let lineCount = 1;
    
    if (typeof message === 'string') {
        // Count lines
        lineCount = (message.match(/\n/g) || []).length + 1;
        
        // Truncate if too long
        if (message.length > MAX_LENGTH) {
            truncatedMessage = `${message.substring(0, MAX_LENGTH)}... [truncated, total length: ${message.length} chars, lines: ${lineCount}]`;
        }
    } else if (typeof message === 'object') {
        try {
            const stringified = JSON.stringify(message);
            if (stringified.length > MAX_LENGTH) {
                truncatedMessage = `${stringified.substring(0, MAX_LENGTH)}... [truncated, total length: ${stringified.length} chars]`;
            } else {
                truncatedMessage = stringified;
            }
        } catch (e) {
            truncatedMessage = '[Object cannot be stringified]';
        }
    }
    
    switch (level) {
        case 'error':
            console.error(truncatedMessage);
            break;
        case 'warn':
            console.warn(truncatedMessage);
            break;
        default:
            console.log(truncatedMessage);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    log('DOM Content Loaded event fired');
    log('Current initialization state:', isInitialized);
    
    if (!isInitialized) {
        log('Initializing AI Recommender...');
        try {
            initializeAIRecommender();
            setupChatFeedback();
            setupSessionPreferences();
            setupAISettings();
            setupPlaylistCreation();
            addButtonFeedback();
            addSmoothScrolling();
            log('All initialization functions completed');
            
            // Show Lightning mode (hyper fast) status
            log('⚡ LIGHTNING MODE (HYPER FAST) ACTIVE - Ultra-fast recommendations enabled!');
            setTimeout(() => {
                showNotification('⚡ Lightning Mode Active - Hyper fast recommendations enabled!', 'success');
            }, 2000);
        } catch (error) {
            log('Error during initialization: ' + error.message, 'error');
        }
    } else {
        log('AI Recommender already initialized, skipping initialization');
    }
});

function initializeAIRecommender() {
    log('Starting AI Recommender initialization...');
    
    if (isInitialized) {
        log('AI Recommender already initialized, returning early');
        return;
    }

    const discoverBtn = document.getElementById('getRecommendation');
    const createPlaylistBtn = document.getElementById('createPlaylistBtn');
    const feedbackLearningSection = document.getElementById('feedbackLearningSection');

    log('Found elements:', {
        discoverBtn: !!discoverBtn,
        createPlaylistBtn: !!createPlaylistBtn,
        feedbackLearningSection: !!feedbackLearningSection
    });

    if (discoverBtn) {
        log('Adding click listener to discover button');
        discoverBtn.addEventListener('click', function(e) {
            log('Discover button clicked');
            handleAIRecommendation();
        });
    } else {
        log('Discover button not found in DOM');
    }

    if (createPlaylistBtn) {
        log('Adding click listener to create playlist button');
        createPlaylistBtn.addEventListener('click', function(e) {
            log('Create playlist button clicked');
            const modal = document.getElementById('createPlaylistModal');
            if (modal) {
                log('Found create playlist modal, showing it');
                const bootstrapModal = new bootstrap.Modal(modal);
                bootstrapModal.show();
            } else {
                log('Create playlist modal not found');
            }
        });
    } else {
        log('Create playlist button not found in DOM');
    }

    if (feedbackLearningSection) {
        log('Setting up feedback learning section');
        const feedbackCollapse = document.getElementById('feedbackLearningCollapse');
        if (feedbackCollapse) {
            log('Adding collapse event listener to feedback section');
            feedbackCollapse.addEventListener('show.bs.collapse', function(e) {
                log('Feedback section expanded, fetching insights');
                fetchFeedbackInsights();
            });
        } else {
            log('Feedback collapse element not found');
        }
    } else {
        log('Feedback learning section not found in DOM');
    }

    isInitialized = true;
    log('AI Recommender initialization completed');
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
    log('Refreshing track info...');
    
    // This would typically fetch updated track info via AJAX
    // For now, we'll just reload the page to get fresh data
    // In a production app, you'd want to implement AJAX endpoints
    
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
            log('Failed to update track info:', error, 'error');
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
            log('Playback error:', error, 'error');
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
        log('Error:', error, 'error');
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
    log('Discover button clicked - initiating AI recommendation request');
    
    const discoverBtn = document.getElementById('getRecommendation');
    if (!discoverBtn) {
        log('Discover button not found in DOM', 'error');
        return;
    }

    // Add loading state
    addLoadingState(discoverBtn);
    log('Added loading state to discover button');

    // Get session adjustment if any
    const sessionAdjustment = localStorage.getItem('sessionAdjustment');
    log('Session adjustment:', sessionAdjustment || 'None');

    // Get custom Gemini API key
    const customGeminiKey = localStorage.getItem('gemini_api_key');
    log('Custom Gemini API key present:', !!customGeminiKey);

    if (!customGeminiKey) {
        showRecommendationError('Please add your Gemini API key in AI Settings to get recommendations.');
        // Remove loading state
        const currentDiscoverBtn = document.getElementById('getRecommendation');
        if (currentDiscoverBtn) {
            currentDiscoverBtn.disabled = false;
            currentDiscoverBtn.innerHTML = '<i class="fas fa-magic"></i> Discover';
            currentDiscoverBtn.classList.remove('loading');
        }
        return;
    }

    // First, check which endpoint is available via performance toggle
    fetch('/api/performance-toggle', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(perfData => {
        log('Performance toggle response:', perfData);
        
        const endpoint = perfData.endpoint || '/ai-recommendation';
        const mode = perfData.mode || 'standard';
        
        log('Using AI recommendation endpoint:', endpoint, 'mode:', mode);

        // Prepare request payload
        const payload = {
            gemini_api_key: customGeminiKey
        };

        if (sessionAdjustment) {
            payload.session_adjustment = sessionAdjustment;
            log('🎛️ Including session adjustment in request:', sessionAdjustment);
        } else {
            log('🎛️ No session adjustment to include in request');
        }

        log('Request payload prepared:', payload);

        // Make AI recommendation request
        return fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload)
        });
    })
    .then(response => {
        log('Received response from server, status:', response.status);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        log('AI recommendation response received:', data);
        
        if (data.success) {
            log('Recommendation successful:', data.track.name, 'by', data.track.artist);
            
            // Show performance banner with stats
            if (data.performance_stats) {
                showPerformanceBanner(data.performance_stats, data.performance_stats.mode || 'standard');
            }
            
            // Display the recommended track immediately with placeholder reasoning
            displayRecommendedTrack(data.track, data.ai_reasoning, data.recommendation_id);
            
            // If reasoning generation is required, start it now
            if (data.requires_reasoning_generation && data.recommendation_id) {
                log('Starting conversational reasoning generation...');
                generateConversationalReasoning(data.recommendation_id, customGeminiKey);
            }
        } else {
            log('Recommendation failed:', data.message, 'error');
            showRecommendationError(data.message || 'Failed to get recommendation');
        }
    })
    .catch(error => {
        log('AI recommendation request failed:', error.message, 'error');
        showRecommendationError('Network error: ' + error.message);
    })
    .finally(() => {
        // Remove loading state
        const currentDiscoverBtn = document.getElementById('getRecommendation');
        if (currentDiscoverBtn) {
            currentDiscoverBtn.disabled = false;
            currentDiscoverBtn.innerHTML = '<i class="fas fa-magic"></i> Discover';
            currentDiscoverBtn.classList.remove('loading');
        }
        log('Loading state removed from discover button');
    });
}

function generateConversationalReasoning(recommendationId, geminiApiKey) {
    log('Generating conversational reasoning for recommendation:', recommendationId);
    
    // Show spinner in the reasoning section
    const reasoningElement = document.querySelector('.ai-reasoning-text');
    if (reasoningElement) {
        reasoningElement.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Crafting your personalized explanation...';
    }
    
    // Make request to generate reasoning
    fetch('/api/generate-conversational-reasoning', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            recommendation_id: recommendationId,
            gemini_api_key: geminiApiKey
        })
    })
    .then(response => {
        log('Reasoning generation response status:', response.status);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        log('Reasoning generation response:', data);
        
        if (data.success) {
            log('Reasoning generated successfully in', data.generation_time + 's');
            
            // Update the reasoning text
            if (reasoningElement) {
                reasoningElement.innerHTML = data.ai_reasoning;
            }
            
            // Show a subtle notification
            showNotification('✨ Personalized explanation ready!', 'success');
        } else {
            log('Reasoning generation failed:', data.message, 'error');
            
            // Show fallback message
            if (reasoningElement) {
                reasoningElement.innerHTML = 'This track was selected based on your unique music taste and listening patterns.';
            }
        }
    })
    .catch(error => {
        log('Reasoning generation request failed:', error.message, 'error');
        
        // Show fallback message
        if (reasoningElement) {
            reasoningElement.innerHTML = 'This track was selected based on your unique music taste and listening patterns.';
        }
    });
}

function showPerformanceBanner(stats, mode) {
    // Remove existing banner if present
    const existingBanner = document.getElementById('performanceBanner');
    if (existingBanner) {
        existingBanner.remove();
    }
    
    // Create performance banner
    const banner = document.createElement('div');
    banner.id = 'performanceBanner';
    banner.className = 'alert alert-success alert-dismissible fade show mb-3';
    
    let bannerStyle, bannerContent;
    
    if (mode === 'lightning') {
        // Lightning mode styling
        bannerStyle = 'background: linear-gradient(45deg, #00ff88, #00ccff); border: none; color: white; font-weight: bold;';
        const cacheStatus = stats.cached_data ? '⚡ Cached data' : '🔄 Fresh data';
        const profileStatus = stats.cached_profile ? '🧠 Cached profile' : '🔍 New profile';
        bannerContent = `
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="font-size: 24px;">⚡</div>
                <div>
                    <strong>LIGHTNING MODE (HYPER FAST)</strong><br>
                    <small>Total: ${stats.total_duration}s | LLM: ${stats.total_llm_duration}s | Model: ${stats.model_used} | ${profileStatus} | ${cacheStatus}</small>
                </div>
                <div style="margin-left: auto; font-size: 14px;">
                    <strong>${stats.performance_gain_estimate || 'Ultra-fast!'}</strong>
                </div>
            </div>
        `;
    } else {
        // Standard mode styling
        bannerStyle = 'background: linear-gradient(45deg, #1db954, #1ed760); border: none; color: white; font-weight: bold;';
        bannerContent = `
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="font-size: 24px;">🎵</div>
                <div>
                    <strong>STANDARD AI MODE</strong><br>
                    <small>Total: ${stats.total_duration}s | Model: ${stats.model_used} | Non-optimized mode active</small>
                </div>
                <div style="margin-left: auto; font-size: 14px;">
                    <strong>Ready!</strong>
                </div>
            </div>
        `;
    }
    
    banner.style.cssText = bannerStyle;
    banner.innerHTML = `
        ${bannerContent}
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="alert"></button>
    `;
    
    // Insert banner at the top of the recommendations section
    const container = document.querySelector('.recommendation-section') || document.querySelector('.container');
    if (container && container.firstChild) {
        container.insertBefore(banner, container.firstChild);
    }
}

let lastAIData = null; // Store AI interaction data globally

function displayRecommendedTrack(track, reasoning, recommendationId) {
    log('Displaying recommended track...');
    const trackDiv = document.getElementById('recommendedTrack');
    const recommendationResult = document.getElementById('recommendationResult');
    
    if (!trackDiv || !recommendationResult) {
        log('Required elements not found:', {
            trackDiv: !!trackDiv,
            recommendationResult: !!recommendationResult
        }, 'error');
        return;
    }
    
    log('AI Recommendation received:', track);
    log('AI Reasoning:', reasoning);
    
    // Show the recommendation result section
    recommendationResult.style.display = 'block';
    
    // Set the recommendation ID on the container for the track reasoning function
    if (recommendationId) {
        recommendationResult.dataset.recommendationId = recommendationId;
        localStorage.setItem('currentRecommendationId', recommendationId);
        log('Set recommendation ID on container:', recommendationId);
        log('Stored recommendation ID in localStorage:', recommendationId);
    } else {
        log('No current recommendation ID found in localStorage', 'warn');
    }
    
    trackDiv.innerHTML = `
        <div class="recommended-track-item">
            ${track.image ? `<img src="${track.image}" alt="${track.album}" class="album-cover me-3">` : 
              '<div class="album-cover-placeholder me-3"><i class="fas fa-music"></i></div>'}
            <div class="flex-grow-1">
                <h6 class="text-white mb-1">${track.name}</h6>
                <p class="text-muted mb-1">${track.artist}</p>
                <p class="text-muted small mb-0">${track.album}</p>
                <p class="text-spotify small mt-2">
                    <i class="fas fa-robot me-1"></i>why this song?: 
                    <span class="ai-reasoning-text">${reasoning}</span>
                </p>
            </div>
            <div>
                <button class="btn btn-spotify me-2" onclick="playRecommendedTrack('${track.uri}')">
                    <i class="fas fa-play me-1"></i>Play
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
    
    log('Track display HTML updated');
    
    // Show chat feedback section
    const chatFeedback = document.getElementById('chatFeedback');
    if (chatFeedback) {
        chatFeedback.style.display = 'block';
        log('Chat feedback section displayed');
        setupChatFeedback();
    } else {
        log('Chat feedback section not found', 'error');
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
        log('Play Error:', error, 'error');
        showNotification('Failed to play recommended track', 'error');
    })
    .finally(() => {
        button.innerHTML = originalHTML;
        button.disabled = false;
    });
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
    
    // Get custom Gemini API key
    const customGeminiKey = localStorage.getItem('gemini_api_key');
    if (!customGeminiKey) {
        statusDiv.innerHTML = '<div class="alert alert-danger small mt-2">API key required for feedback analysis. Please set your Gemini API key in AI Settings.</div>';
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
            recommendation_id: localStorage.getItem('currentRecommendationId'),
            custom_gemini_key: customGeminiKey
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
        log('Error submitting feedback:', error, 'error');
        statusDiv.innerHTML = '<div class="alert alert-danger small mt-2">Failed to submit feedback. Please try again.</div>';
    });
}

function getNextRecommendation() {
    log('🔄 Getting next recommendation...');
    
    // Hide current chat feedback
    const chatFeedback = document.getElementById('chatFeedback');
    if (chatFeedback) {
        chatFeedback.style.display = 'none';
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
    
    // Clear feedback status
    const statusDiv = document.getElementById('feedbackStatus');
    if (statusDiv) {
        statusDiv.innerHTML = '';
    }
    
    // Trigger a new recommendation
    handleAIRecommendation();
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
async function fetchFeedbackInsights() {
    const contentDiv = document.getElementById('feedbackInsightsContent');
    if (!contentDiv) {
        log('Feedback insights content div not found - this is expected if the section is not visible');
        return;
    }

    // Show loading state
    contentDiv.innerHTML = `
        <div class="d-flex align-items-center justify-content-center py-4">
            <div class="spinner-border spinner-border-sm text-warning me-3" role="status"></div>
            <span class="text-muted">Analyzing your feedback patterns and generating detailed insights...</span>
        </div>
    `;

    try {
        // Check if we have a Gemini API key for AI-powered insights
        const customGeminiKey = localStorage.getItem('gemini_api_key');
        
        let response;
        if (customGeminiKey) {
            // Use POST with API key for AI-powered insights
            log('Fetching ultra-detailed AI-powered feedback insights...');
            response = await fetch('/feedback-insights', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    custom_gemini_key: customGeminiKey
                })
            });
        } else {
            // Use GET for enhanced basic insights
            log('Fetching enhanced basic feedback insights...');
            response = await fetch('/feedback-insights');
        }
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        
        if (data.insights) {
            // Enhanced formatting for ultra-detailed insights
            const insightType = data.ai_powered ? 
                '<div class="badge bg-gradient" style="background: linear-gradient(45deg, #1db954, #1ed760); color: white; font-weight: bold;"><i class="fas fa-sparkles me-1"></i>Ultra-Detailed AI Analysis</div>' : 
                '<div class="badge bg-secondary"><i class="fas fa-chart-bar me-1"></i>Enhanced Statistical Analysis</div>';
            
            // Process the insights for better formatting
            const formattedInsights = formatDetailedInsights(data.insights, data.ai_powered);
            
            contentDiv.innerHTML = `
                <div class="detailed-insights-container">
                    <div class="mb-3 d-flex align-items-center justify-content-between">
                        ${insightType}
                        <small class="text-muted"><i class="fas fa-clock me-1"></i>Updated now</small>
                    </div>
                    
                    <div class="insights-content" style="line-height: 1.6; color: #e9ecef;">
                        ${formattedInsights}
                    </div>
                    
                    ${!data.ai_powered ? `
                        <div class="mt-4 p-3 rounded" style="background: rgba(29, 185, 84, 0.1); border: 1px solid rgba(29, 185, 84, 0.3);">
                            <div class="d-flex align-items-center">
                                <i class="fas fa-info-circle text-spotify me-2"></i>
                                <small class="text-spotify">
                                    <strong>Unlock AI-Powered Insights:</strong> Add your Gemini API key in AI Settings for ultra-detailed psychological analysis, personalized recommendations, and comprehensive musical preference mapping!
                                </small>
                            </div>
                        </div>
                    ` : `
                        <div class="mt-4 p-3 rounded" style="background: rgba(29, 185, 84, 0.05); border: 1px solid rgba(29, 185, 84, 0.2);">
                            <div class="d-flex align-items-center">
                                <i class="fas fa-brain text-spotify me-2"></i>
                                <small class="text-spotify">
                                    <strong>Continuous Learning:</strong> Your feedback helps the AI understand your evolving musical taste and improve future recommendations with each interaction.
                                </small>
                            </div>
                        </div>
                    `}
                </div>
            `;
            
            log(`Ultra-detailed feedback insights loaded successfully (${data.ai_powered ? 'AI-powered' : 'enhanced basic'}) - ${data.insights.length} characters`);
        } else {
            contentDiv.innerHTML = `
                <div class="text-center py-4">
                    <div class="text-muted mb-3">
                        <i class="fas fa-music fa-2x mb-3 opacity-50"></i>
                        <h6 class="text-white">No Feedback Data Available</h6>
                        <p class="mb-0">Start providing feedback on recommendations to unlock detailed insights about your musical preferences and taste patterns!</p>
                    </div>
                    <small class="text-muted">
                        Rate songs using the feedback section after getting recommendations to begin building your personalized insight profile.
                    </small>
                </div>
            `;
        }
    } catch (error) {
        log('Error fetching feedback insights:', error, 'error');
        contentDiv.innerHTML = `
            <div class="text-center py-4">
                <div class="text-danger mb-3">
                    <i class="fas fa-exclamation-triangle fa-2x mb-3"></i>
                    <h6>Failed to Load Insights</h6>
                    <p class="mb-3">Unable to analyze your feedback patterns at this time.</p>
                    <button class="btn btn-outline-light btn-sm" onclick="fetchFeedbackInsights()">
                        <i class="fas fa-redo me-1"></i>Try Again
                    </button>
                </div>
            </div>
        `;
    }
}

function formatDetailedInsights(insights, isAIPowered) {
    // Format insights text for better visual presentation
    
    if (!insights) return insights;
    
    // If it's AI-powered insights, format as comprehensive analysis
    if (isAIPowered) {
        // Split into paragraphs and format markdown-style headers
        let formatted = insights
            // Format bold markdown-style headers
            .replace(/\*\*(.*?)\*\*/g, '<strong class="text-spotify">$1</strong>')
            // Format numbered/bullet sections
            .replace(/^(\d+\.\s*\*\*.*?\*\*:)/gm, '<h6 class="text-white mt-4 mb-2">$1</h6>')
            // Format sub-bullets with better spacing
            .replace(/^\s*-\s*(.+)/gm, '<div class="ms-3 mb-2"><i class="fas fa-angle-right text-spotify me-2"></i>$1</div>')
            // Add proper paragraph breaks
            .replace(/\n\n/g, '</p><p class="mb-3">')
            // Format specific insights sections
            .replace(/(MUSICAL TASTE PATTERNS|BEHAVIORAL & LISTENING|RECOMMENDATION SYSTEM|LEARNING INSIGHTS|PSYCHOLOGICAL MUSIC|FORWARD-LOOKING)/g, '<strong class="text-warning">$1</strong>');
        
        return `<div class="ultra-detailed-insights"><p class="mb-3">${formatted}</p></div>`;
    } else {
        // Enhanced basic insights formatting
        let formatted = insights
            // Format bold sections for enhanced basic insights
            .replace(/\*\*(.*?)\*\*/g, '<strong class="text-spotify">$1</strong>')
            // Add proper spacing between sections
            .replace(/(\.\s)([A-Z*])/g, '$1</p><p class="mb-3">$2')
            // Highlight percentages and numbers
            .replace(/(\d+\.?\d*%)/g, '<span class="text-warning fw-bold">$1</span>')
            .replace(/(\d+ out of \d+)/g, '<span class="text-info fw-bold">$1</span>')
            // Format artist names in parentheses
            .replace(/\((\d+ times?)\)/g, '<small class="text-muted">($1)</small>');
        
        return `<div class="enhanced-basic-insights"><p class="mb-3">${formatted}</p></div>`;
    }
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
    // Store in both local variable and localStorage
    sessionAdjustment = adjustment;
    localStorage.setItem('sessionAdjustment', adjustment);
    
    const statusDiv = document.getElementById('sessionAdjustmentStatus');
    const messageSpan = document.getElementById('sessionAdjustmentMessage');
    
    statusDiv.style.display = 'block';
    statusDiv.className = 'alert alert-success';
    messageSpan.textContent = `Session preference applied: "${adjustment}"`;
    
    log('🎛️ Session adjustment applied and saved to localStorage:', adjustment);
}

function clearSessionAdjustment() {
    // Clear both local variable and localStorage
    sessionAdjustment = null;
    localStorage.removeItem('sessionAdjustment');
    
    const textArea = document.getElementById('sessionAdjustmentText');
    const statusDiv = document.getElementById('sessionAdjustmentStatus');
    
    textArea.value = '';
    statusDiv.style.display = 'none';
    
    log('🎛️ Session adjustment cleared from localStorage');
}

function setupAISettings() {
    log('Setting up AI settings...');
    
    // Always ensure Lightning mode is enabled by default
    if (!localStorage.getItem('ai_performance_mode')) {
        localStorage.setItem('ai_performance_mode', 'lightning');
        log('Initialized Lightning mode to: lightning (default)');
    } else {
        log('Lightning mode setting:', localStorage.getItem('ai_performance_mode'));
    }
    
    const apiKeyInput = document.getElementById('geminiApiKey');
    const saveKeyBtn = document.getElementById('saveApiKey');
    const clearKeyBtn = document.getElementById('clearApiKey');
    
    if (!apiKeyInput || !saveKeyBtn || !clearKeyBtn) {
        log('Required AI settings elements not found:', {
            apiKeyInput: !!apiKeyInput,
            saveKeyBtn: !!saveKeyBtn,
            clearKeyBtn: !!clearKeyBtn
        }, 'warn');
        
        // Still try to setup performance toggle even if main AI settings aren't found
        setupPerformanceToggle();
        log('Lightning mode enabled by default even without full AI settings UI');
        return;
    }

    // Load saved API key
    const savedKey = localStorage.getItem('gemini_api_key');
    log('Saved API key present:', !!savedKey);
    
    if (savedKey) {
        apiKeyInput.value = savedKey;
        clearKeyBtn.style.display = 'block';
        log('Loaded saved API key');
    }

    // Handle input changes
    apiKeyInput.addEventListener('input', function() {
        log('API key input changed');
        clearKeyBtn.style.display = this.value ? 'block' : 'none';
    });

    // Handle save button click
    saveKeyBtn.addEventListener('click', function() {
        log('Save API key button clicked');
        const apiKey = apiKeyInput.value.trim();
        
        if (!apiKey) {
            log('Attempted to save empty API key', 'warn');
            showNotification('Please enter a valid API key', 'error');
            return;
        }

        try {
            localStorage.setItem('gemini_api_key', apiKey);
            log('API key saved successfully');
            showNotification('API key saved successfully', 'success');
            clearKeyBtn.style.display = 'block';
            
            // Refresh feedback insights to show AI-powered version
            setTimeout(() => {
                fetchFeedbackInsights();
                log('Refreshed feedback insights with AI capabilities');
            }, 500);
            
        } catch (error) {
            log('Failed to save API key:', error, 'error');
            showNotification('Failed to save API key', 'error');
        }
    });

    // Handle clear button click
    clearKeyBtn.addEventListener('click', function() {
        log('Clear API key button clicked');
        try {
            localStorage.removeItem('gemini_api_key');
            apiKeyInput.value = '';
            clearKeyBtn.style.display = 'none';
            log('API key cleared successfully');
            showNotification('API key cleared', 'success');
        } catch (error) {
            log('Failed to clear API key:', error, 'error');
            showNotification('Failed to clear API key', 'error');
        }
    });

    // Setup performance optimization toggle
    setupPerformanceToggle();

    log('AI settings setup completed');
}

function setupPerformanceToggle() {
    // Set Lightning mode as the only supported mode
    localStorage.setItem('ai_performance_mode', 'lightning');
    log('Lightning mode (hyper fast) is the only mode supported');
}

function loadPerformanceStats() {
    const statsText = document.getElementById('statsText');
    if (!statsText) return;
    
    fetch('/api/performance-stats')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const stats = data.stats;
                statsText.innerHTML = `
                    Cache entries: ${stats.cache_status.cached_entries} | 
                    Total recommendations: ${stats.total_recommendations} | 
                    Mode: Lightning (Hyper Fast)
                `;
            }
        })
        .catch(error => {
            log('Failed to load performance stats:', error, 'error');
            statsText.textContent = 'Performance stats unavailable';
        });
}

function setupPlaylistCreation() {
    const createPlaylistBtn = document.getElementById('createPlaylistBtn');
    const modal = document.getElementById('createPlaylistModal');
    const confirmBtn = document.getElementById('createPlaylistConfirm');
    
    if (!createPlaylistBtn || !modal || !confirmBtn) {
        log('Playlist creation elements not found');
        return;
    }
    
    // Show modal when button is clicked
    createPlaylistBtn.addEventListener('click', function() {
        log('Create playlist button clicked');
        const bootstrapModal = new bootstrap.Modal(modal);
        bootstrapModal.show();
    });
    
    // Handle playlist creation confirmation
    confirmBtn.addEventListener('click', function() {
        log('Create playlist confirm clicked');
        handlePlaylistCreation();
    });
    
    // Clean up when modal is hidden (for any reason)
    modal.addEventListener('hidden.bs.modal', function() {
        log('Modal hidden, cleaning up...');
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
    
    if (!customApiKey) {
        showNotification('Please add your Gemini API key in AI Settings to create AI playlists', 'error');
        return;
    }
    
    // Show loading state
    const confirmBtn = document.getElementById('createPlaylistConfirm');
    const originalBtnText = confirmBtn.innerHTML;
    confirmBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Creating Playlist...';
    confirmBtn.disabled = true;
    
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
        log('Playlist creation response:', data);
        
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
        log('Error creating playlist:', error, 'error');
        showNotification('Error creating playlist. Please try again.', 'error');
    })
    .finally(() => {
        // Reset button state
        confirmBtn.innerHTML = originalBtnText;
        confirmBtn.disabled = false;
    });
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    if (!isInitialized) {
        initializeAIRecommender();
        setupChatFeedback();
        setupSessionPreferences();
        setupAISettings();
        setupPlaylistCreation();
        addButtonFeedback();
        addSmoothScrolling();
        
        // Show Lightning mode (hyper fast) status
        log('⚡ LIGHTNING MODE (HYPER FAST) ACTIVE - Ultra-fast recommendations enabled!');
        setTimeout(() => {
            showNotification('⚡ Lightning Mode Active - Hyper fast recommendations enabled!', 'success');
        }, 2000);
    }
});

// Initialize session adjustment from localStorage on page load
document.addEventListener('DOMContentLoaded', function() {
    // Load session adjustment from localStorage if it exists
    const savedSessionAdjustment = localStorage.getItem('sessionAdjustment');
    if (savedSessionAdjustment) {
        sessionAdjustment = savedSessionAdjustment;
        
        // Update the UI to show the saved session adjustment
        const textArea = document.getElementById('sessionAdjustmentText');
        const statusDiv = document.getElementById('sessionAdjustmentStatus');
        const messageSpan = document.getElementById('sessionAdjustmentMessage');
        
        if (textArea) textArea.value = savedSessionAdjustment;
        if (statusDiv && messageSpan) {
            statusDiv.style.display = 'block';
            statusDiv.className = 'alert alert-success';
            messageSpan.textContent = `Session preference applied: "${savedSessionAdjustment}"`;
        }
        
        log('🎛️ Restored session adjustment from localStorage:', savedSessionAdjustment);
    }
});

// Console welcome message with debug info
log('%c🎵 Spotify Clone Player Initialized', 'color: #1db954; font-size: 16px; font-weight: bold;');
log('%cDebug Mode: Enabled', 'color: #ff6b6b; font-size: 12px;');
log('%cUse spacebar to play/pause music', 'color: #b3b3b3; font-size: 12px;');
log('%cAI recommendations powered by Google Gemini', 'color: #1db954; font-size: 12px;');
log('%cLogging Level: DEBUG', 'color: #ff6b6b; font-size: 12px;');

