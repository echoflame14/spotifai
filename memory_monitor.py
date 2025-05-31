#!/usr/bin/env python3
"""
Memory Monitor for Spotifai Application
Helps track memory usage and prevent OOM errors
"""

import psutil
import time
import logging
import os
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('memory_usage.log'),
        logging.StreamHandler()
    ]
)

def get_memory_usage():
    """Get current memory usage statistics"""
    try:
        # Get process memory info
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        # Get system memory info
        system_memory = psutil.virtual_memory()
        
        return {
            'process_memory_mb': round(memory_info.rss / 1024 / 1024, 2),
            'process_memory_percent': round(process.memory_percent(), 2),
            'system_memory_percent': system_memory.percent,
            'system_memory_available_mb': round(system_memory.available / 1024 / 1024, 2),
            'system_memory_total_mb': round(system_memory.total / 1024 / 1024, 2)
        }
    except Exception as e:
        logging.error(f"Error getting memory usage: {e}")
        return None

def log_memory_usage():
    """Log current memory usage"""
    memory_stats = get_memory_usage()
    if memory_stats:
        logging.info(
            f"Memory Usage - Process: {memory_stats['process_memory_mb']}MB "
            f"({memory_stats['process_memory_percent']}%), "
            f"System: {memory_stats['system_memory_percent']}% used, "
            f"{memory_stats['system_memory_available_mb']}MB available"
        )
        return memory_stats
    return None

def check_memory_threshold(threshold_percent=80):
    """Check if memory usage exceeds threshold"""
    memory_stats = get_memory_usage()
    if memory_stats:
        if memory_stats['system_memory_percent'] > threshold_percent:
            logging.warning(
                f"HIGH MEMORY USAGE: {memory_stats['system_memory_percent']}% "
                f"(threshold: {threshold_percent}%)"
            )
            return True
    return False

def memory_cleanup_recommendations():
    """Provide memory cleanup recommendations"""
    memory_stats = get_memory_usage()
    if not memory_stats:
        return []
    
    recommendations = []
    
    if memory_stats['system_memory_percent'] > 80:
        recommendations.append("System memory usage high - consider restarting the application")
    
    if memory_stats['process_memory_mb'] > 500:
        recommendations.append("Process memory usage high - check for memory leaks in AI processing")
    
    if memory_stats['system_memory_available_mb'] < 100:
        recommendations.append("Very low available memory - restart system or close other applications")
    
    return recommendations

def monitor_memory(duration_minutes=60, check_interval_seconds=30):
    """Monitor memory usage for a specified duration"""
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    
    logging.info(f"Starting memory monitoring for {duration_minutes} minutes")
    
    max_usage = 0
    high_usage_count = 0
    
    while time.time() < end_time:
        memory_stats = log_memory_usage()
        
        if memory_stats:
            # Track peak usage
            if memory_stats['system_memory_percent'] > max_usage:
                max_usage = memory_stats['system_memory_percent']
            
            # Check for high usage
            if check_memory_threshold(75):
                high_usage_count += 1
                
                # Log recommendations if consistently high
                if high_usage_count >= 3:
                    recommendations = memory_cleanup_recommendations()
                    for rec in recommendations:
                        logging.warning(f"RECOMMENDATION: {rec}")
                    high_usage_count = 0  # Reset counter
        
        time.sleep(check_interval_seconds)
    
    logging.info(f"Memory monitoring complete. Peak usage: {max_usage}%")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitor Spotifai application memory usage")
    parser.add_argument("--duration", type=int, default=60, help="Monitoring duration in minutes")
    parser.add_argument("--interval", type=int, default=30, help="Check interval in seconds")
    parser.add_argument("--single", action="store_true", help="Single memory check")
    
    args = parser.parse_args()
    
    if args.single:
        memory_stats = log_memory_usage()
        recommendations = memory_cleanup_recommendations()
        for rec in recommendations:
            print(f"RECOMMENDATION: {rec}")
    else:
        monitor_memory(args.duration, args.interval) 