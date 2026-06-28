import os
import json
import feedparser
import requests
import streamlit as st
from datetime import datetime

# =====================================================================
# 1. SET UP THE WEB PAGE CONFIGURATION (Must be the first Streamlit command)
# =====================================================================
st.set_page_config(
    page_title="Smart News Digest",
    page_icon="📰",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# =====================================================================
# 2. CONFIGURATION & CREDENTIALS
# =====================================================================
API_KEY = "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"
API_BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions" 
LLM_MODEL = "google/gemma-4-31b-it" 

RSS_FEEDS = [
    "https://feeds.bloomberg.com/markets/news.rss",
    "https://feeds.bloomberg.com/politics/news.rss"
    "https://feeds.bloomberg.com/technology/news.rss",
    "https://feeds.bloomberg.com/wealth/news.rss",
    "https://feeds.bloomberg.com/economics/news.rss",
    "http://rss.cnn.com/rss/cnn_topstories.rss",
    "http://rss.cnn.com/rss/cnn_world.rss",
    "http://rss.cnn.com/rss/cnn_allpolitics.rss",
    "http://rss.cnn.com/rss/cnn_tech.rss",
    "http://rss.cnn.com/rss/money_latest.rss",
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"
]

# Storing the processed data as raw JSON for fast app loading
OUTPUT_DIR = "/DATA/news_feed"
CACHE_FILE = f"{OUTPUT_DIR}/news_cache.json"

# =====================================================================
# 3. CORE PROCESSING LOGIC
# =====================================================================

def fetch_and_process_news():
    """Triggers the full RSS + LLM background pipeline and saves cache."""
    collected_articles = []
    
    # 1. Fetch from RSS
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            feed_title = feed.feed.title if 'title' in feed.feed else "News"
            for entry in feed.entries[:5]:
                collected_articles.append({
                    "source": feed_title,
                    "title": entry.get("title", "No Title"),
                    "link": entry.get("link", "#"),
                    "raw_text": entry.get("summary", entry.get("description", ""))
                })
        except Exception as e:
            st.error(f"Error reading feed {url}: {e}")

    if not collected_articles:
        return False

    # 2. Process via LLM
    processed_news = []
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    system_prompt = (
        "You are an elite news analyst. Process the article details and return a structured summary. "
        "Extract as many bullet points as useful to thoroughly cover the context. Stop only when more bullets add fluff.\n"
        "Respond ONLY in valid JSON format matching this schema:\n"
        "{\n"
        '  "category": "Single word category (e.g., Tech, World, Finance, Security)",\n'
        '  "bullet_points": ["Detail 1", "Detail 2"],\n'
        '  "takeaway": "One crisp sentence explaining the wider impact."\n'
        "}"
    )

    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, article in enumerate(collected_articles):
        status_text.text(f"Processing story {idx+1} of {len(collected_articles)}...")
        progress_bar.progress((idx + 1) / len(collected_articles))
        
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Source: {article['source']}\nTitle: {article['title']}\nRaw: {article['raw_text']}"}
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }
        
        try:
            response = requests.post(f"{API_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=20)
            if response.status_code == 200:
                summary_json = json.loads(response.json()['choices'][0]['message']['content'])
                processed_news.append({
                    "article": article,
                    "summary": summary_json
                })
        except Exception:
            continue

    # Clean up UI bars
    progress_bar.empty()
    status_text.empty()

    # 3. Save Cache
    if processed_news:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        cache_data = {
            "last_updated": datetime.now().strftime("%A, %b %d at %I:%M %p"),
            "news": processed_news
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=4)
        return True
    return False

# =====================================================================
# 4. GORGEOUS FRONTEND RENDERING BUILDER
# =====================================================================

# Title Header Configuration
st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>📰 Smart News Digest</h1>", unsafe_allowed_html=True)

# Check if cache exists
cache_exists = os.path.exists(CACHE_FILE)

# Header Control Layout
col1, col2 = st.columns([2, 1])
with col1:
    if cache_exists:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        st.caption(f"🕒 **Last updated:** {data['last_updated']}")
    else:
        st.caption("No articles downloaded yet.")

with col2:
    # Big trigger button to fetch fresh data
    if st.button("🔄 Refresh News", use_container_width=True, type="primary"):
        with st.spinner("Analyzing stories..."):
            success = fetch_and_process_news()
            if success:
                st.success("Feed updated successfully!")
                st.rerun()
            else:
                st.error("Failed to parse updates.")

st.markdown("---")

# Render News Container cards
if cache_exists:
    with open(CACHE_FILE, "r") as f:
        data = json.load(f)
        
    for item in data["news"]:
        art = item["article"]
        sum_data = item["summary"]
        
        # Color mapping logic based on category variables
        cat = sum_data.get("category", "General").upper()
        color_map = {"TECH": "#00d2ff", "WORLD": "#ff9f43", "FINANCE": "#10ac84", "SECURITY": "#ee5253"}
        badge_color = color_map.get(cat, "#5f27cd")
        
        # News Container Block Design
        with st.container():
            # Header tag & link row
            st.markdown(
                f"<span style='background-color: {badge_color}; color: white; padding: 2px 8px; "
                f"border-radius: 4px; font-size: 0.75rem; font-weight: bold;'>{cat}</span> "
                f"<span style='color: #888888; font-size: 0.85rem; margin-left: 10px;'>{art['source']}</span>", 
                unsafe_allowed_html=True
            )
            st.markdown(f"### [{art['title']}]({art['link']})")
            
            # Bullet point output looping
            for bullet in sum_data.get("bullet_points", []):
                st.markdown(f"• {bullet}")
                
            # Colorful "The Big Picture" Callout banner
            st.info(f"**The Big Picture:** {sum_data.get('takeaway', 'N/A')}")
            st.markdown("<br>", unsafe_allowed_html=True)
else:
    st.warning("👋 Welcome! Click the **Refresh News** button above to compile your very first custom digest.")