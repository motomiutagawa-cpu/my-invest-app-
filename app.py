import streamlit as st
import feedparser
import google.generativeai as genai

# 画面の基本設定
st.set_page_config(page_title="AI投資ダッシュボード", layout="wide")
st.title("📊 最新ニュース＆AIポジネガ判定")

# 左側のサイドバー
api_key = st.sidebar.text_input("Google AI StudioのAPIキーを入力", type="password")

# 監視銘柄のデフォルトリスト
default_stocks = "三菱重工, 川崎重工, IHI, ソニーg, ソニーfg, 任天堂, アストロスケール, 安川電機, 住友電工, 古河電気工業, フジクラ, 東レ, 本田技研, 日立製作所, 東北電力, シマノ, acsl, 日東電工, 三菱UFJ, サンリオ, KDDI, 川崎汽船, 商船三井, 日本郵船, VALUENEX, 三菱hcキャピタル, 三菱ケミカル, 伊藤忠, 日東紡績, 三菱マテリアル, 小松製作所, 三菱商事, オリックス, 楽天グループ, ディー・エヌ・エー, 三井不動産, 三井物産, igポート, Liberaware, メタプラネット, アドバンテスト, 東京エレクトロン, キーエンス, ファナック, 村田製作所, レーザーテック, イビデン, ディスコ, 信越化学工業, 第一生命, ヤマハ, 住友金属鉱山, エニーカラー, ソフトバンク, ソフトバンクg, キオクシア, 三井住友fg, みずほfg, 東邦銀行, アルコニックス, レンゴー, 楽天銀行, 細谷火工, QPSホールディングス, ブルーイノベーション, 名村造船所, カバー, inpex, ispace, スカパーjsat"

st.sidebar.markdown("---")
st.sidebar.markdown("### 📝 監視銘柄の編集")
stock_input = st.sidebar.text_area("カンマ(,)区切りで自由に追加・削除できます", value=default_stocks, height=300)
WATCHLIST = [stock.strip() for stock in stock_input.split(",") if stock.strip()]

# --- アプリの記憶領域（チャットや分析結果を保持するため） ---
if "news_items" not in st.session_state:
    st.session_state.news_items = None
if "analysis_text" not in st.session_state:
    st.session_state.analysis_text = None
if "chat_session" not in st.session_state:
    st.session_state.chat_session = None
if "messages" not in st.session_state:
    st.session_state.messages = []

def get_news():
    """RSSを利用してニュースを取得する関数"""
    rss_urls = ["https://news.yahoo.co.jp/rss/topics/business.xml"]
    target_news = []
    for url in rss_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries[:30]: 
            if any(stock in entry.title for stock in WATCHLIST):
                target_news.append({"title": entry.title, "link": entry.link})
    return target_news

# 「分析開始」ボタンが押された時の処理
if st.sidebar.button("ニュースを取得＆分析"):
    if not api_key:
        st.error("左側のメニューにAPIキーを入力してください。")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-pro") 

        with st.spinner("ニュースを収集中..."):
            news = get_news()
            st.session_state.news_items = news

        if not news:
            st.session_state.analysis_text = "※上記以外の銘柄については、本日特筆すべき個別材料はありません（全体相場・マクロ要因に連動して推移）"
            st.session_state.chat_session = None
        else:
            news_text_for_ai = "\n".join([f"・{item['title']}" for item in news])
            
            # --- プロンプトに地政学リスクの条件を追加 ---
            prompt = f"""
            以下のニュースの見出しリストから、投資判断に直結する分析を行ってください。
            
            【ニュースリスト】
            {news_text_for_ai}
            
            【出力ルール】
            セクター単位でのまとめではなく、「個別銘柄名」を見出しにして一つずつ記載すること。
            決算発表、業績修正、株式分割、自社株買い、業務提携、新技術の発表、アナリストのレーティング変更、配当落ちなど、その企業単独の材料を優先して抽出すること。
            各ニュースの事実を端的に記載し、最後にその材料が株価に与える影響（ポジティブかネガティブか）を1〜2行で客観的に添えること。
            ★重要★：その材料が「地政学リスク」の観点から見て好材料か悪材料か（あるいは影響なしか）についても、必ず明確に言及すること。
            投資判断に不要な前置きや挨拶は一切省き、すぐにニュースの一覧から出力すること。
            """
            
            with st.spinner("AIがポジネガ判定＆地政学リスクを分析中..."):
                try:
                    # AIとのチャットセッションを開始（記憶を持たせる）
                    chat = model.start_chat(history=[])
                    response = chat.send_message(prompt, generation_config={"temperature": 0.0})
                    
                    st.session_state.analysis_text = response.text
                    st.session_state.chat_session = chat
                    st.session_state.messages = [] # 新しい分析のたびにチャット履歴をリセット
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")

# --- 分析結果とチャット画面の表示 ---
if st.session_state.news_items is not None:
    if not st.session_state.news_items:
        st.info(st.session_state.analysis_text)
    else:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("📰 関連ニュース一覧")
            for item in st.session_state.news_items:
                st.markdown(f"- [{item['title']}]({item['link']})")
        
        with col2:
            st.subheader("🤖 AI分析結果")
            st.write(st.session_state.analysis_text)
            
            st.markdown("---")
            st.subheader("💬 分析結果について深掘りする")
            
            # これまでのチャット履歴を表示
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
            
            # チャットの入力フォーム
            if user_question := st.chat_input("例：この記事の地政学リスクは中期的にどう影響する？"):
                # ユーザーの質問を表示・保存
                st.session_state.messages.append({"role": "user", "content": user_question})
                with st.chat_message("user"):
                    st.markdown(user_question)
                
                # AIの回答を生成・表示・保存
                with st.chat_message("assistant"):
                    with st.spinner("考え中..."):
                        response = st.session_state.chat_session.send_message(user_question)
                        st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
