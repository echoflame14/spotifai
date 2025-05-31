# Memory Optimization for Spotifai

## Overview
This document explains the memory optimizations implemented to prevent out-of-memory (OOM) errors in the Spotifai application, particularly when processing large feedback datasets with AI models.

## Problem
The application was experiencing OOM errors with the message:
```
[ERROR] Worker (pid:122) was sent SIGKILL! Perhaps out of memory?
```

This occurred primarily in the `process_feedback_insights` function when:
- Processing 22+ feedback entries simultaneously
- Creating very large prompts for Gemini AI
- Receiving "ultra-detailed" responses that consumed excessive memory

## Solutions Implemented

### 1. Chunked Feedback Processing
**File:** `routes.py` - `process_feedback_insights` function

**Changes:**
- Reduced maximum feedback entries from 25 to 15
- Implemented chunking: process 5 feedback entries at a time
- Generate smaller insights for each chunk, then combine into final summary
- Reduced prompt complexity and response size

**Benefits:**
- Prevents memory spikes from processing large datasets
- More stable memory usage patterns
- Graceful degradation if individual chunks fail

### 2. Optimized AI Prompts
**File:** `routes.py` - `generate_ultra_detailed_music_analysis` function

**Changes:**
- Extracted only key data points instead of full dataset
- Reduced prompt size by 80%
- Limited response to 300 words instead of 1000+
- Simplified JSON response structure

**Benefits:**
- Smaller memory footprint for prompts and responses
- Faster AI processing
- Reduced risk of hitting API limits

### 3. Gunicorn Configuration
**File:** `Procfile`

**Changes:**
```bash
# Before
web: gunicorn --bind 0.0.0.0:$PORT main:app

# After  
web: gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 --max-requests 100 --max-requests-jitter 10 main:app
```

**Benefits:**
- Reduced workers prevent memory multiplication
- Threads are more memory-efficient than processes
- Worker recycling prevents memory leaks
- Longer timeout accommodates AI processing

### 4. Memory Monitoring
**File:** `memory_monitor.py`

**Features:**
- Real-time memory usage tracking
- Automatic threshold alerts
- Memory cleanup recommendations
- Logging for debugging

**Usage:**
```bash
# Single check
python memory_monitor.py --single

# Continuous monitoring
python memory_monitor.py --duration 60 --interval 30
```

## Memory Usage Guidelines

### For Developers

1. **AI Processing:**
   - Always limit input data size
   - Use chunking for large datasets
   - Implement response size limits
   - Add timeout protection

2. **Data Handling:**
   - Avoid loading entire datasets into memory
   - Use database pagination
   - Clean up large variables after use
   - Monitor memory in development

3. **Error Handling:**
   - Always have fallback methods
   - Log memory usage before expensive operations
   - Implement graceful degradation

### For Deployment

1. **Resource Allocation:**
   - Start with at least 1GB RAM
   - Monitor peak usage and scale accordingly
   - Consider horizontal scaling for high load

2. **Monitoring:**
   - Use the memory monitor script
   - Set up alerts for high memory usage
   - Regular memory usage analysis

3. **Configuration:**
   - Adjust Gunicorn workers based on available RAM
   - Use the optimized Procfile configuration
   - Consider memory-optimized hosting plans

## Memory Optimization Checklist

### Before Deployment
- [ ] Test with realistic data volumes
- [ ] Run memory monitor during stress testing
- [ ] Verify Gunicorn configuration
- [ ] Check log files for memory warnings

### During Operation
- [ ] Monitor memory usage regularly
- [ ] Set up automated alerts
- [ ] Review memory logs weekly
- [ ] Scale resources based on usage patterns

### When Issues Occur
- [ ] Check memory monitor logs
- [ ] Reduce concurrent users temporarily
- [ ] Restart application to clear memory
- [ ] Review recent AI processing loads

## Troubleshooting

### High Memory Usage
1. Check if multiple AI operations are running simultaneously
2. Verify feedback dataset sizes
3. Review recent error logs
4. Consider reducing Gunicorn workers temporarily

### OOM Errors Persist
1. Increase server RAM
2. Reduce maximum feedback entries further
3. Implement additional chunking
4. Add more aggressive timeout limits

### Performance Impact
1. Monitor response times after optimizations
2. Adjust chunk sizes if too slow
3. Balance memory vs. processing time
4. Consider caching for frequent operations

## Future Improvements

1. **Streaming Responses:** Implement streaming for AI responses to reduce memory buffer requirements
2. **Background Processing:** Move heavy AI operations to background tasks
3. **Caching:** Cache processed insights to avoid recomputation
4. **Database Optimization:** Use database-level pagination and filtering
5. **Memory Profiling:** Implement detailed memory profiling in development

## Contact
For questions about memory optimizations or if you encounter OOM errors, please check the application logs and memory monitor output before reporting issues. 