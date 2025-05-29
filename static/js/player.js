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

    // Add loading states for control buttons
    const controlButtons = document.querySelectorAll('.btn-spotify, .btn-outline-spotify');
    controlButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            // Only add loading state for play/pause buttons
            if (this.href && (this.href.includes('/play') || this.href.includes('/pause'))) {
                addLoadingState(this);
            }
        });
    });

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

// Console welcome message
console.log('%c🎵 Spotify Clone Player Initialized', 'color: #1db954; font-size: 16px; font-weight: bold;');
console.log('%cUse spacebar to play/pause music', 'color: #b3b3b3; font-size: 12px;');
