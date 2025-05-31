#!/usr/bin/env python3
"""
Test script for the Spotify data cleaner
This will load the collected data and test the cleaning functions
"""

import json
import os
from spotify_data_cleaner import clean_spotify_data, extract_essential_music_context

def test_data_cleaner():
    """Test the data cleaner on collected Spotify data"""
    
    print("🧹 TESTING SPOTIFY DATA CLEANER")
    print("=" * 50)
    
    # Find the most recent data file
    data_files = [f for f in os.listdir('.') if f.startswith('spotify_data_full_') and f.endswith('.json')]
    
    if not data_files:
        print("❌ No Spotify data files found. Run test_spotify_data_collection.py first.")
        return
    
    # Get the most recent file
    latest_file = sorted(data_files)[-1]
    print(f"📁 Testing with file: {latest_file}")
    
    # Load the raw data
    with open(latest_file, 'r') as f:
        raw_data = json.load(f)
    
    print(f"📊 Raw data loaded: {len(json.dumps(raw_data)):,} characters")
    
    # Test basic cleaning
    print("\n🧹 Testing basic data cleaning...")
    cleaned_data = clean_spotify_data(raw_data)
    
    cleaned_size = len(json.dumps(cleaned_data))
    raw_size = len(json.dumps(raw_data))
    reduction = ((raw_size - cleaned_size) / raw_size) * 100
    
    print(f"✅ Basic cleaning complete:")
    print(f"   • Original: {raw_size:,} characters")
    print(f"   • Cleaned: {cleaned_size:,} characters")
    print(f"   • Reduction: {reduction:.1f}%")
    
    # Test essential context extraction
    print("\n🎯 Testing essential context extraction...")
    essential_context = extract_essential_music_context(raw_data)
    
    essential_size = len(json.dumps(essential_context))
    essential_reduction = ((raw_size - essential_size) / raw_size) * 100
    
    print(f"✅ Essential context extraction complete:")
    print(f"   • Original: {raw_size:,} characters")
    print(f"   • Essential: {essential_size:,} characters")
    print(f"   • Reduction: {essential_reduction:.1f}%")
    
    # Save cleaned data for inspection
    timestamp = latest_file.split('_')[-1].replace('.json', '')
    
    cleaned_filename = f"spotify_data_cleaned_{timestamp}.json"
    with open(cleaned_filename, 'w') as f:
        json.dump(cleaned_data, f, indent=2)
    print(f"\n💾 Cleaned data saved to: {cleaned_filename}")
    
    essential_filename = f"spotify_data_essential_{timestamp}.json"
    with open(essential_filename, 'w') as f:
        json.dump(essential_context, f, indent=2)
    print(f"💾 Essential context saved to: {essential_filename}")
    
    # Analysis summary
    print(f"\n📈 CLEANING ANALYSIS SUMMARY:")
    print(f"   • Basic cleaning reduces data by {reduction:.1f}%")
    print(f"   • Essential extraction reduces data by {essential_reduction:.1f}%")
    print(f"   • Essential context is {(essential_size / cleaned_size) * 100:.1f}% of cleaned data")
    
    # Show structure of essential context
    print(f"\n🏗️ ESSENTIAL CONTEXT STRUCTURE:")
    for key in essential_context.keys():
        if isinstance(essential_context[key], dict):
            subkeys = list(essential_context[key].keys())
            print(f"   • {key}: {subkeys}")
        elif isinstance(essential_context[key], list):
            print(f"   • {key}: [{len(essential_context[key])} items]")
        else:
            print(f"   • {key}: {type(essential_context[key]).__name__}")
    
    print(f"\n✅ Data cleaner testing complete!")
    print(f"📁 Files created:")
    print(f"   • {cleaned_filename} - Basic cleaned data")
    print(f"   • {essential_filename} - Essential context only")

if __name__ == "__main__":
    test_data_cleaner() 