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
st.set_page_config(page_title="AI投資アナリスト・マルチ", layout="wide")
st.title("🌐 AI投資ニュース・精密マルチセクター分析")

# --- サイドバー設定 ---
api_key = st.sidebar.text_input("APIキーを入力してください", type="password")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🕒 取得範囲の設定")
hours_range = st.sidebar.slider("過去何時間分を取得しますか？", min_value=1, max_value=72, value=24)

# 【大幅強化】セクター細分化と複数選択
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔍 分析ターゲット（複数選択可）")
SECTOR_OPTIONS = [
    "防衛", "宇宙", "重工", "海運", "物流", "エネルギー", "資源・素材", 
    "半導体", "ハイテク・IT", "金融・銀行", "商社", "自動車", 
    "不動産", "電力・インフラ", "化学・素材"
]
selected_sectors = st.sidebar.multiselect(
    "注目するセクターを選んでください",
    options=SECTOR_OPTIONS,
    default=[] # 空の場合は「全体」として扱います
)

# もとみさんの監視銘柄リスト
default_stocks = "三菱重工, 川崎重工, IHI, ソニーg, ソニーfg, トヨタ, 任天堂, アストロスケール, 安川電機, 住友電工, 古河電気工業, フジクラ, 東レ, 本田技研, 日立製作所, 東北電力, シマノ, acsl, 日東電工, 三菱UFJ, サンリオ, KDDI, 川崎汽船, 商船三井, 日本郵船, 三菱hcキャピタル, 三菱ケミカル, 伊藤忠, 日東紡績, 三菱マテリアル, 小松製作所, 三菱商事, オリックス, 楽天グループ, 三井不動産, 三井物産, igポート, アドバンテスト, 東京エレクトロン, キーエンス, ファナック, 村田製作所, レーザーテック, イビデン, ディスコ, 信越化学工業, 第一生命, ヤマハ, 住友金属鉱山, エニーカラー, ソフトバンクg, キオクシア, 三井住友fg, みずほfg, QPSホールディングス, 名村造船所, カバー, inpex, ispace, スカパーjsat"

st.sidebar.markdown("---")
st.sidebar.markdown("### 📝 監視銘柄の編集")
stock_input = st.sidebar.text_area("銘柄リスト", value=default_stocks, height=150)
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
    """指定された時間以内のニュースを取得"""
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
                    "title": entry.title,
                    "summary": entry.get("summary", ""),
                    "link": entry.link,
                    "source": source_name,
                    "time": pub_time.astimezone(timezone(timedelta(hours=9))).strftime('%m/%d %H:%M') if pub_struct else "--:--"
                })
                seen_links.add(entry.link)
        except: continue
    return news_list

# 分析実行
button_label = f"選択した {len(selected_sectors)} セクターを分析" if selected_sectors else "全セクターを分析"
if st.sidebar.button(button_label):
    if not api_key:
        st.error("APIキーを入れてください！")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview") 
        
        with st.spinner("指定セクターを重点分析中..."):
            news_data = get_all_news(hours_range)
            st.session_state.fetched_news = news_data
            
            all_news_text = ""
            for i, n in enumerate(news_data):
                all_news_text += f"No.{i} [{n['source']}]: {n['title']}\n{n['summary']}\n\n"
            
            sector_target = ", ".join(selected_sectors) if selected_sectors else "全方位"
            
            prompt = f"""
            あなたはプロの投資アナリストです。
            
            【今回の重点分析ターゲット】
            {sector_target}
            
            【監視銘柄リスト】
            {', '.join(WATCHLIST)}
            
            【指示】
            1. ニュースリスト（No.0〜）を読み、上記のターゲットセクターおよび監視銘柄に関連する地政学リスクや重要情報を抽出してください。
            2. 見出しは必ず【銘柄名（証券コード）】とし、監視銘柄を最優先してください。
            3. 監視銘柄以外でも、上記ターゲットに関連する重要な動きがあれば、代表銘柄を推測して分析に含めてください。
            4. 各銘柄ごとに「事実」「地政学的な意味」「株価への影響（ポジネガ）」を端的に記載。
            5. 挨拶は不要。
            
            【ニュースリスト】
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
        st.subheader(f"📰 元記事リスト ({len(st.session_state.fetched_news)}件)")
        for i, n in enumerate(st.session_state.fetched_news):
            with st.expander(f"No.{i}: 📌 [{n['time']}] {n['title']}"):
                st.caption(f"ソース: {n['source']}")
                st.write(n['summary'])
                st.link_button("記事全文", n['link'])
    with col2:
        st.subheader("🤖 AI 深層分析結果")
        with st.spinner("音声を生成中..."):
            try:
                audio_bytes = asyncio.run(generate_voice(st.session_state.analysis_text))
                st.audio(audio_bytes, format='audio/mp3')
            except: st.warning("音声生成に失敗しました。")
        st.write(st.session_state.analysis_text)
        
        st.markdown("---")
        st.subheader("💬 チャットで深掘り")
        for m in st.session_state.messages:
            with st.chat_message(m["role"]): st.markdown(m["content"])
        if q := st.chat_input("この分析についてさらに詳しく聞きたいことは？"):
            st.session_state.messages.append({"role": "user", "content": q})
            with st.chat_message("user"): st.markdown(q)
            with st.chat_message("assistant"):
                res = st.session_state.chat_session.send_message(q)
                st.markdown(res.text)
            st.session_state.messages.append({"role": "assistant", "content": res.text})
