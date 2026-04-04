import streamlit as st
import feedparser
import google.generativeai as genai

# 画面設定
st.set_page_config(page_title="AI投資アナリスト", layout="wide")
st.title("🌐 AI投資ニュース・プロ分析")

# サイドバー設定
api_key = st.sidebar.text_input("APIキーを再入力してください", type="password")

default_stocks = "三菱重工, 川崎重工, IHI, ソニーg, ソニーfg, 任天堂, アストロスケール, 安川電機, 住友電工, フジクラ, 東レ, 本田技研, 日立製作所, 東北電力, シマノ, acsl, 日東電工, 三菱UFJ, サンリオ, KDDI, 川崎汽船, 商船三井, 日本郵船, VALUENEX, 三菱hcキャピタル, 伊藤忠, 日東紡績, 三菱商事, オリックス, 楽天グループ, 三井物産, メタプラネット, アドバンテスト, 東京エレクトロン, キーエンス, レーザーテック, ディスコ, 信越化学工業, ソフトバンクg, キオクシア, みずほfg, QPSホールディングス, 名村造船所, カバー, inpex, ispace, スカパーjsat"

st.sidebar.markdown("---")
st.sidebar.markdown("### 📝 監視銘柄の編集")
stock_input = st.sidebar.text_area("銘柄リスト", value=default_stocks, height=250)
WATCHLIST = [s.strip() for s in stock_input.replace("、", ",").split(",") if s.strip()]

if "messages" not in st.session_state: st.session_state.messages = []
if "analysis_text" not in st.session_state: st.session_state.analysis_text = None

def get_all_news():
    """主要ニュースをフィルタリングせずに全部持ってくる"""
    rss_urls = [
        "https://news.yahoo.co.jp/rss/topics/business.xml",
        "https://news.yahoo.co.jp/rss/topics/world.xml"
    ]
    all_items = []
    for url in rss_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries[:20]:
            all_items.append(f"【見出し】: {entry.title}\n【概要】: {entry.get('summary', '')}\n")
    return "\n".join(all_items)

# 分析実行ボタン
if st.sidebar.button("AIに全ニュースを精査させる"):
    if not api_key:
        st.error("左のメニューにAPIキーを入れてください！")
    else:
        genai.configure(api_key=api_key)
        # もとみさんの環境で動く魔法のモデル
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview") 
        
        with st.spinner("AIが全ニュースから『お宝材料』を抽出中..."):
            all_news_text = get_all_news()
            
            prompt = f"""
            あなたはプロの投資アナリストです。
            以下の最新ニュースリストを全て読み、私の【監視銘柄リスト】に関連するニュース、または「地政学リスク」「マクロ経済」の観点から日本株全体に影響を与える重要なニュースだけを厳選して分析してください。
            
            【監視銘柄リスト】
            {', '.join(WATCHLIST)}
            
            【ニュースリスト】
            {all_news_text}
            
            【出力ルール】
            1. 関連するニュースがない場合は「特筆すべき材料はありません」と出力すること。
            2. 関連がある場合は、銘柄名（またはセクター名）を見出しにし、ニュースの事実、地政学的な意味合い、株価へのポジネガ（1-2行）を端的に記載すること。
            3. 挨拶や導入文は一切不要。
            """
            
            try:
                chat = model.start_chat(history=[])
                response = chat.send_message(prompt)
                st.session_state.analysis_text = response.text
                st.session_state.chat_session = chat
                st.session_state.messages = []
            except Exception as e:
                st.error(f"エラー: {e}")

# 分析結果表示
if st.session_state.analysis_text:
    st.subheader("🤖 AIによる厳選インパクト分析")
    st.write(st.session_state.analysis_text)
    
    st.markdown("---")
    st.subheader("💬 この結果について深掘り質問")
    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])
    
    if q := st.chat_input("例：ホルムズ海峡の緊張はいつまで続く？"):
        st.session_state.messages.append({"role": "user", "content": q})
        with st.chat_message("user"): st.markdown(q)
        with st.chat_message("assistant"):
            res = st.session_state.chat_session.send_message(q)
            st.markdown(res.text)
        st.session_state.messages.append({"role": "assistant", "content": res.text})
