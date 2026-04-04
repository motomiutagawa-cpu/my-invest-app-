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
st.title("🌐 AI投資ニュース・個別深層分析対応")

# --- サイドバー設定 ---
api_key = st.sidebar.text_input("APIキーを入力してください", type="password")

st.sidebar.markdown("---")
market_choice = st.sidebar.radio(
    "分析対象を選択",
    options=["日本株", "米国株", "先物・商品", "FX・為替"],
    horizontal=True
)

st.sidebar.markdown("🕒 取得範囲")
hours_range = st.sidebar.slider("過去何時間分を取得しますか？", min_value=1, max_value=72, value=24)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔍 注目セクター（複数選択可）")
SECTOR_OPTIONS = ["防衛", "宇宙", "重工", "海運", "物流", "エネルギー", "資源・素材", "半導体", "ハイテク・AI", "金融・銀行", "商社", "自動車", "不動産", "電力・インフラ", "化学・素材"]
selected_sectors = st.sidebar.multiselect("セクターを選択", options=SECTOR_OPTIONS, default=[])

# もとみさん指定の精鋭リスト
jp_stocks_curated = "ソニーg, ソニーfg, アストロスケール, QPSホールディングス, ACSL, 三菱重工, 川崎重工, IHI, 安川電機, 住友電工, 古河電気工業, フジクラ, 日本郵船, 商船三井, 川崎汽船, 日東電工, 東レ, シマノ, 三菱UFJ, みずほフィナンシャルグループ, 三井物産, 三菱商事, KDDI, 東北電力, 九州電力, 任天堂, カバー, トヨタ, ホンダ, 日立製作所, サンリオ, INPEX"
us_stocks_curated = "Apple, NVIDIA, Alphabet, Amazon, Tesla, Microsoft, Meta, Palantir, Rocket Lab, Broadcom, Berkshire Hathaway"
future_items = "日経225先物, NYダウ先物, ナスダック100先物, WTI原油先物, 金先物(Gold), 米国債10年"
fx_pairs = "USD/JPY, EUR/JPY, GBP/JPY, AUD/JPY"

st.sidebar.markdown("---")
st.sidebar.markdown(f"### 📝 {market_choice} 監視コア銘柄")
if market_choice == "米国株": current_default = us_stocks_curated
elif market_choice == "先物・商品": current_default = future_items
elif market_choice == "FX・為替": current_default = fx_pairs
else: current_default = jp_stocks_curated

stock_input = st.sidebar.text_area("コア銘柄リスト", value=current_default, height=180)
WATCHLIST = [s.strip() for s in stock_input.replace("、", ",").split(",") if s.strip()]

# セッション状態の管理
if "messages" not in st.session_state: st.session_state.messages = []
if "analysis_text" not in st.session_state: st.session_state.analysis_text = None
if "fetched_news" not in st.session_state: st.session_state.fetched_news = []
if "individual_summaries" not in st.session_state: st.session_state.individual_summaries = {}

async def generate_voice(text):
    """読み上げ前に記号を掃除し、1.3倍速で生成"""
    clean_text = text.replace("#", "").replace("*", "").replace(">", " ")
    communicate = edge_tts.Communicate(clean_text, "ja-JP-NanamiNeural", rate="+30%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": audio_data += chunk["data"]
    return audio_data

def get_all_news(hours):
    """ニュースソースを取得"""
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

# 個別記事のAI要約・分析関数
def analyze_single_article(title, summary, market, watchlist):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
    prompt = f"""
    以下のニュース記事を投資家の視点で要約・分析してください。
    【タイトル】: {title}
    【概要】: {summary}
    
    【出力指示】
    1. 記事の内容を3行以内で要約してください。
    2. 監視銘柄（{watchlist[:5]}...）や関連市場への「具体的な影響」と「ポジネガ」を客観的に述べてください。
    3. 挨拶は不要。
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"要約エラー: {e}"

# メイン分析実行
if st.sidebar.button(f"{market_choice} 攻めの分析を開始"):
    if not api_key:
        st.error("APIキーを入れてください！")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
        with st.spinner("コア銘柄を軸に、市場全体からチャンスを探索中..."):
            news_data = get_all_news(hours_range)
            st.session_state.fetched_news = news_data
            st.session_state.individual_summaries = {} # リセット
            all_news_text = ""
            for i, n in enumerate(news_data):
                all_news_text += f"No.{i} [{n['source']}]: {n['title']}\n{n['summary']}\n\n"
            
            prompt = f"あなたは凄腕の投資アナリストです。過去{hours_range}時間のニュースから、{market_choice}および{', '.join(selected_sectors)}に関連する情報を分析してください。監視銘柄（{', '.join(WATCHLIST)}）を最優先にしつつ、リスト外の注目銘柄も積極的に提案してください。具体的銘柄を見出しにし、事実・意味・ポジネガを記載。挨拶は不要。\n\n{all_news_text}"
            
            try:
                chat = model.start_chat(history=[])
                response = chat.send_message(prompt)
                st.session_state.analysis_text = response.text
                st.session_state.chat_session = chat
                st.session_state.messages = []
            except Exception as e:
                st.error(f"分析エラー: {e}")

# --- 表示部分 ---
if st.session_state.analysis_text:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("📊 ニュースフィード")
        for i, n in enumerate(st.session_state.fetched_news):
            with st.expander(f"No.{i}: 📌 [{n['time']}] {n['title']}"):
                st.caption(f"ソース: {n['source']}")
                st.write(n['summary'])
                
                # 【新規】個別要約ボタン
                if st.button(f"✨ AIでこの記事を深掘り要約 (No.{i})", key=f"btn_{i}"):
                    with st.spinner("AI要約中..."):
                        summary_res = analyze_single_article(n['title'], n['summary'], market_choice, WATCHLIST)
                        st.session_state.individual_summaries[i] = summary_res
                
                if i in st.session_state.individual_summaries:
                    st.info(st.session_state.individual_summaries[i])
                
                st.link_button("記事全文（外部リンク）", n['link'])

    with col2:
        st.subheader(f"🤖 {market_choice} 精鋭分析 ＆ 銘柄提案")
        with st.spinner("音声を生成中..."):
            try:
                audio_bytes = asyncio.run(generate_voice(st.session_state.analysis_text))
                st.audio(audio_bytes, format='audio/mp3')
            except: st.warning("音声生成に失敗しました。")
        st.write(st.session_state.analysis_text)
        st.markdown("---")
        st.subheader("💬 深掘りチャット")
        for m in st.session_state.messages:
            with st.chat_message(m["role"]): st.markdown(m["content"])
        if q := st.chat_input("この分析についてさらに詳しく！"):
            st.session_state.messages.append({"role": "user", "content": q})
            with st.chat_message("user"): st.markdown(q)
            with st.chat_message("assistant"):
                res = st.session_state.chat_session.send_message(q)
                st.markdown(res.text)
            st.session_state.messages.append({"role": "assistant", "content": res.text})
