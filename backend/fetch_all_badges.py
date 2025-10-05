#!/usr/bin/env python3
"""
Standalone script to fetch all badge counts and update CSV
Run this script to fetch badges for all participants at once
"""

import pandas as pd
import requests
import json
from time import sleep
import sys

# Configuration
CSV_PATH = "participants.csv"
ANALYZE_API_URL = "https://arcadecalc-v1-backend.onrender.com/api/v1/analyzeProfile"
SOURCE_VALUE = "lsqQXcYhauLsRDp"
DELAY_SECONDS = 0.5  # Delay between API calls to avoid rate limiting

def fetch_profile_badges(profile_url: str, timeout: int = 30):
    """
    Fetch totalBadges from a Google Cloud Skills Boost profile
    """
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "source": SOURCE_VALUE,
        "Referer": "https://arcadecalc.netlify.app/"
    }
    
    payload = {"publicUrl": profile_url}
    
    try:
        response = requests.post(ANALYZE_API_URL, headers=headers, json=payload, timeout=timeout)
        
        if response.status_code == 200:
            data = response.json()
            total_badges = data['data']['totalBadges']
            return total_badges
        else:
            print(f"   ⚠️ API returned status {response.status_code}")
            return None
            
    except requests.RequestException as e:
        print(f"   ❌ Request failed: {e}")
        return None
    except (ValueError, KeyError) as e:
        print(f"   ❌ Failed to parse response: {e}")
        return None

def main():
    print("🚀 Badge Fetcher - Starting...")
    print(f"📁 Reading CSV: {CSV_PATH}")
    
    # Load CSV
    try:
        df = pd.read_csv(CSV_PATH)
    except FileNotFoundError:
        print(f"❌ Error: CSV file not found: {CSV_PATH}")
        sys.exit(1)
    
    # Rename columns
    column_mapping = {
        'User Name': 'name',
        'User Email': 'email',
        'Google Cloud Skills Boost Profile URL': 'publicUrl'
    }
    df.rename(columns=column_mapping, inplace=True)
    
    # Add ID and totalBadges columns if not present
    if 'id' not in df.columns:
        df['id'] = range(1, len(df) + 1)
    
    if 'totalBadges' not in df.columns:
        df['totalBadges'] = 0
    
    total = len(df)
    success_count = 0
    failed_count = 0
    
    print(f"📊 Found {total} participants")
    print(f"⏱️ Estimated time: ~{total * DELAY_SECONDS / 60:.1f} minutes")
    print("\n" + "="*60)
    
    # Fetch badges for each participant
    for idx, row in df.iterrows():
        profile_url = row['publicUrl']
        name = row['name']
        
        print(f"\n[{idx + 1}/{total}] {name}")
        print(f"   🔗 {profile_url}")
        
        badges = fetch_profile_badges(profile_url)
        
        if badges is not None:
            df.at[idx, 'totalBadges'] = badges
            success_count += 1
            print(f"   ✅ Fetched: {badges} badges")
        else:
            failed_count += 1
            print(f"   ❌ Failed to fetch")
        
        # Delay to avoid rate limiting
        if idx < total - 1:  # Don't delay after last item
            sleep(DELAY_SECONDS)
    
    print("\n" + "="*60)
    print("\n📈 Results Summary:")
    print(f"   ✅ Success: {success_count}/{total}")
    print(f"   ❌ Failed: {failed_count}/{total}")
    print(f"   🏅 Total badges: {int(df['totalBadges'].sum())}")
    print(f"   📊 Average badges: {df['totalBadges'].mean():.2f}")
    
    # Save updated CSV
    output_path = CSV_PATH.replace('.csv', '_with_badges.csv')
    
    # Reverse column mapping for output
    reverse_mapping = {
        'name': 'User Name',
        'email': 'User Email',
        'publicUrl': 'Google Cloud Skills Boost Profile URL'
    }
    df.rename(columns=reverse_mapping, inplace=True)
    
    # Save CSV
    df.to_csv(output_path, index=False)
    print(f"\n💾 Saved updated CSV: {output_path}")
    
    # Also save as JSON
    json_output = output_path.replace('.csv', '.json')
    df.to_json(json_output, orient='records', indent=2)
    print(f"💾 Saved JSON: {json_output}")
    
    print("\n✅ Done! You can now use the updated CSV file.")

if __name__ == "__main__":
    main()