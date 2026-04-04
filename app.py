import streamlit as st
import feedparser
import google.generativeai as genai

# 画面設定
st.set_page_config(page_title="AI投資アナリスト・プロ", layout="wide")
st.title("🌐 マルチソース・AI投資ニュース分析")

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

def get_all_news():
    """Yahoo, ロイター, PR TIMESからニュースを統合して取得"""
    rss_urls = [
        "https://news.yahoo.co.jp/rss/topics/business.xml", # Yahooビジネス
        "https://news.yahoo.co.jp/rss/topics/world.xml",    # Yahoo国際
        "https://jp.reuters.com/rss/businessNews",          # ロイター・ビジネス
        "https://jp.reuters.com/rss/worldNews",             # ロイター・世界
        "https://prtimes.jp/index.rdf"                      # PR TIMES (企業プレスリリース)
    ]
    news_list = []
    seen_titles = set() # 重複ニュースを弾く

    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            source_name = "Yahoo" if "yahoo" in url else "ロイター" if "reuters" in url else "PR TIMES"
            
            for entry in feed.entries[:15]: # 各ソースから上位15件
                # 似たような見出しの重複を避ける
                if entry.title[:15] in seen_titles: 
                    continue
                
                news_list.append({
                    "title": entry.title,
                    "summary": entry.get("summary", ""),
                    "link": entry.link,
                    "source": source_name
                })
                seen_titles.add(entry.title[:15])
        except:
            continue
            
    return news_list

# 分析実行ボタン
if st.sidebar.button("多角的なニュースをAIに丸投げ"):
    if not api_key:
        st.error("APIキーを入れてください！")
    else:
        genai.configure(api_key=api_key)
        # もとみさんの環境で唯一成功した魔法のモデル
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview") 
        
        with st.spinner("Yahoo, ロイター, PR TIMESを精査中..."):
            news_data = get_all_news()
            st.session_state.fetched_news = news_data
            
            all_news_text = ""
            for i, n in enumerate(news_data):
                all_news_text += f"No.{i} [{n['source']}]: 【見出し】: {n['title']}\n【概要】: {n['summary']}\n\n"
            
            prompt = f"""
            あなたはプロの投資アナリストです。
            複数のソース（Yahoo, ロイター, PR TIMES）から集まったニュースを精査し、私の【監視銘柄リスト】に関連する材料や、地政学リスク等の重要情報を抽出して分析してください。
            
            【監視銘柄リスト】
            {', '.join(WATCHLIST)}
            
            【ニュースリスト】
            {all_news_text}
            
            【分析ルール】
            1. 特に「地政学リスク」と「個別企業の独占材料（新技術・提携等）」を最優先。
            2. 各銘柄（またはセクター）に対し、事実・地政学的な意味・株価へのポジネガを客観的に記載。
            3. PR TIMES等のプレスリリースがあれば、企業の将来性に直結する投資判断として評価すること。
            4. 挨拶は不要。
            """
            
            try:
                chat = model.start_chat(history=[])
                response = chat.send_message(prompt)
                st.session_state.analysis_text = response.text
                st.session_state.chat_session = chat
                st.session_state.messages = []
            except Exception as e:
                st.error(f"分析中にエラーが発生しました: {e}")

# --- 表示部分 ---
if st.session_state.analysis_text:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📰 統合ニュースフィード")
        st.caption("Yahoo / Reuters / PR TIMES から取得")
        for n in st.session_state.fetched_news:
            # ソースごとにバッジの色を変える
            source_tag = f"[{n['source']}]"
            with st.expander(f"📌 {source_tag} {n['title']}"):
                st.write(n['summary'])
                st.link_button("記事全文を読む", n['link'])

    with col2:
        st.subheader("🤖 AIによる多角的分析")
        st.write(st.session_state.analysis_text)
        
        st.markdown("---")
        st.subheader("💬 この結果をさらに深掘り")
        for m in st.session_state.messages:
            with st.chat_message(m["role"]): st.markdown(m["content"])
        
        if q := st.chat_input("この中東リスク、海運株にはいつまで影響しそう？"):
            st.session_state.messages.append({"role": "user", "content": q})
            with st.chat_message("user"): st.markdown(q)
            with st.chat_message("assistant"):
                res = st.session_state.chat_session.send_message(q)
                st.markdown(res.text)
            st.session_state.messages.append({"role": "assistant", "content": res.text})
