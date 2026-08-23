import os
import streamlit as st
import pandas as pd

from auth_manager import AuthManager
from recommender_engine import RecommenderEngine

# Set Page Config
st.set_page_config(
    page_title="WatchWise - AI Movie Recommender System",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Glassmorphism Dark Theme Styling
STYLING_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }

    /* Dark Mode Glassmorphism Background */
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
        color: #f8fafc;
    }

    /* Glass Cards */
    .glass-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        transition: transform 0.3s ease, border-color 0.3s ease;
    }

    .glass-card:hover {
        transform: translateY(-4px);
        border-color: rgba(168, 85, 247, 0.4);
    }

    /* Movie Poster Cards */
    .movie-card {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 14px;
        padding: 12px;
        text-align: center;
        transition: all 0.3s ease;
        height: 100%;
    }

    .movie-card:hover {
        transform: scale(1.03);
        box-shadow: 0 10px 25px rgba(168, 85, 247, 0.3);
        border-color: #a855f7;
    }

    /* Badges */
    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        margin: 2px;
    }
    
    .badge-purple { background: rgba(168, 85, 247, 0.2); color: #d8b4fe; border: 1px solid #a855f7; }
    .badge-cyan { background: rgba(6, 182, 212, 0.2); color: #67e8f9; border: 1px solid #06b6d4; }
    .badge-amber { background: rgba(245, 158, 11, 0.2); color: #fde68a; border: 1px solid #f59e0b; }
    .badge-green { background: rgba(34, 197, 94, 0.2); color: #86efac; border: 1px solid #22c55e; }

    /* Custom Gradient Headers */
    .gradient-header {
        background: linear-gradient(90deg, #c084fc 0%, #38bdf8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
    }
    
    /* Hide Streamlit Branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
"""
st.markdown(STYLING_CSS, unsafe_allow_html=True)


# Streamlit Version Compatibility Helpers
def btn_stretch(label, key=None, type="secondary"):
    """Render a full-width button compatible with current Streamlit version."""
    try:
        return st.button(label, key=key, type=type, width="stretch")
    except TypeError:
        return st.button(label, key=key, type=type, use_container_width=True)

def img_stretch(image_src):
    """Render a full-width image compatible with current Streamlit version."""
    try:
        return st.image(image_src, width="stretch")
    except TypeError:
        return st.image(image_src, use_container_width=True)


@st.cache_resource
def load_app_services():
    auth = AuthManager()
    engine = RecommenderEngine()
    return auth, engine

auth, engine = load_app_services()

# Session State Initialization
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "selected_movie_id" not in st.session_state:
    st.session_state.selected_movie_id = None

# Sidebar Authentication & Controls
with st.sidebar:
    st.markdown("<h2 class='gradient-header'>🎬 WatchWise AI</h2>", unsafe_allow_html=True)
    st.caption("Multi-Model Movie Recommender System")
    st.divider()

    # User Profile Switcher
    if st.session_state.user_id:
        user_info = auth.get_user_profile(st.session_state.user_id)
        st.success(f"🔒 Logged In as **{user_info.get('username')}**")
        if btn_stretch("🚪 Logout"):
            st.session_state.user_id = None
            st.rerun()
    else:
        st.info("🔓 Guest Mode (Public Access)")
        st.markdown("### 🔐 User Login")
        login_option = st.selectbox("Select User Profile", options=list(auth.users.keys()), format_func=lambda uid: auth.users[uid]["username"])
        if btn_stretch("Log In Profile", type="primary"):
            st.session_state.user_id = login_option
            st.rerun()

        with st.expander("➕ Register New User"):
            new_name = st.text_input("Username")
            if st.button("Create Profile"):
                if new_name:
                    new_uid, _ = auth.register_user(new_name)
                    st.session_state.user_id = new_uid
                    st.success("Account created!")
                    st.rerun()

    st.divider()
    st.markdown("### ⚙️ Quick Filters")
    all_genres = ["All", "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary", "Drama", "Family", "Fantasy", "History", "Horror", "Music", "Mystery", "Romance", "Science Fiction", "TV Movie", "Thriller", "War", "Western"]
    selected_genre = st.selectbox("Filter Genre", options=all_genres)
    min_vote = st.slider("Minimum Rating (Stars)", 0.0, 5.0, 0.0, step=0.5)

# Header Bar
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown("<h1 class='gradient-header'>WatchWise Movie Recommender</h1>", unsafe_allow_html=True)
    st.caption("Powered by Machine Learning, TF-IDF NLP, and SVD Collaborative Matrix Factorization")
with col_h2:
    if st.session_state.user_id:
        user_info = auth.get_user_profile(st.session_state.user_id)
        st.markdown(f"<div style='text-align:right;'><span class='badge badge-purple'>🔒 Logged In: {user_info['username']}</span></div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='text-align:right;'><span class='badge badge-cyan'>🔓 Guest Mode</span></div>", unsafe_allow_html=True)

# Main Navigation Tabs
tab_explore, tab_nlp, tab_personal, tab_detail = st.tabs([
    "🏠 Explore & Top 250 (Guest)",
    "🔍 Content NLP Search (Guest)",
    "👤 Personalized Feed (Logged-In)",
    "🎬 Movie Details & User-Aware"
])


def render_movie_card(movie_row, key_prefix="card", show_predicted=True, rank_num=None):
    """Render a styled movie card with poster, badges, rank number, and rating controls."""
    title = movie_row.get("title", "Unknown")
    year = movie_row.get("year", "N/A")
    rating = movie_row.get("vote_average", 0.0)
    mid = str(movie_row.get("movie_id", ""))
    
    # Poster URL or placeholder
    poster_url = movie_row.get("full_poster_url") or movie_row.get("poster_path")
    if poster_url and str(poster_url).strip() and str(poster_url).lower() != "nan":
        p_str = str(poster_url).strip()
        if p_str.startswith("http"):
            image_src = p_str
        elif p_str.startswith("/"):
            image_src = f"https://image.tmdb.org/t/p/w500{p_str}"
        else:
            image_src = f"https://image.tmdb.org/t/p/w500/{p_str}"
    else:
        image_src = f"https://placehold.co/300x450/1e1b4b/d8b4fe?text={title.replace(' ', '+')}"

    img_stretch(image_src)
    
    rank_badge = f"<span class='badge badge-purple'>#{rank_num}</span> " if rank_num else ""
    st.markdown(f"{rank_badge}**{title}** ({year})", unsafe_allow_html=True)
    
    # Badges
    st.markdown(f"<span class='badge badge-amber'>⭐ {rating}/10</span>", unsafe_allow_html=True)
    
    if show_predicted and st.session_state.user_id:
        u_profile = auth.get_user_profile(st.session_state.user_id)
        p_rating = engine.predict_rating(st.session_state.user_id, mid, user_ratings=u_profile.get("ratings", {}))
        st.markdown(f"<span class='badge badge-green'>For You: ⭐ {round(p_rating, 1)}/5</span>", unsafe_allow_html=True)
        
    if btn_stretch("Details ℹ️", key=f"{key_prefix}_details_{mid}"):
        st.session_state.selected_movie_id = mid
        st.rerun()

    # User Interaction Buttons (Logged-In)
    if st.session_state.user_id:
        u_profile = auth.get_user_profile(st.session_state.user_id)
        c1, c2, c3 = st.columns(3)
        with c1:
            is_liked = mid in u_profile.get("likes", [])
            like_label = "❤️" if is_liked else "🤍"
            if st.button(like_label, key=f"{key_prefix}_like_{mid}"):
                auth.toggle_like(st.session_state.user_id, mid)
                st.rerun()
        with c2:
            is_wl = mid in u_profile.get("watchlist", [])
            wl_label = "🔖" if is_wl else "➕"
            if st.button(wl_label, key=f"{key_prefix}_wl_{mid}"):
                auth.toggle_watchlist(st.session_state.user_id, mid)
                st.rerun()
        with c3:
            user_rating = u_profile.get("ratings", {}).get(mid, 0)
            st.caption(f"Rated: {user_rating}★" if user_rating else "-")


# ==========================================
# TAB 1: EXPLORE & TOP N MOVIES (GUEST FEATURES)
# ==========================================
with tab_explore:
    st.markdown("### 🏆 Top Ranked Movies (IMDb Weighted Rating Formula)")
    st.caption("Evaluates IMDb Weighted Rating $WR = \\frac{v}{v+m}R + \\frac{m}{v+m}C$ across all movies")
    
    col_t1, col_t2 = st.columns([2, 2])
    with col_t1:
        top_n_choice = st.selectbox("Select Ranking Limit (Top N)", options=[10, 50, 100, 250, 500], index=3, key="top_n_limit")
    
    top_ranked_df = engine.get_imdb_top_250(top_n=top_n_choice)
    if 'rank' not in top_ranked_df.columns:
        top_ranked_df['rank'] = range(1, len(top_ranked_df) + 1)
    
    items_per_page = 10
    total_pages = max(1, (len(top_ranked_df) + items_per_page - 1) // items_per_page)
    
    with col_t2:
        page_options = [f"Page {p} of {total_pages}" for p in range(1, total_pages + 1)]
        selected_page_str = st.selectbox("Browse Pages", options=page_options, index=0, key="top_page_select")
        page_num = int(selected_page_str.split()[1])
        
    start_idx = (page_num - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, len(top_ranked_df))
    page_df = top_ranked_df.iloc[start_idx:end_idx]
    
    st.markdown(f"Displaying **Rank #{start_idx+1} to #{end_idx}** of Top {top_n_choice} Movies:")
    cols = st.columns(5)
    for i, (_, row) in enumerate(page_df.iterrows()):
        with cols[i % 5]:
            render_movie_card(row, key_prefix=f"top_{page_num}_{i}", rank_num=row.get("rank"))

    st.divider()
    st.markdown("### 🎭 Top Movies by Genre Explorer")
    st.caption("Search and filter top-ranked movies across all 19 official TMDB genres")
    
    col_g1, col_g2, col_g3 = st.columns([2, 1, 1])
    with col_g1:
        target_genre = st.selectbox("Select Genre to Explore", options=all_genres[1:], index=0, key="genre_explorer_select")
    with col_g2:
        genre_top_n = st.selectbox("Genre Limit", options=[10, 25, 50, 100], index=1, key="genre_top_n")
        
    genre_df = engine.get_top_by_genre(target_genre, top_n=genre_top_n)
    if not genre_df.empty:
        g_total_pages = max(1, (len(genre_df) + items_per_page - 1) // items_per_page)
        with col_g3:
            g_page_options = [f"Page {p} of {g_total_pages}" for p in range(1, g_total_pages + 1)]
            g_selected_page_str = st.selectbox("Genre Page", options=g_page_options, index=0, key="g_page_select")
            g_page_num = int(g_selected_page_str.split()[1])

        g_start_idx = (g_page_num - 1) * items_per_page
        g_end_idx = min(g_start_idx + items_per_page, len(genre_df))
        g_page_df = genre_df.iloc[g_start_idx:g_end_idx]

        st.markdown(f"Displaying **Rank #{g_start_idx+1} to #{g_end_idx}** of Top {len(genre_df)} {target_genre} Movies:")
        cols2 = st.columns(5)
        for i, (_, row) in enumerate(g_page_df.iterrows()):
            with cols2[i % 5]:
                render_movie_card(row, key_prefix=f"genre_{target_genre}_{g_page_num}_{i}", rank_num=row.get("rank"))

    st.divider()
    st.markdown("### 🔥 Trending Now (Recent Hits & New Releases)")
    st.caption("Popular recent releases sorted by TMDB Popularity & Recency")
    
    col_tr1, col_tr2 = st.columns([2, 2])
    with col_tr1:
        trending_limit = st.selectbox("Trending Limit", options=[10, 25, 50, 75, 100], index=2, key="trending_limit_select")
        
    trending_df = engine.get_trending_now(top_n=trending_limit) if hasattr(engine, 'get_trending_now') else engine.get_trending_popular(top_n=trending_limit)
    
    if not trending_df.empty:
        tr_total_pages = max(1, (len(trending_df) + items_per_page - 1) // items_per_page)
        with col_tr2:
            tr_page_options = [f"Page {p} of {tr_total_pages}" for p in range(1, tr_total_pages + 1)]
            tr_selected_page_str = st.selectbox("Trending Page", options=tr_page_options, index=0, key="tr_page_select")
            tr_page_num = int(tr_selected_page_str.split()[1])

        tr_start_idx = (tr_page_num - 1) * items_per_page
        tr_end_idx = min(tr_start_idx + items_per_page, len(trending_df))
        tr_page_df = trending_df.iloc[tr_start_idx:tr_end_idx]

        st.markdown(f"Displaying **Rank #{tr_start_idx+1} to #{tr_end_idx}** of Top {len(trending_df)} Trending Movies:")
        cols_tr = st.columns(5)
        for i, (_, row) in enumerate(tr_page_df.iterrows()):
            with cols_tr[i % 5]:
                render_movie_card(row, key_prefix=f"tr_{tr_page_num}_{i}", rank_num=row.get("rank"))



    st.divider()
    st.markdown("### 💡 Because You Liked *Inception*")
    inception_recs = engine.recommend_content("Inception", top_n=5)
    if not inception_recs.empty:
        cols3 = st.columns(5)
        for i, (_, row) in enumerate(inception_recs.iterrows()):
            with cols3[i % 5]:
                render_movie_card(row, key_prefix=f"byl_{i}")


# ==========================================
# TAB 2: CONTENT NLP SEARCH (GUEST FEATURES)
# ==========================================
with tab_nlp:
    st.markdown("### 🔍 Content-Based NLP Similarity Engine")
    st.caption("Uses TF-IDF Vectorization & Cosine Similarity over Plot Overviews, Genres, Cast, and Directors")

    all_titles = list(engine.indices.keys())
    search_query = st.selectbox("Select or Type a Movie Title", options=[""] + [t.title() for t in all_titles[:500]])
    
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        actor_query = st.text_input("Filter by Actor Name")
    with col_s2:
        director_query = st.text_input("Filter by Director Name")
    with col_s3:
        search_top_n = st.slider("Number of Recommendations", 5, 20, 10)

    if st.button("🚀 Find Similar Movies", type="primary"):
        if search_query:
            st.markdown(f"#### 🎯 Movies Similar to *'{search_query}'*")
            results = engine.recommend_content(search_query, top_n=search_top_n)
            if not results.empty:
                cols_n = st.columns(5)
                for i, (_, row) in enumerate(results.iterrows()):
                    with cols_n[i % 5]:
                        st.markdown(f"<span class='badge badge-purple'>Match: {row.get('similarity_score', 0)}%</span>", unsafe_allow_html=True)
                        render_movie_card(row, key_prefix=f"nlp_{i}")
            else:
                st.warning("No similar movies found for this title.")
        elif actor_query or director_query:
            st.markdown("#### 🎬 Multi-Attribute Search Results")
            results = engine.multi_attribute_search(genre=selected_genre, director=director_query, actor=actor_query, top_n=search_top_n)
            if not results.empty:
                cols_m = st.columns(5)
                for i, (_, row) in enumerate(results.iterrows()):
                    with cols_m[i % 5]:
                        render_movie_card(row, key_prefix=f"multi_{i}")


# ==========================================
# TAB 3: PERSONALIZED FEED (LOGGED-IN FEATURES)
# ==========================================
with tab_personal:
    if not st.session_state.user_id:
        st.warning("🔒 Please Log In or Select a User Profile in the Sidebar to access Personalized Collaborative & Hybrid Feed.")
    else:
        u_profile = auth.get_user_profile(st.session_state.user_id)
        st.markdown(f"### 🤖 Hybrid Personalized Feed for **{u_profile['username']}**")
        st.caption("Combines Content NLP Similarity + SVD Collaborative Model + Real-Time User Likes/Dislikes & Retraining")

        # Interactive Real-Time Retraining Section
        with st.expander("⭐ Rate Movies to Retrain Your Recommendations in Real-Time"):
            r_col1, r_col2, r_col3 = st.columns([2, 1, 1])
            with r_col1:
                rate_movie_title = st.selectbox("Select Movie to Rate", options=[t.title() for t in all_titles[:200]])
            with r_col2:
                rate_val = st.slider("Rating (Stars)", 1.0, 5.0, 5.0, step=0.5)
            with r_col3:
                st.write("")
                st.write("")
                if st.button("Submit Rating & Retrain"):
                    m_details = engine.get_movie_details(rate_movie_title)
                    if m_details:
                        auth.add_user_rating(st.session_state.user_id, m_details['movie_id'], rate_val)
                        st.success(f"Rated {rate_movie_title} {rate_val}★! Model updated in real-time.")
                        st.rerun()

        st.divider()
        st.markdown("#### 🔀 Hybrid Recommended For You")
        hybrid_recs = engine.recommend_hybrid_personalized(
            user_id=st.session_state.user_id,
            user_profile=u_profile,
            top_n=10,
            genre_filter=selected_genre,
            min_rating=min_vote
        )
        if not hybrid_recs.empty:
            cols_h = st.columns(5)
            for i, (_, row) in enumerate(hybrid_recs.iterrows()):
                with cols_h[i % 5]:
                    st.markdown(f"<span class='badge badge-cyan'>Match: {row.get('match_percentage', 0)}%</span>", unsafe_allow_html=True)
                    render_movie_card(row, key_prefix=f"hybrid_{i}")


# ==========================================
# TAB 4: MOVIE DETAILS & USER-AWARE RECS
# ==========================================
with tab_detail:
    target_mid = st.session_state.selected_movie_id or "19995"
    m_info = engine.get_movie_details(target_mid)

    if m_info:
        st.markdown(f"## 🎬 {m_info['title']} ({m_info.get('year', 'N/A')})")
        col_d1, col_d2 = st.columns([1, 2])

        with col_d1:
            p_url = m_info.get("full_poster_url") or m_info.get("poster_path")
            if p_url and str(p_url).strip() and str(p_url).lower() != "nan":
                p_str = str(p_url).strip()
                if p_str.startswith("http"):
                    d_img_src = p_str
                elif p_str.startswith("/"):
                    d_img_src = f"https://image.tmdb.org/t/p/w500{p_str}"
                else:
                    d_img_src = f"https://image.tmdb.org/t/p/w500/{p_str}"
            else:
                d_img_src = f"https://placehold.co/300x450/1e1b4b/d8b4fe?text={m_info['title'].replace(' ', '+')}"
            img_stretch(d_img_src)

        with col_d2:
            st.markdown(f"**Genres:** {', '.join(m_info.get('parsed_genres', []))}")
            st.markdown(f"**Director:** {', '.join(m_info.get('parsed_director', []))}")
            st.markdown(f"**Cast:** {', '.join(m_info.get('parsed_cast', []))}")
            st.markdown(f"**Vote Average:** ⭐ {m_info.get('vote_average', 0)}/10 ({m_info.get('vote_count', 0)} votes)")
            st.markdown(f"**Popularity Score:** 🔥 {m_info.get('popularity', 0)}")
            st.markdown(f"**Overview:** {m_info.get('overview', 'No overview available.')}")

            if st.session_state.user_id:
                u_profile = auth.get_user_profile(st.session_state.user_id)
                pred_val = engine.predict_rating(st.session_state.user_id, target_mid, user_ratings=u_profile.get("ratings", {}))
                st.info(f"🎯 **Predicted Rating for {u_profile['username']}: ⭐ {round(pred_val, 1)} / 5.0**")

        st.divider()
        st.markdown("### 🔄 User-Aware 'More Like This' Recommendations")
        st.caption("The same movie page yields DIFFERENT results tailored to the currently logged-in user!")

        user_profile_data = auth.get_user_profile(st.session_state.user_id) if st.session_state.user_id else None
        user_aware_recs = engine.recommend_hybrid_personalized(
            user_id=st.session_state.user_id,
            movie_title=m_info['title'],
            user_profile=user_profile_data,
            top_n=5
        )

        if not user_aware_recs.empty:
            cols_u = st.columns(5)
            for i, (_, row) in enumerate(user_aware_recs.iterrows()):
                with cols_u[i % 5]:
                    render_movie_card(row, key_prefix=f"user_aware_{i}")
