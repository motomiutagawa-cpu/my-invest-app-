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
with st.sidebar.expander("🔍 注目セクターを選択", expanded=False):
    SECTOR_OPTIONS = ["防衛", "宇宙", "重工", "海運", "物流", "エネルギー", "資源・素材", "半導体", "ハイテク・AI", "金融・銀行", "商社", "自動車", "不動産", "電力・インフラ", "化学・素材"]
    col_s1, col_s2 = st.columns(2)
    if col_s1.button("全選択", key="sec_all"):
        for s in SECTOR_OPTIONS: st.session_state[f"sec_{s}"] = True
    if col_s2.button("全解除", key="sec_none"):
        for s in SECTOR_OPTIONS: st.session_state[f"sec_{s}"] = False
    selected_sectors = [s for s in SECTOR_OPTIONS if st.checkbox(s, key=f"sec_{s}", value=st.session_state.get(f"sec_{s}", False))]

# --- 銘柄を絞る（直接入力） ---
st.sidebar.markdown("---")
st.sidebar.markdown("### 🎯 銘柄を絞る")
narrow_stocks = st.sidebar.text_area(
    "銘柄名や証券コードを入力",
    placeholder="例: 7011, ソニー, NVIDIA\n空欄なら注目銘柄＋材料株を分析",
    help="入力がある場合、その銘柄のみを分析します。"
)

# もとみさんの精鋭マスターリスト（内部保持用）
CORE_WATCHLIST = {
    "日本株": "ソニーg, ソニーfg, アストロスケール, QPSホールディングス, acsl, 三菱重工, 川崎重工, ihi, 安川電機, 住友電工, 古河電気工業, フジクラ, 日本郵船, 商船三井, 川崎汽船, 日東電工, 東レ, シマノ, 三菱UFJ, みずほフィナンシャルグループ, 三井物産, 三菱商事, kddi, 東北電力, 九州電力, 任天堂, カバー, トヨタ, ホンダ, 日立製作所, サンリオ, inpex",
    "米国株": "Apple, NVIDIA, Alphabet, Amazon, Tesla, Microsoft, Meta, Palantir, Rocket Lab, Broadcom, Berkshire Hathaway",
    "先物・商品": "日経225先物, NYダウ先物, ナスダック100先物, WTI原油先物, 金先物(Gold), 米国債10年",
    "FX・為替": "USD/JPY, EUR/JPY, GBP/JPY, AUD/JPY, EUR/USD"
}

# セッション状態
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
    prompt = f"投資家視点で3行要約し、株価材料（ポジネガ）を判定せよ。免責文や挨拶は不要。\n【タイトル】: {title}\n【本文】: {summary}"
    try:
        response = model.generate_content(prompt)
        return response.text
    except: return "要約エラー"

# --- メイン分析実行 ---
if st.sidebar.button(f"{market_choice} 分析を開始"):
    if not api_key: st.error("APIキーを入れてください。")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
        with st.spinner("ニュースと市場材料を精査中..."):
            news_data = get_all_news(hours_range)
            st.session_state.fetched_news = news_data
            st.session_state.individual_summaries = {}
            st.session_state.messages = []
            all_news_text = ""
            for i, n in enumerate(news_data):
                all_news_text += f"No.{i}: {n['title']}\n{n['summary']}\n\n"
            
            # ロジックの分岐指示
            if narrow_stocks:
                analysis_policy = f"【銘柄指定あり】リストにある銘柄「{narrow_stocks}」だけに集中して、ニュースに関連があれば分析してください。それ以外の無関係な銘柄は一切不要です。"
            else:
                analysis_policy = f"【銘柄指定なし】私の注目銘柄（{CORE_WATCHLIST.get(market_choice)}）を中心に分析してください。さらに、それ以外の銘柄でも「個別材料（決算、修正、提携等）」が出ているものはすべて積極的に拾い上げて報告してください。"

            prompt = f"""
            あなたは伝説の投資アナリストです。挨拶や「自己責任」等の免責文は一切書くな。
            
            【絶対指示】
            1. {analysis_policy}
            2. 各項目の文末に必ず根拠番号「(No.Xより)」を明記せよ。
            3. セクター（{', '.join(selected_sectors)}）に関連する重要な動きも逃さず捉えよ。
            
            見出しを【銘柄名(コード)】とし、「事実」「意味」「ポジネガ」を端的に記載せよ。
            
            ニュースリスト:
            {all_news_text}
            """
            try:
                chat = model.start_chat(history=[])
                response = chat.send_message(prompt)
                st.session_state.analysis_text = response.text
                st.session_state.chat_session = chat
            except Exception as e: st.error(f"分析エラー: {e}")

# --- 表示エリア（独立スクロール） ---
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
        st.subheader("🤖 AI分析・深掘りチャット")
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
            
            if q := st.chat_input("この結果についてさらに詳しく聞く..."):
                st.session_state.messages.append({"role": "user", "content": q})
                with st.chat_message("user"): st.markdown(q)
                with st.chat_message("assistant"):
                    if st.session_state.chat_session:
                        resp = st.session_state.chat_session.send_message(q)
                        st.markdown(resp.text)
                        st.session_state.messages.append({"role": "assistant", "content": resp.text})
                    else: st.error("分析を先に開始してください。")
