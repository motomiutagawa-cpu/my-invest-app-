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
st.set_page_config(page_title="AI投資アナリスト・コンプリート", layout="wide")
st.title("🌐 AI投資ニュース・先物・経済指標深層分析")

# --- サイドバー設定 ---
api_key = st.sidebar.text_input("APIキーを入力してください", type="password")

st.sidebar.markdown("---")
# 市場選択に「先物」を追加
market_choice = st.sidebar.radio(
    "分析対象を選択",
    options=["日本株", "米国株", "先物・商品", "FX・為替"],
    horizontal=True
)

st.sidebar.markdown("🕒 取得範囲")
hours_range = st.sidebar.slider("過去何時間分を取得しますか？", min_value=1, max_value=72, value=24)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔍 注目セクター（複数選択可）")
SECTOR_OPTIONS = [
    "防衛", "宇宙", "重工", "海運", "物流", "エネルギー", "資源・素材", 
    "半導体", "ハイテク・AI", "金融・銀行", "商社", "自動車", 
    "不動産", "電力・インフラ", "化学・素材"
]
selected_sectors = st.sidebar.multiselect("セクターを選択", options=SECTOR_OPTIONS, default=[])

# 銘柄リストの定義
jp_stocks = "三菱重工, 川崎重工, IHI, ソニーg, ソニーfg, トヨタ, 任天堂, アストロスケール, 安川電機, 住友電工, フジクラ, 東レ, 本田技研, 日立製作所, 東北電力, シマノ, acsl, 日東電工, 三菱UFJ, サンリオ, KDDI, 川崎汽船, 商船三井, 日本郵船, 三菱hcキャピタル, 三菱ケミカル, 伊藤忠, 日東紡績, 三菱マテリアル, 小松製作所, 三菱商事, オリックス, 楽天グループ, 三井不動産, 三井物産, アドバンテスト, 東京エレクトロン, キーエンス, ファナック, 村田製作所, レーザーテック, イビデン, ディスコ, 信越化学工業, 第一生命, ヤマハ, 住友金属鉱山, エニーカラー, ソフトバンクg, キオクシア, 三井住友fg, みずほfg, QPSホールディングス, 名村造船所, カバー, inpex, ispace, スカパーjsat"
us_stocks = "Alphabet, Apple, NVIDIA, Oracle, Palantir, Amazon, Bank of America, Tesla, Rocket Lab, Intel, Microsoft, Netflix, SanDisk, Adobe, Meta, Advantest, Boeing, Shopify, Novo Nordisk, Berkshire Hathaway, Exxon Mobil, Ford, General Motors, Spotify"
future_items = "日経225先物, NYダウ先物, ナスダック100先物, WTI原油先物, 金先物(Gold), 銅先物, 天然ガス, 米国債10年"
fx_pairs = "USD/JPY, EUR/JPY, GBP/JPY, AUD/JPY, EUR/USD"

st.sidebar.markdown("---")
st.sidebar.markdown(f"### 📝 {market_choice} 監視対象")
if market_choice == "米国株": current_default = us_stocks
elif market_choice == "先物・商品": current_default = future_items
elif market_choice == "FX・為替": current_default = fx_pairs
else: current_default = jp_stocks

stock_input = st.sidebar.text_area("リスト", value=current_default, height=150)
WATCHLIST = [s.strip() for s in stock_input.replace("、", ",").split(",") if s.strip()]

# セッション状態
if "messages" not in st.session_state: st.session_state.messages = []
if "analysis_text" not in st.session_state: st.session_state.analysis_text = None
if "fetched_news" not in st.session_state: st.session_state.fetched_news = []

async def generate_voice(text):
    """読み上げ前に記号を掃除し、1.3倍速で生成"""
    clean_text = text.replace("#", "").replace("*", "").replace(">", " ")
    communicate = edge_tts.Communicate(clean_text, "ja-JP-NanamiNeural", rate="+30%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data

def get_all_news(hours):
    """ニュースソースを取得"""
    rss_urls = [
        "https://news.yahoo.co.jp/rss/topics/business.xml",
        "https://news.yahoo.co.jp/rss/topics/world.xml",
        "https://jp.reuters.com/rss/businessNews",
        "https://jp.reuters.com/rss/worldNews",
        "https://prtimes.jp/index.rdf"
    ]
    news_list = []
    seen_links = set()
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
                news_list.append({
                    "title": entry.title, "summary": entry.get("summary", ""), "link": entry.link, 
                    "source": source_name, "time": pub_time.astimezone(timezone(timedelta(hours=9))).strftime('%m/%d %H:%M') if pub_struct else "--:--"
                })
                seen_links.add(entry.link)
        except: continue
    return news_list

# 分析実行
if st.sidebar.button(f"{market_choice} を分析"):
    if not api_key:
        st.error("APIキーを入れてください！")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview") 
        
        with st.spinner(f"{market_choice}と経済指標を精査中..."):
            news_data = get_all_news(hours_range)
            st.session_state.fetched_news = news_data
            all_news_text = ""
            for i, n in enumerate(news_data):
                all_news_text += f"No.{i} [{n['source']}]: {n['title']}\n{n['summary']}\n\n"
            
            prompt = f"""
            あなたはプロの投資アナリストです。
            
            【ターゲット市場】: {market_choice}
            【監視対象】: {', '.join(WATCHLIST)}
            
            指示:
            1. 過去{hours_range}時間のニュースを分析してください。
            2. 【FX・為替】または【先物】の場合、直近および近日予定されている「重要経済指標（雇用統計、CPI、FOMC等）」が、ドル円や指数にどのようなインパクトを与えるか予測を含めて解説してください。
            3. 【先物・商品】の場合、原油や金などのコモディティ価格が、地政学リスクや為替とどう連動しているか紐解いてください。
            4. 具体的な対象名を見出しにし、事実・意味・ポジネガを記載。
            5. 挨拶は不要。
            
            ニュースリスト:
            {all_news_text}
            """
            
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
        # 左側には経済指標カレンダーも表示
        st.subheader("📊 経済指標・元記事")
        with st.expander("🕒 直近の注目経済指標カレンダー（目安）"):
            st.write("※AIはニュース内の速報および市場予測値を元に分析しています。")
            st.info("今週の注目: 米雇用統計(金)、CPI(水)、FOMC議事録")
            
        for i, n in enumerate(st.session_state.fetched_news):
            with st.expander(f"No.{i}: 📌 [{n['time']}] {n['title']}"):
                st.write(n['summary'])
                st.link_button("記事全文", n['link'])
    with col2:
        st.subheader(f"🤖 {market_choice} 分析結果")
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
        if q := st.chat_input("この指標の結果、円安はどこまで進むと思う？"):
            st.session_state.messages.append({"role": "user", "content": q})
            with st.chat_message("user"): st.markdown(q)
            with st.chat_message("assistant"):
                res = st.session_state.chat_session.send_message(q)
                st.markdown(res.text)
            st.session_state.messages.append({"role": "assistant", "content": res.text})
