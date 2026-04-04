import streamlit as st
import feedparser
import google.generativeai as genai

# 画面の基本設定
st.set_page_config(page_title="AI投資ダッシュボード", layout="wide")
st.title("📊 超広域・AI投資ニュース分析")

# 左側のサイドバー
api_key = st.sidebar.text_input("Google AI StudioのAPIキーを入力", type="password")

# 監視銘柄のデフォルトリスト
default_stocks = "三菱重工, 川崎重工, IHI, ソニーg, ソニーfg, 任天堂, アストロスケール, 安川電機, 住友電工, 古河電気工業, フジクラ, 東レ, 本田技研, 日立製作所, 東北電力, シマノ, acsl, 日東電工, 三菱UFJ, サンリオ, KDDI, 川崎汽船, 商船三井, 日本郵船, VALUENEX, 三菱hcキャピタル, 三菱ケミカル, 伊藤忠, 日東紡績, 三菱マテリアル, 小松製作所, 三菱商事, オリックス, 楽天グループ, ディー・エヌ・エー, 三井不動産, 三井物産, igポート, Liberaware, メタプラネット, アドバンテスト, 東京エレクトロン, キーエンス, ファナック, 村田製作所, レーザーテック, イビデン, ディスコ, 信越化学工業, 第一生命, ヤマハ, 住友金属鉱山, エニーカラー, ソフトバンク, ソフトバンクg, キオクシア, 三井住友fg,みずほfg, 東邦銀行, アルコニックス, レンゴー, 楽天銀行, 細谷火工, QPSホールディングス, ブルーイノベーション, 名村造船所, カバー, inpex, ispace, スカパーjsat"

st.sidebar.markdown("---")
st.sidebar.markdown("### 📝 監視銘柄・キーワード編集")
stock_input = st.sidebar.text_area("銘柄名やキーワード（例：海運,防衛,為替）を自由に追加できます", value=default_stocks, height=250)

# 全角・半角どちらのカンマでも分割できるように修正
WATCHLIST = [s.strip() for s in stock_input.replace("、", ",").split(",") if s.strip()]

# 地政学リスクを逃さないための自動追加キーワード
SYSTEM_KEYWORDS = ["海運", "防衛", "半導体", "地政学", "中東", "原油", "為替", "利上げ", "金利"]

# アプリの記憶領域
if "news_items" not in st.session_state:
    st.session_state.news_items = None
if "analysis_text" not in st.session_state:
    st.session_state.analysis_text = None
if "chat_session" not in st.session_state:
    st.session_state.chat_session = None
if "messages" not in st.session_state:
    st.session_state.messages = []

def get_news():
    """RSSからあらゆる情報をスキャンする"""
    rss_urls = [
        "https://news.yahoo.co.jp/rss/topics/business.xml",
        "https://news.yahoo.co.jp/rss/topics/world.xml" # 国際ニュースも追加
    ]
    
    target_news = []
    seen_links = set()
    
    search_terms = WATCHLIST + SYSTEM_KEYWORDS
    
    for url in rss_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            link = entry.get("link", "")
            
            # すでに取得済みのニュースはスキップ
            if link in seen_links:
                continue
                
            # タイトルまたは中身にキーワードが含まれているか
            content_to_scan = (title + summary).lower()
            if any(term.lower() in content_to_scan for term in search_terms):
                target_news.append({"title": title, "link": link, "summary": summary})
                seen_links.add(link)
    
    return target_news

# ボタン動作
if st.sidebar.button("最新ニュースを全スキャン＆分析"):
    if not api_key:
        st.error("APIキーを入力してください。")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview") 

        with st.spinner("経済・国際ニュースを広域スキャン中..."):
            news = get_news()
            st.session_state.news_items = news

        if not news:
            st.session_state.analysis_text = "※現時点で監視銘柄や関連セクターに影響するニュースは見つかりませんでした。"
            st.session_state.chat_session = None
        else:
            news_text_for_ai = ""
            for item in news:
                news_text_for_ai += f"【見出し】: {item['title']}\n【概要】: {item['summary']}\n\n"
            
            prompt = f"""
            以下のニュースリストを、プロの投資アナリストの視点で分析してください。
            
            【ニュースリスト】
            {news_text_for_ai}
            
            【分析の指示】
            1. リスト内の各ニュースが、監視銘柄（{', '.join(WATCHLIST[:10])}...等）や関連業界にどのような影響を与えるか特定してください。
            2. 特に「地政学リスク」や「マクロ経済」の観点から、日本の海運・防衛・製造業等へのインパクトを深く考察すること。
            3. 銘柄ごとにポジティブかネガティブかを明記し、理由を1-2行で添えること。
            
            挨拶や前置きは不要です。
            """
            
            with st.spinner("AIが深層分析中..."):
                try:
                    chat = model.start_chat(history=[])
                    response = chat.send_message(prompt, generation_config={"temperature": 0.0})
                    st.session_state.analysis_text = response.text
                    st.session_state.chat_session = chat
                    st.session_state.messages = [] 
                except Exception as e:
                    st.error(f"分析エラー: {e}")

# 表示部分
if st.session_state.news_items:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("📰 抽出された関連ニュース")
        for item in st.session_state.news_items:
            st.markdown(f"- [{item['title']}]({item['link']})")
    with col2:
        st.subheader("🤖 AIによる投資インパクト分析")
        st.write(st.session_state.analysis_text)
        st.markdown("---")
        st.subheader("💬 深掘り質問（地政学・業績への影響など）")
        for m in st.session_state.messages:
            with st.chat_message(m["role"]): st.markdown(m["content"])
        if q := st.chat_input("この状況はどのくらい続くと予想される？"):
            st.session_state.messages.append({"role": "user", "content": q})
            with st.chat_message("user"): st.markdown(q)
            with st.chat_message("assistant"):
                res = st.session_state.chat_session.send_message(q)
                st.markdown(res.text)
            st.session_state.messages.append({"role": "assistant", "content": res.text})
