import hashlib
import json
import os
import base64
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DATABASE_FILE = os.path.join("datasets", "watchwise.db")
LEGACY_USER_DATA_FILE = os.path.join("datasets", "user_data.json")


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password, encoded):
    try:
        _, salt_text, digest_text = encoded.split("$", 2)
        salt = base64.b64decode(salt_text)
        expected = base64.b64decode(digest_text)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


class AuthManager:
    """SQLite-backed accounts, ratings, likes, and watchlists."""

    def __init__(self, database_file=DATABASE_FILE):
        os.makedirs(os.path.dirname(database_file), exist_ok=True)
        self.database_file = database_file
        self._initialize_database()
        self._import_movie_id_mapping()
        self._migrate_legacy_users()
        self.users = self._users_compatibility_view()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database_file)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize_database(self):
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    username TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS movies (
                    tmdb_id TEXT PRIMARY KEY,
                    movielens_id TEXT UNIQUE,
                    title TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ratings (
                    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    tmdb_id TEXT NOT NULL REFERENCES movies(tmdb_id) ON DELETE CASCADE,
                    rating REAL NOT NULL CHECK(rating >= 1 AND rating <= 5),
                    rated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, tmdb_id)
                );
                CREATE TABLE IF NOT EXISTS user_likes (
                    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    tmdb_id TEXT NOT NULL REFERENCES movies(tmdb_id) ON DELETE CASCADE,
                    PRIMARY KEY(user_id, tmdb_id)
                );
                CREATE TABLE IF NOT EXISTS user_dislikes (
                    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    tmdb_id TEXT NOT NULL REFERENCES movies(tmdb_id) ON DELETE CASCADE,
                    PRIMARY KEY(user_id, tmdb_id)
                );
                CREATE TABLE IF NOT EXISTS watchlist (
                    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    tmdb_id TEXT NOT NULL REFERENCES movies(tmdb_id) ON DELETE CASCADE,
                    PRIMARY KEY(user_id, tmdb_id)
                );
                CREATE INDEX IF NOT EXISTS idx_ratings_user ON ratings(user_id, rated_at DESC);
            """)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
            if "auth_provider" not in columns:
                connection.execute("ALTER TABLE users ADD COLUMN auth_provider TEXT NOT NULL DEFAULT 'password'")
            if "provider_user_id" not in columns:
                connection.execute("ALTER TABLE users ADD COLUMN provider_user_id TEXT")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_provider ON users(auth_provider, provider_user_id)")

    def _import_movie_id_mapping(self):
        mapping_file = os.path.join("datasets", "links_small.csv")
        if not os.path.exists(mapping_file):
            return
        import csv
        with self._connect() as connection, open(mapping_file, newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                if row.get("tmdbId") and row.get("movieId"):
                    connection.execute(
                        "INSERT OR IGNORE INTO movies(tmdb_id, movielens_id, title, created_at) VALUES (?, ?, ?, ?)",
                        (row["tmdbId"], row["movieId"], "", self._now()),
                    )

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _legacy_email(user_id, username):
        safe_name = hashlib.sha256(username.encode("utf-8")).hexdigest()[:12]
        return f"legacy-{user_id}-{safe_name}@watchwise.local"

    def _ensure_movie(self, connection, movie_id, title=""):
        connection.execute(
            "INSERT OR IGNORE INTO movies(tmdb_id, title, created_at) VALUES (?, ?, ?)",
            (str(movie_id), title or "", self._now()),
        )

    def _migrate_legacy_users(self):
        if not os.path.exists(LEGACY_USER_DATA_FILE):
            return
        with open(LEGACY_USER_DATA_FILE, "r", encoding="utf-8") as file:
            legacy_users = json.load(file)
        with self._connect() as connection:
            for legacy_id, legacy in legacy_users.items():
                email = self._legacy_email(str(legacy_id), legacy.get("username", "User"))
                if connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                    continue
                cursor = connection.execute(
                    "INSERT INTO users(email, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    (email, legacy.get("username", f"User {legacy_id}"), hash_password(legacy.get("password", "123")), self._now()),
                )
                user_id = cursor.lastrowid
                for movie_id, rating in legacy.get("ratings", {}).items():
                    self._ensure_movie(connection, movie_id)
                    connection.execute("INSERT OR REPLACE INTO ratings VALUES (?, ?, ?, ?)", (user_id, str(movie_id), float(rating), self._now()))
                for table, key in (("user_likes", "likes"), ("user_dislikes", "dislikes"), ("watchlist", "watchlist")):
                    for movie_id in legacy.get(key, []):
                        self._ensure_movie(connection, movie_id)
                        connection.execute(f"INSERT OR IGNORE INTO {table} VALUES (?, ?)", (user_id, str(movie_id)))

    def _users_compatibility_view(self):
        with self._connect() as connection:
            rows = connection.execute("SELECT user_id, email, username FROM users ORDER BY user_id").fetchall()
        return {str(row["user_id"]): {"username": row["username"], "email": row["email"]} for row in rows}

    def register_user(self, email, password, username=None):
        email = email.strip().lower()
        username = (username or email.split("@")[0]).strip()
        if not email or "@" not in email or len(password) < 8:
            return None, None
        try:
            with self._connect() as connection:
                cursor = connection.execute("INSERT INTO users(email, username, password_hash, created_at) VALUES (?, ?, ?, ?)", (email, username, hash_password(password), self._now()))
                user_id = str(cursor.lastrowid)
            self.users = self._users_compatibility_view()
            return user_id, self.get_user_profile(user_id)
        except sqlite3.IntegrityError:
            return None, None

    def login(self, email, password):
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
        if not row:
            return None, None
        if not verify_password(password, row["password_hash"]):
            return None, None
        return str(row["user_id"]), self.get_user_profile(row["user_id"])

    def login_oauth_user(self, email, username, provider_user_id, provider="google"):
        """Create or retrieve a local account for a verified OIDC identity."""
        email = str(email).strip().lower()
        provider_user_id = str(provider_user_id).strip()
        if not email or not provider_user_id:
            return None, None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id FROM users WHERE auth_provider = ? AND provider_user_id = ?",
                (provider, provider_user_id),
            ).fetchone()
            if row:
                user_id = row["user_id"]
            else:
                row = connection.execute("SELECT user_id FROM users WHERE email = ?", (email,)).fetchone()
                if row:
                    user_id = row["user_id"]
                    connection.execute("UPDATE users SET auth_provider = ?, provider_user_id = ? WHERE user_id = ?", (provider, provider_user_id, user_id))
                else:
                    cursor = connection.execute(
                        "INSERT INTO users(email, username, password_hash, auth_provider, provider_user_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (email, username or email.split("@")[0], "", provider, provider_user_id, self._now()),
                    )
                    user_id = cursor.lastrowid
        self.users = self._users_compatibility_view()
        return str(user_id), self.get_user_profile(user_id)

    def logout(self, user_id):
        return True

    def get_current_user(self, user_id):
        return self.get_user_profile(user_id)

    def add_user_rating(self, user_id, movie_id, rating, title=""):
        try:
            with self._connect() as connection:
                self._ensure_movie(connection, movie_id, title)
                connection.execute("INSERT OR REPLACE INTO ratings VALUES (?, ?, ?, ?)", (int(user_id), str(movie_id), float(rating), self._now()))
                if float(rating) >= 4:
                    connection.execute("INSERT OR IGNORE INTO user_likes VALUES (?, ?)", (int(user_id), str(movie_id)))
                    connection.execute("DELETE FROM user_dislikes WHERE user_id = ? AND tmdb_id = ?", (int(user_id), str(movie_id)))
                elif float(rating) <= 2:
                    connection.execute("INSERT OR IGNORE INTO user_dislikes VALUES (?, ?)", (int(user_id), str(movie_id)))
                    connection.execute("DELETE FROM user_likes WHERE user_id = ? AND tmdb_id = ?", (int(user_id), str(movie_id)))
            return True
        except (ValueError, sqlite3.IntegrityError):
            return False

    def get_ratings_history(self, user_id):
        with self._connect() as connection:
            return [dict(row) for row in connection.execute("SELECT tmdb_id AS movie_id, rating, rated_at FROM ratings WHERE user_id = ? ORDER BY rated_at DESC", (int(user_id),))]

    def get_all_ratings(self):
        with self._connect() as connection:
            return [dict(row) for row in connection.execute("SELECT user_id, tmdb_id AS movie_id, rating FROM ratings")]

    def get_rating(self, user_id, movie_id):
        with self._connect() as connection:
            row = connection.execute("SELECT rating FROM ratings WHERE user_id = ? AND tmdb_id = ?", (int(user_id), str(movie_id))).fetchone()
        return float(row["rating"]) if row else None

    def toggle_like(self, user_id, movie_id):
        return self._toggle_movie_flag(user_id, movie_id, "user_likes")

    def toggle_watchlist(self, user_id, movie_id):
        return self._toggle_movie_flag(user_id, movie_id, "watchlist")

    def _toggle_movie_flag(self, user_id, movie_id, table):
        with self._connect() as connection:
            self._ensure_movie(connection, movie_id)
            exists = connection.execute(f"SELECT 1 FROM {table} WHERE user_id = ? AND tmdb_id = ?", (int(user_id), str(movie_id))).fetchone()
            if exists:
                connection.execute(f"DELETE FROM {table} WHERE user_id = ? AND tmdb_id = ?", (int(user_id), str(movie_id)))
            else:
                connection.execute(f"INSERT INTO {table}(user_id, tmdb_id) VALUES (?, ?)", (int(user_id), str(movie_id)))
        return True

    def get_user_profile(self, user_id):
        with self._connect() as connection:
            user = connection.execute("SELECT user_id, email, username FROM users WHERE user_id = ?", (int(user_id),)).fetchone()
            if not user:
                return None
            ratings = {row["tmdb_id"]: row["rating"] for row in connection.execute("SELECT tmdb_id, rating FROM ratings WHERE user_id = ?", (int(user_id),))}
            likes = [row[0] for row in connection.execute("SELECT tmdb_id FROM user_likes WHERE user_id = ?", (int(user_id),))]
            dislikes = [row[0] for row in connection.execute("SELECT tmdb_id FROM user_dislikes WHERE user_id = ?", (int(user_id),))]
            watchlist = [row[0] for row in connection.execute("SELECT tmdb_id FROM watchlist WHERE user_id = ?", (int(user_id),))]
        return {"user_id": str(user["user_id"]), "email": user["email"], "username": user["username"], "ratings": ratings, "likes": likes, "dislikes": dislikes, "watchlist": watchlist}
