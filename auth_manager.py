import os
import json

"""
AuthManager for WatchWise Movie Recommender System
------------------------------------------------
Handles lightweight user authentication, user sessions,
and persistent tracking of ratings, likes, dislikes, and watchlists.
Supports Real-Time Preference Retraining for Logged-In Users.
"""

USER_DATA_FILE = os.path.join("datasets", "user_data.json")

DEFAULT_USERS = {
    "1": {"username": "User 1 (Action & Sci-Fi Fan)", "password": "123", "ratings": {"19995": 5.0, "285": 4.5, "206647": 5.0}, "likes": ["19995", "206647"], "dislikes": [], "watchlist": ["49026"]},
    "2": {"username": "User 2 (Drama & Romance Fan)", "password": "123", "ratings": {"9889": 5.0, "15976": 4.5, "22947": 5.0}, "likes": ["9889", "22947"], "dislikes": [], "watchlist": []},
    "3": {"username": "User 3 (Animation & Family Fan)", "password": "123", "ratings": {"10674": 5.0}, "likes": ["10674"], "dislikes": [], "watchlist": []}
}

class AuthManager:
    def __init__(self):
        os.makedirs("datasets", exist_ok=True)
        self.data_file = USER_DATA_FILE
        self.users = self._load_users()

    def _load_users(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return DEFAULT_USERS.copy()
        else:
            self._save_users(DEFAULT_USERS)
            return DEFAULT_USERS.copy()

    def _save_users(self, data):
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving user data: {e}")

    def authenticate(self, username_or_id, password=None):
        """Authenticate user by User ID or Username."""
        for uid, user in self.users.items():
            if uid == str(username_or_id) or user.get("username").lower() == str(username_or_id).lower():
                if password is None or user.get("password") == password:
                    return uid, user
        return None, None

    def register_user(self, username, password="123"):
        """Register a new user profile."""
        new_id = str(max([int(k) for k in self.users.keys() if k.isdigit()] or [0]) + 1)
        new_user = {
            "username": username,
            "password": password,
            "ratings": {},
            "likes": [],
            "dislikes": [],
            "watchlist": []
        }
        self.users[new_id] = new_user
        self._save_users(self.users)
        return new_id, new_user

    def add_user_rating(self, user_id, movie_id, rating):
        """Add or update a movie rating (1.0 to 5.0 stars) for a user."""
        user_id = str(user_id)
        movie_id = str(movie_id)
        if user_id in self.users:
            self.users[user_id]["ratings"][movie_id] = float(rating)
            if float(rating) >= 4.0 and movie_id not in self.users[user_id]["likes"]:
                self.users[user_id]["likes"].append(movie_id)
                if movie_id in self.users[user_id]["dislikes"]:
                    self.users[user_id]["dislikes"].remove(movie_id)
            elif float(rating) <= 2.0 and movie_id not in self.users[user_id]["dislikes"]:
                self.users[user_id]["dislikes"].append(movie_id)
                if movie_id in self.users[user_id]["likes"]:
                    self.users[user_id]["likes"].remove(movie_id)
            self._save_users(self.users)
            return True
        return False

    def toggle_like(self, user_id, movie_id):
        """Toggle Like status for a movie."""
        user_id = str(user_id)
        movie_id = str(movie_id)
        if user_id in self.users:
            likes = self.users[user_id]["likes"]
            if movie_id in likes:
                likes.remove(movie_id)
            else:
                likes.append(movie_id)
                if movie_id in self.users[user_id]["dislikes"]:
                    self.users[user_id]["dislikes"].remove(movie_id)
            self._save_users(self.users)
            return True
        return False

    def toggle_watchlist(self, user_id, movie_id):
        """Toggle Watchlist status for a movie."""
        user_id = str(user_id)
        movie_id = str(movie_id)
        if user_id in self.users:
            wl = self.users[user_id]["watchlist"]
            if movie_id in wl:
                wl.remove(movie_id)
            else:
                wl.append(movie_id)
            self._save_users(self.users)
            return True
        return False

    def get_user_profile(self, user_id):
        return self.users.get(str(user_id))
