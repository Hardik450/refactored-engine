from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from typing import Optional, List, Dict
import os
import requests
import json
from time import sleep
import asyncio

app = FastAPI(title="Leaderboard API", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variable to store participants data
participants_df = None

# Configuration for external API
ANALYZE_API_URL = "https://arcadecalc-v1-backend.onrender.com/api/v1/analyzeProfile"
SOURCE_VALUE = "lsqQXcYhauLsRDp"  # You can change this in production

def fetch_profile_badges(profile_url: str, timeout: int = 30) -> Optional[int]:
    """
    Fetch totalBadges from a Google Cloud Skills Boost profile using external API
    
    Args:
        profile_url: The public profile URL
        timeout: Request timeout in seconds
    
    Returns:
        Total badges count or None if failed
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
            # Extract totalBadges from response
            # Adjust the key based on actual API response structure
            total_badges = data['data']['totalBadges']
            print(f"✅ Fetched {total_badges} badges for {profile_url}")
            return total_badges
        else:
            print(f"⚠️ API returned status {response.status_code} for {profile_url}")
            return None
            
    except requests.RequestException as e:
        print(f"❌ Failed to fetch profile {profile_url}: {e}")
        return None
    except (ValueError, KeyError) as e:
        print(f"❌ Failed to parse response for {profile_url}: {e}")
        return None

def load_csv():
    """Load participants data from CSV file"""
    global participants_df
    csv_path = "participants_with_badges.csv"
    
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    participants_df = pd.read_csv(csv_path)
    
    # Rename columns to match our API structure
    column_mapping = {
        'User Name': 'name',
        'User Email': 'email',
        'Google Cloud Skills Boost Profile URL': 'publicUrl'
    }
    participants_df.rename(columns=column_mapping, inplace=True)
    
    # Add ID column if not present
    if 'id' not in participants_df.columns:
        participants_df['id'] = range(1, len(participants_df) + 1)
    
    # Initialize totalBadges column
    if 'totalBadges' not in participants_df.columns:
        participants_df['totalBadges'] = 0
    
    # Validate required columns after mapping
    required_cols = ['id', 'name', 'email', 'publicUrl']
    missing_cols = [col for col in required_cols if col not in participants_df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns after mapping: {missing_cols}")
    
    # Ensure totalBadges are numeric
    participants_df['totalBadges'] = pd.to_numeric(participants_df['totalBadges'], errors='coerce').fillna(0)
    
    print(f"✅ Loaded {len(participants_df)} participants from CSV")

def fetch_all_badges():
    """
    Fetch badge counts for all participants from external API
    This can take a while, so it's run in the background
    """
    global participants_df
    
    if participants_df is None:
        print("⚠️ No data loaded, cannot fetch badges")
        return
    
    print(f"🔄 Starting to fetch badges for {len(participants_df)} participants...")
    
    total = len(participants_df)
    success_count = 0
    failed_count = 0
    
    for idx, row in participants_df.iterrows():
        profile_url = row['publicUrl']
        
        print(f"📡 [{idx + 1}/{total}] Fetching badges for {row['name']}...")
        
        badges = fetch_profile_badges(profile_url)
        
        if badges is not None:
            participants_df.at[idx, 'totalBadges'] = badges
            success_count += 1
            print(f"   ✅ Got {badges} badges")
        else:
            failed_count += 1
            print(f"   ❌ Failed to fetch")
        
        # Be polite - add delay to avoid rate limiting
        sleep(0.5)
    
    print(f"\n✅ Finished fetching badges!")
    print(f"   Success: {success_count}/{total}")
    print(f"   Failed: {failed_count}/{total}")

@app.on_event("startup")
async def startup_event():
    """Load CSV on application startup"""
    try:
        load_csv()
        print("💡 Tip: Use /fetch-badges endpoint to update badge counts from profiles")
    except Exception as e:
        print(f"⚠️ Warning: Could not load CSV on startup: {e}")
        print("The API will still run, but endpoints will fail until CSV is loaded.")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Leaderboard API running",
        "version": "1.0.0",
        "participants_loaded": len(participants_df) if participants_df is not None else 0
    }

@app.post("/fetch-badges")
async def fetch_badges_endpoint(background_tasks: BackgroundTasks):
    """
    Trigger fetching of badge counts from Google Cloud Skills Boost profiles
    This runs in the background and can take several minutes
    
    Returns:
        Status message
    """
    if participants_df is None:
        raise HTTPException(status_code=503, detail="Data not loaded. Please try /refresh endpoint first.")
    
    # Run in background to avoid timeout
    background_tasks.add_task(fetch_all_badges)
    
    return {
        "message": "Badge fetching started in background",
        "participants": len(participants_df),
        "note": "This may take several minutes. Use /leaderboard to check progress."
    }

@app.post("/fetch-badges-sync")
async def fetch_badges_sync():
    """
    Fetch badges synchronously (wait for all to complete)
    ⚠️ Warning: This will take a long time and may timeout for large datasets
    Use /fetch-badges (background) for better experience
    
    Returns:
        Complete results after all fetches are done
    """
    if participants_df is None:
        raise HTTPException(status_code=503, detail="Data not loaded. Please try /refresh endpoint first.")
    
    print("🔄 Starting SYNCHRONOUS badge fetch...")
    fetch_all_badges()
    
    return {
        "message": "All badges fetched successfully",
        "participants": len(participants_df),
        "total_badges": int(participants_df['totalBadges'].sum()),
        "average_badges": round(participants_df['totalBadges'].mean(), 2)
    }

@app.post("/fetch-single-badge/{participant_id}")
async def fetch_single_badge(participant_id: int):
    """
    Fetch badge count for a single participant
    
    Args:
        participant_id: The participant's ID
    
    Returns:
        Updated participant data
    """
    global participants_df
    
    if participants_df is None:
        raise HTTPException(status_code=503, detail="Data not loaded.")
    
    # Find participant by ID
    participant_idx = participants_df[participants_df['id'] == participant_id].index
    
    if len(participant_idx) == 0:
        raise HTTPException(status_code=404, detail=f"Participant with ID {participant_id} not found")
    
    idx = participant_idx[0]
    row = participants_df.iloc[idx]
    profile_url = row['publicUrl']
    
    print(f"📡 Fetching badges for {row['name']}...")
    badges = fetch_profile_badges(profile_url)
    
    if badges is not None:
        participants_df.at[idx, 'totalBadges'] = badges
        return {
            "message": "Badge count updated",
            "id": int(row['id']),
            "name": row['name'],
            "totalBadges": int(badges)
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to fetch badge count from external API")

@app.get("/leaderboard")
async def get_leaderboard(limit: int = Query(100, ge=1, le=1000)):
    """
    Get top participants sorted by totalBadges (descending)
    
    Args:
        limit: Maximum number of participants to return (default: 100)
    
    Returns:
        List of participants with rank, name, totalBadges, and publicUrl
    """
    if participants_df is None:
        raise HTTPException(status_code=503, detail="Data not loaded. Please try /refresh endpoint.")
    
    # Sort by totalBadges descending
    sorted_df = participants_df.sort_values('totalBadges', ascending=False).head(limit)
    
    # Add rank
    result = []
    for idx, row in enumerate(sorted_df.itertuples(), start=1):
        result.append({
            "rank": idx,
            "id": row.id,
            "name": row.name,
            "totalBadges": int(row.totalBadges),
            "publicUrl": row.publicUrl
        })
    
    return result

@app.get("/search")
async def search_profiles(q: str = Query(..., min_length=1)):
    """
    Search participants by name, email, or publicUrl (case-insensitive)
    
    Args:
        q: Search query string
    
    Returns:
        List of up to 20 matching participants
    """
    if participants_df is None:
        raise HTTPException(status_code=503, detail="Data not loaded. Please try /refresh endpoint.")
    
    if not q or len(q.strip()) == 0:
        return []
    
    query_lower = q.lower().strip()
    
    # Search across name, email, and publicUrl
    mask = (
        participants_df['name'].str.lower().str.contains(query_lower, na=False) |
        participants_df['email'].str.lower().str.contains(query_lower, na=False) |
        participants_df['publicUrl'].str.lower().str.contains(query_lower, na=False)
    )
    
    matches = participants_df[mask].sort_values('totalBadges', ascending=False).head(20)
    
    # Format results
    result = []
    for row in matches.itertuples():
        result.append({
            "id": row.id,
            "name": row.name,
            "email": row.email,
            "totalBadges": int(row.totalBadges),
            "publicUrl": row.publicUrl
        })
    
    return result

@app.get("/profile/{participant_id}")
async def get_profile(participant_id: int):
    """
    Get full profile data for a specific participant
    
    Args:
        participant_id: The participant's ID
    
    Returns:
        Complete participant data
    """
    if participants_df is None:
        raise HTTPException(status_code=503, detail="Data not loaded. Please try /refresh endpoint.")
    
    # Find participant by ID
    participant = participants_df[participants_df['id'] == participant_id]
    
    if len(participant) == 0:
        raise HTTPException(status_code=404, detail=f"Participant with ID {participant_id} not found")
    
    # Get the row data
    row = participant.iloc[0]
    
    # Calculate rank
    rank = (participants_df['totalBadges'] > row['totalBadges']).sum() + 1
    
    return {
        "id": int(row['id']),
        "name": row['name'],
        "email": row['email'],
        "publicUrl": row['publicUrl'],
        "totalBadges": int(row['totalBadges']),
        "rank": int(rank)
    }

@app.get("/refresh")
async def refresh_data():
    """
    Reload CSV data without restarting the server
    
    Returns:
        Status message with participant count
    """
    try:
        load_csv()
        return {
            "message": "Data refreshed successfully",
            "participants_loaded": len(participants_df),
            "note": "Use POST /fetch-badges to update badge counts"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload data: {str(e)}")

@app.get("/stats")
async def get_stats():
    """
    Get leaderboard statistics
    
    Returns:
        Statistics about participants and totalBadges
    """
    if participants_df is None:
        raise HTTPException(status_code=503, detail="Data not loaded.")
    
    return {
        "total_participants": len(participants_df),
        "total_badges": int(participants_df['totalBadges'].sum()),
        "average_badges": round(participants_df['totalBadges'].mean(), 2),
        "top_badges": int(participants_df['totalBadges'].max()),
        "lowest_badges": int(participants_df['totalBadges'].min())
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)