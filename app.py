import streamlit as st
import feedparser
import google.generativeai as genai
import asyncio
import edge_tts
import io

# 画面設定
st.set_page_config(page_title="AI投資アナリスト・プロ", layout="wide")
st.title("🌐 AI投資ニュース・プロ分析（1.5倍速対応版）")

# サイドバー設定
api_key = st.sidebar.text_input("APIキーを入力してください", type="password")

default_stocks = "三菱重工, 川崎重工, IHI, ソニーg, ソニーfg, 任天堂, アストロスケール, 安川電機, 住友電工, フジクラ, 東レ, 本田技研, 日立製作所, 東北電力, シマノ, acsl, 日東電工, 三菱UFJ, サンリオ, KDDI, 川崎汽船, 商船三井, 日本郵船, VALUENEX, 三菱hcキャピタル, 伊藤忠, 日東紡績, 三菱商事, オリックス, 楽天グループ, 三井物産, メタプラネット, アドバンテスト, 東京エレクトロン, キーエンス, レーザーテック, ディスコ, 信越化学工業, ソフトバンクg, キオクシア, みずほfg, QPSホールディングス, 名村造船所, カバー, inpex, ispace, スカパーjsat"

st.sidebar.markdown("---")
st.sidebar.markdown("### 📝 監視銘柄の編集")
stock_input = st.sidebar.text_area("銘柄リスト", value=default_stocks, height=250)
WATCHLIST = [s.strip() for s in stock_input.replace("、", ",").split(",") if s.strip()]

# セッション状態の初期化
if "messages" not in st.session_state: st.session_state.messages = []
if "analysis_text" not in st.session_state: st.session_state.analysis_text = None
if "fetched_news" not in st.session_state: st.session_state.fetched_news = []

async def generate_voice(text):
    """音声を1.5倍速で生成する関数"""
    # ja-JP-NanamiNeuralは聞き取りやすい女性の声です。rate="+50%"で1.5倍速になります。
    communicate = edge_tts.Communicate(text, "ja-JP-NanamiNeural", rate="+50%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data

def get_all_news():
    """Yahoo, ロイター, PR TIMESからニュースを取得"""
    rss_urls = [
        "https://news.yahoo.co.jp/rss/topics/business.xml",
        "https://news.yahoo.co.jp/rss/topics/world.xml",
        "https://jp.reuters.com/rss/businessNews",
        "https://jp.reuters.com/rss/worldNews",
        "https://prtimes.jp/index.rdf"
    ]
    news_list = []
    seen_titles = set()
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            source_name = "Yahoo" if "yahoo" in url else "ロイター" if "reuters" in url else "PR TIMES"
            for entry in feed.entries[:15]:
                if entry.title[:15] in seen_titles: continue
                news_list.append({"title": entry.title, "summary": entry.get("summary", ""), "link": entry.link, "source": source_name})
                seen_titles.add(entry.title[:15])
        except: continue
    return news_list

# 分析実行ボタン
if st.sidebar.button("AI分析＆1.5倍速読み上げ"):
    if not api_key:
        st.error("APIキーを入れてください！")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview") 
        
        with st.spinner("最新情報を分析中..."):
            news_data = get_all_news()
            st.session_state.fetched_news = news_data
            all_news_text = ""
            for i, n in enumerate(news_data):
                all_news_text += f"No.{i} [{n['source']}]: {n['title']}\n{n['summary']}\n\n"
            
            prompt = f"あなたはプロの投資アナリストです。以下のニュースから監視銘柄に関連する地政学リスクや重要情報を抽出し、銘柄別に事実・意味・株価への影響を客観的に分析してください。\n\n{all_news_text}"
            
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
        st.subheader("📰 ニュースフィード")
        for n in st.session_state.fetched_news:
            with st.expander(f"📌 [{n['source']}] {n['title']}"):
                st.write(n['summary'])
                st.link_button("記事全文", n['link'])

    with col2:
        st.subheader("🤖 AI分析結果 (1.5倍速読み上げ)")
        
        # --- 音声生成（1.5倍速） ---
        with st.spinner("音声を生成中..."):
            try:
                audio_bytes = asyncio.run(generate_voice(st.session_state.analysis_text))
                st.audio(audio_bytes, format='audio/mp3')
            except Exception as e:
                st.warning("音声生成に失敗しました。")

        st.write(st.session_state.analysis_text)
        
        st.markdown("---")
        st.subheader("💬 チャットで深掘り")
        for m in st.session_state.messages:
            with st.chat_message(m["role"]): st.markdown(m["content"])
        
        if q := st.chat_input("この材料について詳しく！"):
            st.session_state.messages.append({"role": "user", "content": q})
            with st.chat_message("user"): st.markdown(q)
            with st.chat_message("assistant"):
                res = st.session_state.chat_session.send_message(q)
                st.markdown(res.text)
            st.session_state.messages.append({"role": "assistant", "content": res.text})
