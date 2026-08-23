import os
import json
import time
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

"""
Populate Real Poster URLs for WatchWise Movie Dataset
-----------------------------------------------------
Fetches official TMDB poster_path for all movies in latest_movies_2026.csv
and saves them directly into the CSV dataset.
"""

def fetch_poster_path(movie_id):
    """Fetch poster_path for a movie_id from TMDB."""
    try:
        url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key=4cbc61374e87259f8a60796438a71b13"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            poster = data.get("poster_path")
            if poster:
                return str(movie_id), poster
    except Exception:
        pass
    return str(movie_id), None

def update_dataset_posters():
    csv_path = os.path.join("datasets", "latest_movies_2026.csv")
    if not os.path.exists(csv_path):
        print(f"File {csv_path} not found.")
        return

    df = pd.read_csv(csv_path)
    print(f"🎬 Processing posters for {len(df)} movies in {csv_path}...")
    
    movie_ids = [str(mid) for mid in df['movie_id'].tolist()]
    poster_map = {}
    
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(fetch_poster_path, mid): mid for mid in movie_ids}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Fetching Posters"):
            mid, poster = future.result()
            if poster:
                poster_map[mid] = poster

    df['poster_path'] = df['movie_id'].astype(str).map(poster_map)
    df.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"✅ Successfully updated {len(poster_map)} movie posters in {csv_path}!")

if __name__ == "__main__":
    update_dataset_posters()
