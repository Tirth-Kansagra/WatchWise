import os
import ast
import json
import numpy as np
import pandas as pd
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel, cosine_similarity

"""
RecommenderEngine for WatchWise Movie Recommender System
--------------------------------------------------------
Supports:
 1. Content-Based Filtering (TF-IDF NLP + Cosine Similarity)
 2. Collaborative Filtering (SVD Matrix Factorization)
 3. IMDb Weighted Rating Top 250 Calculation
 4. Hybrid User-Aware Ensembling Engine (Content + Collaborative + Real-Time User Preference Retraining)
"""

def parse_json_column(val):
    """Parse JSON strings or literal lists from datasets safely."""
    if pd.isna(val) or not val:
        return []
    if isinstance(val, list):
        return val
    try:
        data = json.loads(val)
        if isinstance(data, list):
            if len(data) > 0 and isinstance(data[0], dict):
                return [d.get("name", "") for d in data if isinstance(d, dict) and d.get("name")]
            return data
    except Exception:
        pass
    try:
        data = ast.literal_eval(val)
        if isinstance(data, list):
            if len(data) > 0 and isinstance(data[0], dict):
                return [d.get("name", "") for d in data if isinstance(d, dict) and d.get("name")]
            return data
    except Exception:
        pass
    return [str(val)]


