import streamlit as st
import feedparser
import google.generativeai as genai
import asyncio
import edge_tts
import io
from datetime import datetime, timedelta, timezone
import time
import yfinance as yf

# 画面設定
st.set_page_config(page_title="AI投資アナリスト・プロ", layout="wide")

st.title("🌐 AI投資ニュース・プロ分析（要約＋予測統合版）")

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

# セクター選択
st.sidebar.markdown("---")
with st.sidebar.expander("🔍 注目セクターを選択"):
    SECTOR_OPTIONS = ["防衛", "宇宙", "重工", "海運", "物流", "エネルギー", "資源・素材", "半導体", "ハイテク・AI", "金融・銀行", "商社", "自動車", "不動産", "電力・インフラ", "化学・素材"]
    col_s1, col_s2 = st.columns(2)
    if col_s1.button("全選択", key="sec_all"):
        for s in SECTOR_OPTIONS: st.session_state[f"sec_{s}"] = True
    if col_s2.button("全解除", key="sec_none"):
        for s in SECTOR_OPTIONS: st.session_state[f"sec_{s}"] = False
    selected_sectors = [s for s in SECTOR_OPTIONS if st.checkbox(s, key=f"sec_{s}", value=st.session_state.get(f"sec_{s}", False))]

# 銘柄を絞る
st.sidebar.markdown("---")
st.sidebar.markdown("### 🎯 特定銘柄を深掘り")
narrow_stocks = st.sidebar.text_area(
    "銘柄名・コードを入力",
    placeholder="例: 7011, NVDA\n空欄なら注目銘柄を自動選別",
)

# 精鋭マスターリスト
CORE_WATCHLIST = {
    "日本株": "6758, 8729, 186A, 5595, 6767, 7011, 7012, 7013, 6506, 5802, 5801, 5803, 9101, 9104, 9107, 6988, 3402, 7309, 8306, 8411, 8031, 8058, 9433, 9506, 9508, 7974, 5253, 7203, 7267, 6501, 8136, 1605",
    "米国株": "AAPL, NVDA, GOOGL, AMZN, TSLA, MSFT, META, PLTR, RKLB, AVGO, BRK-B",
    "先物・商品": "^NK225, ^DJI, ^IXIC, CL=F, GC=F, ^TNX",
    "FX・為替": "USD/JPY, EUR/JPY, GBP/JPY, AUD/JPY, EUR/USD"
}

# セッション状態
if "analysis_text" not in st.session_state: st.session_state.analysis_text = None
if "fetched_news" not in st.session_state: st.session_state.fetched_news = []
if "individual_summaries" not in st.session_state: st.session_state.individual_summaries = {}
if "messages" not in st.session_state: st.session_state.messages = []
if "chat_session" not in st.session_state: st.session_state.chat_session = None

# --- 株価取得関数 ---
def get_price_info(stock_str, market):
    items = [s.strip() for s in stock_str.replace("、", ",").split(",") if s.strip()]
    price_data = ""
    for item in items:
        ticker_symbol = item
        if "/" in item or market == "FX・為替":
            ticker_symbol = item.replace("/", "").replace(" ", "")
            if not ticker_symbol.endswith("=X"): ticker_symbol += "=X"
        elif market == "日本株" and item.isdigit() and len(item) == 4:
            ticker_symbol = f"{item}.T"
        
        try:
            tk = yf.Ticker(ticker_symbol)
            df = tk.history(period="5d")
            if not df.empty and len(df) >= 2:
                cur_price = df['Close'].iloc[-1]
                prev_price = df['Close'].iloc[-2]
                change = ((cur_price - prev_price) / prev_price) * 100
                price_data += f"・{item}: {cur_price:,.1f} ({change:+.2f}%)\n"
            else:
                price_data += f"・{item}: データ取得不可\n"
        except: continue
    return price_data

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
            for entry in feed.entries[:100]:
                pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
                if pub_struct:
                    pub_time = datetime.fromtimestamp(time.mktime(pub_struct), timezone.utc)
                    if pub_time < time_threshold: continue
                if entry.link in seen_links: continue
                news_list.append({"title": entry.title, "summary": entry.get("summary", ""), "link": entry.link, "source": "Yahoo" if "yahoo" in url else "ロイター" if "reuters" in url else "PR TIMES", "time": pub_time.astimezone(timezone(timedelta(hours=9))).strftime('%m/%d %H:%M') if pub_struct else "--:--"})
                seen_links.add(entry.link)
        except: continue
    return news_list

