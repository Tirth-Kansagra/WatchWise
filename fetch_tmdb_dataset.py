import os
import sys
import json
import time
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

"""
TMDB Dataset Fetcher for WatchWise Movie Recommender System (Robust Version)
---------------------------------------------------------------------------
Features:
 - Automatic SSL & Connection Retries with Exponential Backoff
 - Rate-limit (HTTP 429) & Connection Drop handling
 - Smart Page Allocation based on target movie count
 - Raw & Pre-processed dataset outputs for MRS.ipynb compatibility
"""

BASE_URL = "https://api.themoviedb.org/3"

def create_robust_session():
    """Create a requests Session with automatic retries and connection pooling."""
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1.5,  # Waits 1.5s, 3s, 6s... between retries
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "WatchWise-DatasetFetcher/1.0"})
    return session


def mask_url_key(url):
    """Hide API key in error messages for security."""
    import re
    return re.sub(r'api_key=[^&]+', 'api_key=***', url)


def fetch_movie_ids_by_popularity(session, api_key, target_count=5000):
    """Fetch movie IDs sorted by popularity from TMDB."""
    movie_ids = set()
    
    # Each page returns 20 movies. Calculate pages needed per endpoint.
    pages_needed = max(10, (target_count // 20) // 3 + 15)
    max_pages = min(pages_needed, 500) # TMDB limit is 500
    
    print(f"🔍 Discovering latest & popular movies across {max_pages} pages per category...")
    
    endpoints = [
        f"{BASE_URL}/movie/popular?api_key={api_key}&language=en-US&page={{page}}",
        f"{BASE_URL}/discover/movie?api_key={api_key}&language=en-US&sort_by=popularity.desc&vote_count.gte=10&page={{page}}",
        f"{BASE_URL}/discover/movie?api_key={api_key}&language=en-US&sort_by=primary_release_date.desc&vote_count.gte=5&page={{page}}"
    ]
    
    for endpoint in endpoints:
        for page in range(1, max_pages + 1):
            if len(movie_ids) >= target_count * 1.2: # Found enough IDs
                break
                
            url = endpoint.format(page=page)
            attempts = 0
            while attempts < 3:
                try:
                    res = session.get(url, timeout=12)
                    if res.status_code == 200:
                        data = res.json()
                        results = data.get("results", [])
                        if not results:
                            break
                        for movie in results:
                            if movie.get("id"):
                                movie_ids.add(movie["id"])
                        break
                    elif res.status_code == 429: # Too Many Requests
                        time.sleep(2)
                        attempts += 1
                    else:
                        break
                except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as ssl_err:
                    attempts += 1
                    time.sleep(1.5 * attempts)
                except Exception as e:
                    print(f"⚠️ Page {page} warning: {type(e).__name__}")
                    break
                    
            time.sleep(0.05) # Small rate-limit delay
                
    print(f"✅ Discovered {len(movie_ids)} unique movies!")
    return list(movie_ids)


def fetch_single_movie_details(session, api_key, movie_id):
    """Fetch complete metadata, cast, crew, and keywords for a single movie."""
    url = f"{BASE_URL}/movie/{movie_id}?api_key={api_key}&append_to_response=credits,keywords"
    
    for attempt in range(3):
        try:
            res = session.get(url, timeout=12)
            if res.status_code != 200:
                if res.status_code == 429:
                    time.sleep(2)
                    continue
                return None
                
            data = res.json()
            
            # Extract genres
            genres = [g["name"] for g in data.get("genres", [])]
            
            # Extract keywords
            keywords_data = data.get("keywords", {}).get("keywords", [])
            keywords = [k["name"] for k in keywords_data]
            
            # Extract cast (top 5)
            cast_data = data.get("credits", {}).get("cast", [])
            cast = [c["name"] for c in cast_data[:5]]
            
            # Extract director(s) from crew
            crew_data = data.get("credits", {}).get("crew", [])
            directors = [c["name"] for c in crew_data if c.get("job") == "Director"]
            
            return {
                "movie_id": data.get("id"),
                "title": data.get("title"),
                "original_title": data.get("original_title"),
                "overview": data.get("overview", ""),
                "release_date": data.get("release_date", ""),
                "popularity": data.get("popularity", 0.0),
                "vote_average": data.get("vote_average", 0.0),
                "vote_count": data.get("vote_count", 0),
                "genres": json.dumps(genres),
                "keywords": json.dumps(keywords),
                "cast": json.dumps(cast),
                "director": json.dumps(directors),
                # Raw structure compatible with tmdb_5000 / MRS.ipynb
                "raw_genres_json": json.dumps(data.get("genres", [])),
                "raw_keywords_json": json.dumps(keywords_data),
                "raw_cast_json": json.dumps([{"cast_id": c.get("cast_id"), "character": c.get("character"), "name": c.get("name")} for c in cast_data[:5]]),
                "raw_crew_json": json.dumps([{"job": c.get("job"), "name": c.get("name")} for c in crew_data if c.get("job") == "Director"])
            }
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError):
            time.sleep(1.5 * (attempt + 1))
        except Exception:
            return None
            
    return None


def fetch_dataset(api_key, target_count=5000, max_workers=6):
    """Fetch details for target_count movies concurrently using Session pool."""
    session = create_robust_session()
    
    all_movie_ids = fetch_movie_ids_by_popularity(session, api_key, target_count=target_count)
    selected_ids = all_movie_ids[:target_count]
    
    print(f"🚀 Fetching detailed metadata for {len(selected_ids)} movies using {max_workers} worker threads...")
    movies_data = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_single_movie_details, session, api_key, mid): mid for mid in selected_ids}
        
        for future in tqdm(as_completed(futures), total=len(futures), desc="Downloading metadata"):
            result = future.result()
            if result and result.get("title"):
                movies_data.append(result)
                
    df = pd.DataFrame(movies_data)
    if df.empty:
        print("❌ No movies fetched. Please verify your TMDB API key and connection.")
        return
        
    # Sort by popularity
    df.sort_values(by="popularity", ascending=False, inplace=True)
    
    # Save dataset
    os.makedirs("datasets", exist_ok=True)
    output_path = os.path.join("datasets", "latest_movies_2026.csv")
    df.to_csv(output_path, index=False, encoding="utf-8")
    
    print(f"\n🎉 Successfully created latest movie dataset!")
    print(f"📁 Saved to: {output_path}")
    print(f"📊 Rows: {df.shape[0]}, Columns: {df.shape[1]}")
    if "release_date" in df.columns:
        valid_dates = df['release_date'].dropna()
        valid_dates = valid_dates[valid_dates != ""]
        if not valid_dates.empty:
            print(f"📅 Release Range: {valid_dates.min()} to {valid_dates.max()}")
    print("\nPreview:")
    print(df[["movie_id", "title", "release_date", "popularity", "vote_average"]].head())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch latest movie dataset from TMDB API")
    parser.add_argument("--api-key", type=str, help="TMDB API Key (v3)")
    parser.add_argument("--movies-count", type=int, default=5000, help="Number of movies to fetch (default: 5000)")
    parser.add_argument("--workers", type=int, default=6, help="Concurrent HTTP worker threads (default: 6)")
    
    args = parser.parse_args()
    
    api_key = args.api_key or os.getenv("TMDB_API_KEY")
    if not api_key:
        api_key = input("🔑 Please enter your TMDB API Key: ").strip()
        
    if not api_key:
        print("❌ Error: TMDB API key is required.")
        sys.exit(1)
        
    fetch_dataset(api_key, target_count=args.movies_count, max_workers=args.workers)
