/**
 * Spotify Clone Player JavaScript
 * Handles interactive music controls and UI updates
 */

document.addEventListener('DOMContentLoaded', function() {
    initializePlayer();
});

function initializePlayer() {
    // Add click handlers for playlist items
    const playlistItems = document.querySelectorAll('.playlist-item');
    playlistItems.forEach(item => {
        item.addEventListener('click', function() {
            // Add visual feedback
            this.style.backgroundColor = 'var(--spotify-gray)';
            setTimeout(() => {
                this.style.backgroundColor = '';
            }, 200);
        });
    });

    // Add hover effects for playlist cards
    const playlistCards = document.querySelectorAll('.playlist-card');
    playlistCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-4px)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
        });
    });

    // Add AJAX handlers for control buttons
    const controlButtons = document.querySelectorAll('.btn-spotify, .btn-outline-spotify');
    controlButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            // Handle play/pause buttons with AJAX
            if (this.href && (this.href.includes('/play') || this.href.includes('/pause'))) {
                e.preventDefault();
                handlePlayPauseClick(this);
            }
        });
    });

    // Add AI recommendation button handler
    const aiButton = document.getElementById('getRecommendation');
    if (aiButton) {
        aiButton.addEventListener('click', handleAIRecommendation);
    }

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
    // This function would make an AJAX call to get current track info
    // Implementation depends on having AJAX endpoints in the Flask app
    console.log('Would update track info via AJAX');
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
    fetch('/ai-recommendation', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            displayRecommendedTrack(data.track, data.ai_reasoning);
        } else {
            showRecommendationError(data.message);
        }
    })
    .catch(error => {
        console.error('AI Recommendation Error:', error);
        showRecommendationError('Failed to get AI recommendation. Please try again.');
    })
    .finally(() => {
        // Restore button
        button.innerHTML = originalHTML;
        button.disabled = false;
    });
}

function displayRecommendedTrack(track, reasoning) {
    const trackDiv = document.getElementById('recommendedTrack');
    
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
                <a href="${track.external_url}" target="_blank" class="btn btn-outline-spotify">
                    <i class="fab fa-spotify me-1"></i>Open in Spotify
                </a>
            </div>
        </div>
    `;
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
            // Refresh page after a short delay to show updated now playing
            setTimeout(() => {
                window.location.reload();
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

// Console welcome message
console.log('%c🎵 Spotify Clone Player Initialized', 'color: #1db954; font-size: 16px; font-weight: bold;');
console.log('%cUse spacebar to play/pause music', 'color: #b3b3b3; font-size: 12px;');
console.log('%cAI recommendations powered by Google Gemini', 'color: #1db954; font-size: 12px;');