# --- 【修正】個別記事の要約＋予測 ---
def analyze_single_article(title, summary):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
    prompt = f"""
    この記事を投資家視点で端的に要約し、影響を予測してください。挨拶や免責文は不要。

    【出力フォーマット】
    ■ ニュース要約
    （※ここに3行程度で事実をわかりやすく要約）

    ■ 投資判断
    【判定】ポジティブ / ネガティブ / 中立
    【予想インパクト】+〇%上昇予測 / -〇%下落予測（※過去の傾向から大胆に数値を提示）

    【タイトル】: {title}
    【本文】: {summary}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"要約エラー: {e}"

# --- 分析実行 ---
if st.sidebar.button(f"{market_choice} 分析を開始"):
    if not api_key: st.error("APIキーを入れてください。")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
        with st.spinner("最新データを統合中..."):
            news_data = get_all_news(hours_range)
            st.session_state.fetched_news = news_data
            st.session_state.individual_summaries = {}
            st.session_state.messages = []
            
            target_list = narrow_stocks if narrow_stocks else CORE_WATCHLIST.get(market_choice)
            realtime_prices = get_price_info(target_list, market_choice)
            
            all_news_text = ""
            for i, n in enumerate(news_data):
                all_news_text += f"No.{i}: {n['title']}\n{n['summary']}\n\n"
            
            prompt = f"""
            プロの投資アナリストとして分析せよ。挨拶・免責文は一切禁止。
            
            【現在の株価・騰落率データ】
            {realtime_prices}
            
            【絶対遵守の出力ルール】
            1. 見出しは必ず **【銘柄名(コード) | 現在価格 | 騰落率】** とし、上記のデータを正確に記載せよ。
            2. 各分析の冒頭に必ず **【判定：ポジティブ/ネガティブ】** と **【予想インパクト：+〇%上昇予測 / -〇%下落予測】** を明記せよ。
            3. **個別銘柄**: 指定銘柄およびリスト外でも材料が強いものは個別で深掘りせよ。
            4. **セクター**: 全体に波及するニュースはセクター（{', '.join(selected_sectors)}）でまとめ、波及銘柄と予測値を書け。
            5. 直接の材料がない場合でも、マクロ環境からの「連想・間接影響」と「テクニカル予測」を必ず含め、文末に「(No.Xより)」を添えよ。
            
            ニュースリスト:
            {all_news_text}
            """
            try:
                chat = model.start_chat(history=[])
                response = chat.send_message(prompt)
                st.session_state.analysis_text = response.text
                st.session_state.chat_session = chat
            except Exception as e: st.error(f"分析エラー: {e}")

# --- 表示エリア ---
if st.session_state.analysis_text:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("📊 ニュースフィード")
        with st.container(height=800):
            for i, n in enumerate(st.session_state.fetched_news):
                with st.expander(f"No.{i}: 📌 [{n['time']}] {n['title']}"):
                    st.write(n['summary'])
                    if st.button(f"✨ AI要約 (No.{i})", key=f"btn_{i}"):
                        with st.spinner("要約と影響度を予測中..."):
                            st.session_state.individual_summaries[i] = analyze_single_article(n['title'], n['summary'])
                    if i in st.session_state.individual_summaries:
                        st.info(st.session_state.individual_summaries[i])
                    st.link_button("全文へ", n['link'])
                
    with col2:
        st.subheader("🤖 AI戦略分析（価格・予測値連動）")
        with st.container(height=800):
            with st.spinner("音声を生成中..."):
                try:
                    audio_bytes = asyncio.run(generate_voice(st.session_state.analysis_text))
                    st.audio(audio_bytes, format='audio/mp3')
                except: st.warning("音声生成エラー")
            
            st.write(st.session_state.analysis_text)
            st.markdown("---")
            for m in st.session_state.messages:
                with st.chat_message(m["role"]): st.markdown(m["content"])
            
            # ここの下の行まで確実にコピーしてください
            if q := st.chat_input("この予測をさらに深掘り..."):
                st.session_state.messages.append({"role": "user", "content": q})
                with st.chat_message("user"): st.markdown(q)
                with st.chat_message("assistant"):
                    if st.session_state.chat_session:
                        resp = st.session_state.chat_session.send_message(q)
                        st.markdown(resp.text)
                        st.session_state.messages.append({"role": "assistant", "content": resp.text})
                    else: st.error("分析を開始してください。")