class RecommenderEngine:
    def __init__(self):
        self.movies_df = None
        self.ratings_df = None
        self.tfidf_matrix = None
        self.cosine_sim = None
        self.indices = None
        self.svd_model = None
        self.use_surprise = False
        
        self._load_and_prepare_data()
        self._build_content_model()
        self._build_collaborative_model()

    def _load_and_prepare_data(self):
        """Load datasets cleanly with fallbacks."""
        print("[DATA] Loading movie datasets for WatchWise...")
        latest_csv = os.path.join("datasets", "latest_movies_2026.csv")
        metadata_csv = os.path.join("datasets", "movies_metadata.csv")
        credits_csv = os.path.join("datasets", "credits.csv")
        keywords_csv = os.path.join("datasets", "keywords.csv")
        ratings_csv = os.path.join("datasets", "ratings_small.csv")

        # Load Movies
        if os.path.exists(latest_csv):
            df = pd.read_csv(latest_csv)
            df['movie_id'] = df['movie_id'].astype(str)
        elif os.path.exists(metadata_csv):
            df_meta = pd.read_csv(metadata_csv, low_memory=False)
            df_meta = df_meta.dropna(subset=['id', 'title'])
            df_meta = df_meta[df_meta['id'].str.isdigit()]
            df_meta['movie_id'] = df_meta['id'].astype(str)
            
            # Merge credits and keywords if available
            if os.path.exists(credits_csv):
                df_credits = pd.read_csv(credits_csv)
                df_credits['movie_id'] = df_credits['movie_id'].astype(str)
                df_meta = df_meta.merge(df_credits[['movie_id', 'cast', 'crew']], on='movie_id', how='left')
            else:
                df_meta['cast'] = '[]'
                df_meta['crew'] = '[]'

            if os.path.exists(keywords_csv):
                df_keywords = pd.read_csv(keywords_csv)
                df_keywords['id'] = df_keywords['id'].astype(str)
                df_meta = df_meta.merge(df_keywords[['id', 'keywords']], left_on='movie_id', right_on='id', how='left')
            else:
                df_meta['keywords'] = '[]'

            df = df_meta
        else:
            # Create a sample dummy dataset if no CSV is available
            df = pd.DataFrame([
                {"movie_id": "19995", "title": "Avatar", "overview": "A paraplegic Marine dispatched to the moon Pandora.", "genres": "['Action', 'Adventure', 'Fantasy', 'Science Fiction']", "keywords": "['culture clash', 'future', 'space war']", "cast": "['Sam Worthington', 'Zoe Saldana']", "director": "['James Cameron']", "release_date": "2009-12-10", "popularity": 150.4, "vote_average": 7.2, "vote_count": 11800},
                {"movie_id": "285", "title": "Pirates of the Caribbean: At World's End", "overview": "Captain Barbossa, long believed to be dead, has come back to life.", "genres": "['Adventure', 'Fantasy', 'Action']", "keywords": "['ocean', 'pirate', 'exotic island']", "cast": "['Johnny Depp', 'Orlando Bloom']", "director": "['Gore Verbinski']", "release_date": "2007-05-19", "popularity": 139.0, "vote_average": 6.9, "vote_count": 4500},
                {"movie_id": "206647", "title": "Spectre", "overview": "A cryptic message from Bond's past sends him on a trail to uncover a sinister organization.", "genres": "['Action', 'Adventure', 'Crime']", "keywords": "['spy', 'secret agent', 'mi6']", "cast": "['Daniel Craig', 'Christoph Waltz']", "director": "['Sam Mendes']", "release_date": "2015-10-26", "popularity": 107.3, "vote_average": 6.3, "vote_count": 4466},
                {"movie_id": "49026", "title": "The Dark Knight Rises", "overview": "Following the death of District Attorney Harvey Dent, Batman assumes responsibility.", "genres": "['Action', 'Crime', 'Drama', 'Thriller']", "keywords": "['dc comics', 'crime fighter', 'terrorist']", "cast": "['Christian Bale', 'Michael Caine']", "director": "['Christopher Nolan']", "release_date": "2012-07-16", "popularity": 112.3, "vote_average": 7.6, "vote_count": 9106},
                {"movie_id": "1571", "title": "Inception", "overview": "Cobb, a skilled thief who steals valuable secrets from deep within the subconscious during dream state.", "genres": "['Action', 'Science Fiction', 'Adventure']", "keywords": "['dream', 'subconscious', 'mind heist']", "cast": "['Leonardo DiCaprio', 'Joseph Gordon-Levitt']", "director": "['Christopher Nolan']", "release_date": "2010-07-15", "popularity": 167.5, "vote_average": 8.1, "vote_count": 14000}
            ])

        # Clean & Normalize Columns
        df['title'] = df['title'].fillna("Unknown Title").astype(str)
        df['overview'] = df['overview'].fillna("").astype(str)
        df['popularity'] = pd.to_numeric(df.get('popularity', 0), errors='coerce').fillna(0)
        df['vote_average'] = pd.to_numeric(df.get('vote_average', 0), errors='coerce').fillna(0)
        df['vote_count'] = pd.to_numeric(df.get('vote_count', 0), errors='coerce').fillna(0)
        df['release_date'] = df.get('release_date', '').fillna('').astype(str)
        
        # Poster URL formatting
        def format_poster(path, title):
            if path and not pd.isna(path):
                p_str = str(path).strip()
                if p_str and p_str.lower() != "nan" and p_str.lower() != "none":
                    if p_str.startswith("http"):
                        return p_str
                    elif p_str.startswith("/"):
                        return f"https://image.tmdb.org/t/p/w500{p_str}"
                    else:
                        return f"https://image.tmdb.org/t/p/w500/{p_str}"
            clean_t = str(title).replace(' ', '+')
            return f"https://placehold.co/300x450/1e1b4b/d8b4fe?text={clean_t}"

        df['poster_path'] = df.get('poster_path', None)
        df['full_poster_url'] = df.apply(lambda r: format_poster(r.get('poster_path'), r.get('title')), axis=1)

        # Parse List Columns for NLP
        df['parsed_genres'] = df['genres'].apply(parse_json_column) if 'genres' in df.columns else [[]]*len(df)
        df['parsed_keywords'] = df['keywords'].apply(parse_json_column) if 'keywords' in df.columns else [[]]*len(df)
        df['parsed_cast'] = df['cast'].apply(parse_json_column) if 'cast' in df.columns else [[]]*len(df)
        
        if 'director' in df.columns:
            df['parsed_director'] = df['director'].apply(parse_json_column)
        elif 'crew' in df.columns:
            def extract_director(crew_val):
                items = parse_json_column(crew_val)
                if isinstance(crew_val, str) and 'Director' in crew_val:
                    try:
                        c_list = ast.literal_eval(crew_val)
                        return [c['name'] for c in c_list if isinstance(c, dict) and c.get('job') == 'Director']
                    except Exception:
                        pass
                return items[:1]
            df['parsed_director'] = df['crew'].apply(extract_director)
        else:
            df['parsed_director'] = [[]]*len(df)

        # Create combined tag string for NLP vectorization
        def create_soup(row):
            genres_str = " ".join(row['parsed_genres'])
            keywords_str = " ".join(row['parsed_keywords'])
            cast_str = " ".join(row['parsed_cast'][:3])
            director_str = " ".join(row['parsed_director'])
            return f"{row['overview']} {genres_str} {keywords_str} {cast_str} {director_str}".lower()

        df['soup'] = df.apply(create_soup, axis=1)

        # Deduplicate by title
        self.movies_df = df.drop_duplicates(subset=['title']).reset_index(drop=True)
        self.indices = pd.Series(self.movies_df.index, index=self.movies_df['title'].str.lower()).to_dict()

        # Load Ratings
        if os.path.exists(ratings_csv):
            self.ratings_df = pd.read_csv(ratings_csv)
            self.ratings_df['userId'] = self.ratings_df['userId'].astype(str)
            self.ratings_df['movieId'] = self.ratings_df['movieId'].astype(str)
        else:
            self.ratings_df = pd.DataFrame([
                {"userId": "1", "movieId": "19995", "rating": 5.0},
                {"userId": "1", "movieId": "285", "rating": 4.5},
                {"userId": "2", "movieId": "9889", "rating": 5.0},
                {"userId": "3", "movieId": "10674", "rating": 5.0}
            ])

        print(f"[SUCCESS] Loaded {len(self.movies_df)} movies and {len(self.ratings_df)} user ratings.")

    def _build_content_model(self):
        """Build TF-IDF matrix and Cosine Similarity matrix for Content-Based NLP."""
        print("[NLP] Building Content-Based TF-IDF & Cosine Similarity Matrix...")
        tfidf = TfidfVectorizer(stop_words='english', max_features=10000)
        self.tfidf_matrix = tfidf.fit_transform(self.movies_df['soup'])
        self.cosine_sim = linear_kernel(self.tfidf_matrix, self.tfidf_matrix)

    def _build_collaborative_model(self):
        """Build SVD Matrix Factorization Model using scikit-surprise or fallback."""
        print("[SVD] Training Collaborative Filtering Model...")
        try:
            from surprise import SVD, Dataset, Reader
            reader = Reader(rating_scale=(1, 5))
            data = Dataset.load_from_df(self.ratings_df[['userId', 'movieId', 'rating']], reader)
            trainset = data.build_full_trainset()
            self.svd_model = SVD(n_factors=50, n_epochs=20, random_state=42)
            self.svd_model.fit(trainset)
            self.use_surprise = True
            print("[SUCCESS] Trained SVD Matrix Factorization model via Surprise.")
        except Exception as e:
            print(f"[WARNING] scikit-surprise not available ({e}). Using mean rating collaborative fallback.")
            self.use_surprise = False

    def predict_rating(self, user_id, movie_id, user_ratings=None):
        """Predict user rating for a movie (1.0 to 5.0 stars)."""
        user_id = str(user_id)
        movie_id = str(movie_id)
        
        # Check if real-time rating exists
        if user_ratings and movie_id in user_ratings:
            return float(user_ratings[movie_id])
            
        if self.use_surprise and self.svd_model:
            try:
                pred = self.svd_model.predict(user_id, movie_id)
                return float(np.clip(pred.est, 1.0, 5.0))
            except Exception:
                pass

        # Fallback to movie's vote_average or global average
        matched = self.movies_df[self.movies_df['movie_id'] == movie_id]
        if not matched.empty and matched.iloc[0]['vote_average'] > 0:
            return float(np.clip(matched.iloc[0]['vote_average'] / 2.0, 1.0, 5.0))
        return 3.5

    def get_top_ranked_movies(self, top_n=250):
        """Calculate IMDb Weighted Rating for Top N Movies (Top 10, 50, 100, 250, 500)."""
        df = self.movies_df.copy()
        v = df['vote_count']
        R = df['vote_average']
        C = R.mean() if not R.empty else 6.0
        m = v.quantile(0.50) if not v.empty else 0 # Minimum votes threshold

        qualified = df[df['vote_count'] >= m].copy()
        if qualified.empty:
            qualified = df.copy()
            m = 0

        def weighted_rating(x, m=m, C=C):
            v_val = x['vote_count']
            R_val = x['vote_average']
            if (v_val + m) == 0:
                return R_val
            return (v_val / (v_val + m) * R_val) + (m / (v_val + m) * C)

        qualified['weighted_score'] = qualified.apply(weighted_rating, axis=1)
        qualified = qualified.sort_values(by='weighted_score', ascending=False).reset_index(drop=True)
        qualified['rank'] = range(1, len(qualified) + 1)
        return qualified.head(top_n)

    def get_imdb_top_250(self, top_n=250):
        return self.get_top_ranked_movies(top_n=top_n)

    def get_top_by_genre(self, genre, top_n=50):
        """Get top ranked movies filtered by a specific genre."""
        df = self.movies_df.copy()
        if not genre or genre.lower() == "all":
            return self.get_top_ranked_movies(top_n=top_n)

        mask = df['parsed_genres'].apply(lambda g_list: any(genre.lower() in g.lower() for g in g_list))
        filtered = df[mask].copy()
        if filtered.empty:
            return pd.DataFrame()

        v = filtered['vote_count']
        R = filtered['vote_average']
        C = R.mean() if not R.empty else 6.0
        m = v.quantile(0.30) if not v.empty else 0

        def weighted_rating(x, m=m, C=C):
            v_val = x['vote_count']
            R_val = x['vote_average']
            if (v_val + m) == 0:
                return R_val
            return (v_val / (v_val + m) * R_val) + (m / (v_val + m) * C)

        filtered['weighted_score'] = filtered.apply(weighted_rating, axis=1)
        filtered = filtered.sort_values(by=['weighted_score', 'popularity'], ascending=[False, False]).reset_index(drop=True)
        filtered['rank'] = range(1, len(filtered) + 1)
        return filtered.head(top_n)

    def get_trending_now(self, top_n=20):
        """Get Trending Now movies (popular recent releases)."""
        df = self.movies_df.copy()
        if 'year' in df.columns:
            df['year_num'] = pd.to_numeric(df['year'], errors='coerce').fillna(2000)
        else:
            df['year_num'] = df['release_date'].apply(lambda x: float(str(x)[:4]) if len(str(x)) >= 4 and str(x)[:4].isdigit() else 2000.0)
            
        recent_df = df[df['year_num'] >= 2015].sort_values(by=['popularity', 'vote_average'], ascending=[False, False]).reset_index(drop=True)
        if recent_df.empty:
            recent_df = df.sort_values(by='popularity', ascending=False).reset_index(drop=True)
        recent_df['rank'] = range(1, len(recent_df) + 1)
        return recent_df.head(top_n)

    def get_most_popular(self, top_n=20):
        """Get Most Popular movies of all time based on TMDB popularity index."""
        df = self.movies_df.copy().sort_values(by='popularity', ascending=False).reset_index(drop=True)
        df['rank'] = range(1, len(df) + 1)
        return df.head(top_n)

    def get_trending_popular(self, top_n=20):
        return self.get_most_popular(top_n=top_n)

    def recommend_content(self, title, top_n=10):
        """Content-Based Recommendation: Find 10 similar movies by title."""
        title_clean = str(title).strip().lower()
        if title_clean not in self.indices:
            # Partial title match search fallback
            matches = [t for t in self.indices.keys() if title_clean in t]
            if matches:
                title_clean = matches[0]
            else:
                return pd.DataFrame()

        idx = self.indices[title_clean]
        sim_scores = list(enumerate(self.cosine_sim[idx]))
        sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)[1:top_n+1]
        
        movie_indices = [i[0] for i in sim_scores]
        results = self.movies_df.iloc[movie_indices].copy()
        results['similarity_score'] = [round(i[1] * 100, 1) for i in sim_scores]
        return results

    def multi_attribute_search(self, genre=None, director=None, actor=None, query=None, top_n=20):
        """Search movies by Genre, Director, Actor, or Keyword query."""
        df = self.movies_df.copy()
        
        if query:
            q = query.lower()
            df = df[df['title'].str.lower().str.contains(q) | df['overview'].str.lower().str.contains(q)]
        if genre and genre != "All":
            df = df[df['parsed_genres'].apply(lambda gl: any(genre.lower() in g.lower() for g in gl))]
        if director and director.strip():
            d = director.lower()
            df = df[df['parsed_director'].apply(lambda dl: any(d in dir_name.lower() for dir_name in dl))]
        if actor and actor.strip():
            a = actor.lower()
            df = df[df['parsed_cast'].apply(lambda cl: any(a in cast_name.lower() for cast_name in cl))]

        return df.sort_values(by='popularity', ascending=False).head(top_n)

    def recommend_hybrid_personalized(self, user_id=None, movie_title=None, user_profile=None, top_n=10, genre_filter=None, min_rating=0.0):
        """
        Hybrid Recommender Engine:
        Combines Content NLP Similarity + SVD Collaborative Rating + Real-Time User Likes/Dislikes & Ratings.
        User-Aware: Same movie page yields DIFFERENT recommendations for different users!
        """
        df = self.movies_df.copy()
        
        # 1. Calculate Content Similarity Base Scores
        if movie_title and str(movie_title).strip().lower() in self.indices:
            target_idx = self.indices[str(movie_title).strip().lower()]
            sim_scores = self.cosine_sim[target_idx]
            df['content_sim'] = sim_scores
        else:
            df['content_sim'] = df['popularity'] / df['popularity'].max()

        # 2. Get User Profile Interactions
        user_ratings = user_profile.get("ratings", {}) if user_profile else {}
        user_likes = user_profile.get("likes", []) if user_profile else []
        user_dislikes = user_profile.get("dislikes", []) if user_profile else []

        # 3. Calculate Collaborative & Preference Ratings
        predicted_ratings = []
        user_preference_bonuses = []

        for _, row in df.iterrows():
            mid = str(row['movie_id'])
            # SVD predicted rating (scaled 0.2 to 1.0)
            p_rating = self.predict_rating(user_id, mid, user_ratings=user_ratings)
            predicted_ratings.append(p_rating / 5.0)

            # Real-time Like / Dislike / Genre preference bonus
            bonus = 0.0
            if mid in user_likes:
                bonus += 0.25
            elif mid in user_dislikes:
                bonus -= 0.35

            # Genre affinity bonus from liked movies
            if user_likes:
                row_genres = row['parsed_genres']
                # Check if genres match user liked movies
                for liked_mid in user_likes[:5]:
                    liked_row = self.movies_df[self.movies_df['movie_id'] == liked_mid]
                    if not liked_row.empty:
                        liked_genres = liked_row.iloc[0]['parsed_genres']
                        shared = set(row_genres).intersection(set(liked_genres))
                        bonus += 0.05 * len(shared)

            user_preference_bonuses.append(bonus)

        df['collab_score'] = predicted_ratings
        df['user_bonus'] = user_preference_bonuses

        # 4. Compute Weighted Hybrid Score
        df['hybrid_score'] = (0.45 * df['content_sim']) + (0.40 * df['collab_score']) + (0.15 * df['user_bonus'])

        # Filter out input movie if specified
        if movie_title and str(movie_title).strip().lower() in self.indices:
            df = df[df['title'].str.lower() != str(movie_title).strip().lower()]

        # Apply Filters
        if genre_filter and genre_filter != "All":
            df = df[df['parsed_genres'].apply(lambda gl: any(genre_filter.lower() in g.lower() for g in gl))]
        if min_rating > 0:
            df = df[df['vote_average'] >= min_rating]

        df['predicted_user_rating'] = [round(r * 5.0, 1) for r in df['collab_score']]
        df['match_percentage'] = [round(min(100.0, max(40.0, s * 100)), 1) for s in df['hybrid_score']]

        return df.sort_values(by='hybrid_score', ascending=False).head(top_n)

    def get_movie_details(self, movie_id_or_title):
        """Fetch details for a specific movie by ID or Title."""
        val = str(movie_id_or_title).strip().lower()
        matched = self.movies_df[
            (self.movies_df['movie_id'] == val) | 
            (self.movies_df['title'].str.lower() == val)
        ]
        if not matched.empty:
            return matched.iloc[0].to_dict()
        return None

    def get_watch_providers(self, movie_id, region="IN"):
        """
        Fetch streaming/rent/buy providers for a movie via TMDB Watch Providers API.
        Returns dict with keys: 'stream', 'rent', 'buy' — each a list of
        {'provider_name': str, 'logo_url': str} dicts.
        Falls back gracefully if no API key or no data available.
        """
        api_key = os.getenv("TMDB_API_KEY", "")
        result = {"stream": [], "rent": [], "buy": [], "link": ""}

        if not api_key:
            return result

        try:
            url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers?api_key={api_key}"
            resp = requests.get(url, timeout=8)
            if resp.status_code != 200:
                return result

            data = resp.json().get("results", {})
            # Try requested region, fall back to US
            region_data = data.get(region) or data.get("US") or {}

            result["link"] = region_data.get("link", "")

            def _extract_providers(provider_list):
                out = []
                for p in (provider_list or []):
                    logo_path = p.get("logo_path", "")
                    logo_url = f"https://image.tmdb.org/t/p/w92{logo_path}" if logo_path else ""
                    out.append({
                        "provider_name": p.get("provider_name", ""),
                        "logo_url": logo_url
                    })
                return out

            result["stream"] = _extract_providers(region_data.get("flatrate"))
            result["rent"]   = _extract_providers(region_data.get("rent"))
            result["buy"]    = _extract_providers(region_data.get("buy"))
        except Exception:
            pass

        return result

    def get_backdrop_url(self, movie_id):
        """
        Fetch the backdrop image URL for a movie from TMDB.
        Returns a full URL string, or empty string on failure.
        """
        api_key = os.getenv("TMDB_API_KEY", "")
        if not api_key:
            return ""
        try:
            url = f"https://api.themoviedb.org/3/movie/{movie_id}/images?api_key={api_key}"
            resp = requests.get(url, timeout=6)
            if resp.status_code != 200:
                return ""
            backdrops = resp.json().get("backdrops", [])
            if backdrops:
                path = backdrops[0].get("file_path", "")
                if path:
                    return f"https://image.tmdb.org/t/p/w1280{path}"
        except Exception:
            pass
        return ""
