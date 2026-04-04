import streamlit as st
import feedparser
import google.generativeai as genai
import asyncio
import edge_tts
import io
from datetime import datetime, timedelta, timezone
import time
import re

# 画面設定
st.set_page_config(page_title="AI投資アナリスト・プロ", layout="wide")

# --- CSSで左右独立スクロール ＆ UI微調整 ---
st.markdown("""
    <style>
    div[data-testid="column"] {
        height: 85vh;
        overflow-y: auto;
        padding-right: 10px;
    }
    /* スクロールバーのデザイン */
    div[data-testid="column"]::-webkit-scrollbar { width: 6px; }
    div[data-testid="column"]::-webkit-scrollbar-thumb { background-color: #888; border-radius: 10px; }
    /* サイドバーのチェックボックスを見やすく */
    .stCheckbox { margin-bottom: -15px; }
    </style>
    """, unsafe_allow_html=True)

st.title("🌐 AI投資ニュース・プロ分析")

# --- サイドバー設定 ---
api_key = st.sidebar.text_input("APIキーを入力", type="password")

st.sidebar.markdown("---")
market_choice = st.sidebar.radio(
    "分析対象を選択",
    options=["日本株", "米国株", "先物・商品", "FX・為替"],
    horizontal=True
)

st.sidebar.markdown("🕒 取得範囲")
hours_range = st.sidebar.slider("過去何時間分を取得しますか？", min_value=1, max_value=72, value=24)

# --- 【改良】キーボードが出ない選択方式 ---
st.sidebar.markdown("---")
with st.sidebar.expander("🔍 注目セクターを選択", expanded=False):
    SECTOR_OPTIONS = ["防衛", "宇宙", "重工", "海運", "物流", "エネルギー", "資源・素材", "半導体", "ハイテク・AI", "金融・銀行", "商社", "自動車", "不動産", "電力・インフラ", "化学・素材"]
    selected_sectors = [s for s in SECTOR_OPTIONS if st.checkbox(s, key=f"sec_{s}")]

st.sidebar.markdown("---")
with st.sidebar.expander(f"📝 {market_choice} 監視銘柄を選択", expanded=True):
    # もとみさん指定のマスターリスト
    MASTER_STOCKS = {
        "日本株": ["ソニーg", "ソニーfg", "アストロスケール", "QPSホールディングス", "acsl", "三菱重工", "川崎重工", "ihi", "安川電機", "住友電工", "古河電気工業", "フジクラ", "日本郵船", "商船三井", "川崎汽船", "日東電工", "東レ", "シマノ", "三菱UFJ", "みずほフィナンシャルグループ", "三井物産", "三菱商事", "kddi", "東北電力", "九州電力", "任天堂", "カバー", "トヨタ", "ホンダ", "日立製作所", "サンリオ", "inpex"],
        "米国株": ["Apple", "NVIDIA", "Alphabet", "Amazon", "Tesla", "Microsoft", "Meta", "Palantir", "Rocket Lab", "Broadcom", "Berkshire Hathaway"],
        "先物・商品": ["日経225先物", "NYダウ先物", "ナスダック100先物", "WTI原油先物", "金先物(Gold)", "米国債10年"],
        "FX・為替": ["USD/JPY", "EUR/JPY", "GBP/JPY", "AUD/JPY", "EUR/USD"]
    }
    
    current_master = MASTER_STOCKS.get(market_choice, [])
    # キーボードを出さないためにチェックボックスで並べる
    selected_stocks = [s for s in current_master if st.checkbox(s, key=f"stk_{s}", value=True)]

custom_stocks = st.sidebar.text_input("その他追加したい銘柄（任意）", placeholder="ここだけキーボードが出ます")
WATCHLIST = selected_stocks + ([custom_stocks] if custom_stocks else [])

# セッション状態
if "messages" not in st.session_state: st.session_state.messages = []
if "analysis_text" not in st.session_state: st.session_state.analysis_text = None
if "fetched_news" not in st.session_state: st.session_state.fetched_news = []
if "individual_summaries" not in st.session_state: st.session_state.individual_summaries = {}

