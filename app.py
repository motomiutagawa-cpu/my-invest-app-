import streamlit as st
import feedparser
import google.generativeai as genai
import asyncio
import edge_tts
import io
from datetime import datetime, timedelta, timezone
import time

# 画面設定
st.set_page_config(page_title="AI投資アナリスト・プロ", layout="wide")

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

# --- セクター選択（キーボードが出ないチェックボックス） ---
st.sidebar.markdown("---")
with st.sidebar.expander("🔍 注目セクターを選択", expanded=True):
    SECTOR_OPTIONS = ["防衛", "宇宙", "重工", "海運", "物流", "エネルギー", "資源・素材", "半導体", "ハイテク・AI", "金融・銀行", "商社", "自動車", "不動産", "電力・インフラ", "化学・素材"]
    col_s1, col_s2 = st.columns(2)
    if col_s1.button("全選択", key="sec_all"):
        for s in SECTOR_OPTIONS: st.session_state[f"sec_{s}"] = True
    if col_s2.button("全解除", key="sec_none"):
        for s in SECTOR_OPTIONS: st.session_state[f"sec_{s}"] = False
    selected_sectors = [s for s in SECTOR_OPTIONS if st.checkbox(s, key=f"sec_{s}", value=st.session_state.get(f"sec_{s}", False))]

# --- 【新機能】銘柄を絞る（直接入力） ---
st.sidebar.markdown("---")
st.sidebar.markdown("### 🎯 銘柄を絞る")
narrow_stocks = st.sidebar.text_area(
    "銘柄名や証券コードを入力（空欄なら全体分析）",
    placeholder="例: 7011, 三菱重工, NVIDIA",
    help="ここに打った銘柄を最優先で分析します。"
)

# セッション状態の管理
if "analysis_text" not in st.session_state: st.session_state.analysis_text = None
if "fetched_news" not in st.session_state: st.session_state.fetched_news = []
if "individual_summaries" not in st.session_state: st.session_state.individual_summaries = {}
if "messages" not in st.session_state: st.session_state.messages = []
if "chat_session" not in st.session_state: st.session_state.chat_session = None

# --- 関数群 ---
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
                news_list.append({
                    "title": entry.title,
                    "summary": entry.get("summary", ""),
                    "link": entry.link,
                    "source": "Yahoo" if "yahoo" in url else "ロイター" if "reuters" in url else "PR TIMES",
                    "time": pub_time.astimezone(timezone(timedelta(hours=9))).strftime('%m/%d %H:%M') if pub_struct else "--:--"
                })
                seen_links.add(entry.link)
        except: continue
    return news_list

def analyze_single_article(title, summary):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
    prompt = f"投資家視点で3行要約し、株価材料としてのポジネガを判定せよ。免責文や挨拶は不要。\n【タイトル】: {title}\n【本文】: {summary}"
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"要約エラー: {e}"

# --- メイン分析実行 ---
if st.sidebar.button(f"{market_choice} 分析を開始"):
    if not api_key: st.error("APIキーを入れてください。")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
        with st.spinner("ニュースと材料株を精査中..."):
            news_data = get_all_news(hours_range)
            st.session_state.fetched_news = news_data
            st.session_state.individual_summaries = {}
            st.session_state.messages = []
            all_news_text = ""
            for i, n in enumerate(news_data):
                all_news_text += f"No.{i}: {n['title']}\n{n['summary']}\n\n"
            
            prompt = f"""
            あなたは伝説の投資アナリストです。挨拶や「自己責任」等の定型文は一切不要。
            
            【絶対指示】
            1. 「絞り込み銘柄」に指定がある場合は、それらを最優先で徹底分析してください。
            2. それ以外でも、ニュースリスト内で個別銘柄の「材料（決算、提携、上方修正、新技術、自社株買い等）」が出ている場合は、指定に関わらず必ずすべて抽出して分析してください。
            3. 文末に必ず根拠番号「(No.Xより)」を明記してください。
            
            【今回のターゲット】
            市場: {market_choice}
            重点セクター: {', '.join(selected_sectors)}
            絞り込み銘柄: {narrow_stocks if narrow_stocks else '未指定（全体を分析）'}
            
            銘柄名を見出しにし、「事実」「意味」「ポジネガ」を端的に記載せよ。
            
            ニュースリスト:
            {all_news_text}
            """
            try:
                chat = model.start_chat(history=[])
                response = chat.send_message(prompt)
                st.session_state.analysis_text = response.text
                st.session_state.chat_session = chat
            except Exception as e: st.error(f"分析エラー: {e}")

# --- 画面表示（独立スクロール） ---
if st.session_state.analysis_text:
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("📊 ニュースフィード")
        with st.container(height=800):
            for i, n in enumerate(st.session_state.fetched_news):
                with st.expander(f"No.{i}: 📌 [{n['time']}] {n['title']}"):
                    st.write(n['summary'])
                    if st.button(f"✨ AI要約 (No.{i})", key=f"btn_{i}"):
                        with st.spinner("要約中..."):
                            st.session_state.individual_summaries[i] = analyze_single_article(n['title'], n['summary'])
                    if i in st.session_state.individual_summaries:
                        st.info(st.session_state.individual_summaries[i])
                    st.link_button("全文へ", n['link'])
                
    with col2:
        st.subheader("🤖 AI深層分析 ＆ チャット")
        # 右側のスクロールエリア
        with st.container(height=800):
            with st.spinner("音声を生成中..."):
                try:
                    audio_bytes = asyncio.run(generate_voice(st.session_state.analysis_text))
                    st.audio(audio_bytes, format='audio/mp3')
                except: st.warning("音声生成エラー")
            
            st.write(st.session_state.analysis_text)
            st.markdown("---")
            
            # チャット履歴
            for m in st.session_state.messages:
                with st.chat_message(m["role"]): st.markdown(m["content"])
            
            # 【復旧】チャット入力欄
            # st.chat_inputはコンテナ内でも動作しますが、スクロール最下部に配置
            if q := st.chat_input("この分析についてさらに詳しく聞く..."):
                st.session_state.messages.append({"role": "user", "content": q})
                with st.chat_message("user"): st.markdown(q)
                with st.chat_message("assistant"):
                    if st.session_state.chat_session:
                        resp = st.session_state.chat_session.send_message(q)
                        st.markdown(resp.text)
                        st.session_state.messages.append({"role": "assistant", "content": resp.text})
                    else:
                        st.error("分析を先に開始してください。")