async def generate_voice(text):
    clean_text = text.replace("#", "").replace("*", "").replace(">", " ")
    communicate = edge_tts.Communicate(clean_text, "ja-JP-NanamiNeural", rate="+30%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": audio_data += chunk["data"]
    return audio_data

def get_all_news(hours):
    rss_urls = ["https://news.yahoo.co.jp/rss/topics/business.xml", "https://news.yahoo.co.jp/rss/topics/world.xml", "https://jp.reuters.com/rss/businessNews", "https://jp.reuters.com/rss/worldNews", "https://prtimes.jp/index.rdf"]
    news_list, seen_links = [], set()
    now = datetime.now(timezone.utc)
    time_threshold = now - timedelta(hours=hours)
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            source_name = "Yahoo" if "yahoo" in url else "ロイター" if "reuters" in url else "PR TIMES"
            for entry in feed.entries[:100]:
                pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
                if pub_struct:
                    pub_time = datetime.fromtimestamp(time.mktime(pub_struct), timezone.utc)
                    if pub_time < time_threshold: continue
                if entry.link in seen_links: continue
                news_list.append({"title": entry.title, "summary": entry.get("summary", ""), "link": entry.link, "source": source_name, "time": pub_time.astimezone(timezone(timedelta(hours=9))).strftime('%m/%d %H:%M') if pub_struct else "--:--"})
                seen_links.add(entry.link)
        except: continue
    return news_list

if st.sidebar.button(f"{market_choice} 分析を開始"):
    if not api_key: st.error("APIキーを入れてください！")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
        with st.spinner("情報を精査中..."):
            news_data = get_all_news(hours_range)
            st.session_state.fetched_news = news_data
            st.session_state.individual_summaries = {}
            all_news_text = ""
            for i, n in enumerate(news_data):
                all_news_text += f"No.{i}: {n['title']}\n{n['summary']}\n\n"
            
            prompt = f"""
            凄腕投資アナリストとして分析せよ。挨拶、免責事項、自己責任等の定型文は一切書くな。各分析には必ず根拠番号「(No.Xより)」を明記せよ。
            【市場】: {market_choice}
            【セクター】: {', '.join(selected_sectors) if selected_sectors else '全方位'}
            【監視銘柄】: {', '.join(WATCHLIST)}
            
            具体的銘柄を見出しにし、「事実」「意味」「ポジネガ」を端的に記載。リスト外でも材料があれば積極的に提案せよ。
            ニュースリスト: {all_news_text}
            """
            try:
                chat = model.start_chat(history=[])
                response = chat.send_message(prompt)
                st.session_state.analysis_text = response.text
                st.session_state.chat_session = chat
                st.session_state.messages = []
            except Exception as e: st.error(f"エラー: {e}")

# --- 表示部分 ---
if st.session_state.analysis_text:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("📊 ニュースフィード")
        for i, n in enumerate(st.session_state.fetched_news):
            with st.expander(f"No.{i}: 📌 [{n['time']}] {n['title']}"):
                st.write(n['summary'])
                if st.button(f"✨ AI要約 (No.{i})", key=f"btn_{i}"):
                    st.session_state.individual_summaries[i] = "分析中..." # 暫定
                st.link_button("全文へ", n['link'])
    with col2:
        st.subheader(f"🤖 AI分析（1.3倍速）")
        with st.spinner("音声を生成中..."):
            try:
                audio_bytes = asyncio.run(generate_voice(st.session_state.analysis_text))
                st.audio(audio_bytes, format='audio/mp3')
            except: st.warning("音声生成エラー")
        st.write(st.session_state.analysis_text)
        st.markdown("---")
        if q := st.chat_input("深掘り質問"):
            st.session_state.messages.append({"role": "user", "content": q})
            with st.chat_message("user"): st.markdown(q)
            with st.chat_message("assistant"):
                res = st.session_state.chat_session.send_message(q)
                st.markdown(res.text)
