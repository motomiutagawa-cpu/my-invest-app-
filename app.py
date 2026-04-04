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
st.set_page_config(page_title="AI投資アナリスト・エグゼクティブ", layout="wide")

st.title("🌐 AI投資ニュース・プロ分析（株価・連想分析版）")

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
st.sidebar.markdown("### 🎯 銘柄を絞る（証券コード推奨）")
narrow_stocks = st.sidebar.text_area(
    "銘柄名や証券コードを入力",
    placeholder="例: 7011, ソニー, NVDA\n空欄なら注目銘柄＋材料株を分析",
    help="日本株は4桁コード、米国株はティッカーを入力すると株価取得が正確になります。"
)

# もとみさんの精鋭マスターリスト（内部保持用）
CORE_WATCHLIST = {
    "日本株": "ソニーg(6758), ソニーfg(8729), アストロスケール(186A), QPSホールディングス(5595), acsl(6767), 三菱重工(7011), 川崎重工(7012), ihi(7013), 安川電機(6506), 住友電工(5802), 古河電気工業(5801), フジクラ(5803), 日本郵船(9101), 商船三井(9104), 川崎汽船(9107), 日東電工(6988), 東レ(3402), シマノ(7309), 三菱UFJ(8306), みずほフィナンシャルグループ(8411), 三井物産(8031), 三菱商事(8058), kddi(9433), 東北電力(9506), 九州電力(9508), 任天堂(7974), カバー(5253), トヨタ(7203), ホンダ(7267), 日立製作所(6501), サンリオ(8136), inpex(1605)",
    "米国株": "Apple(AAPL), NVIDIA(NVDA), Alphabet(GOOGL), Amazon(AMZN), Tesla(TSLA), Microsoft(MSFT), Meta(META), Palantir(PLTR), Rocket Lab(RKLB), Broadcom(AVGO), Berkshire Hathaway(BRK-B)",
    "先物・商品": "日経225先物(^NK225), NYダウ先物(^DJI), ナスダック100先物(^IXIC), WTI原油先物(CL=F), 金先物(GC=F), 米国債10年(^TNX)",
    "FX・為替": "USD/JPY=X, EUR/JPY=X, GBP/JPY=X, AUD/JPY=X, EUR/USD=X"
}

# セッション状態
if "analysis_text" not in st.session_state: st.session_state.analysis_text = None
if "fetched_news" not in st.session_state: st.session_state.fetched_news = []
if "individual_summaries" not in st.session_state: st.session_state.individual_summaries = {}
if "messages" not in st.session_state: st.session_state.messages = []
if "chat_session" not in st.session_state: st.session_state.chat_session = None

# --- 株価取得関数 ---
def get_price_info(stock_str, market):
    """銘柄名/コードから株価と騰落率を取得"""
    items = [s.strip() for s in stock_str.replace("、", ",").split(",") if s.strip()]
    price_data = ""
    for item in items:
        ticker_symbol = item
        if market == "日本株" and item.isdigit() and len(item) == 4:
            ticker_symbol = f"{item}.T"
        elif market == "米国株":
            ticker_symbol = item.upper()
        
        try:
            tk = yf.Ticker(ticker_symbol)
            info = tk.history(period="2d")
            if len(info) >= 2:
                cur_price = info['Close'].iloc[-1]
                prev_price = info['Close'].iloc[-2]
                change = ((cur_price - prev_price) / prev_price) * 100
                price_data += f"・{item}: {cur_price:,.1f} ({change:+.2f}%)\n"
            else:
                price_data += f"・{item}: 株価取得不可\n"
        except:
            price_data += f"・{item}: 検索失敗\n"
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

# --- メイン分析実行 ---
if st.sidebar.button(f"{market_choice} 分析を開始"):
    if not api_key: st.error("APIキーを入れてください。")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
        with st.spinner("株価データとニュースを照合中..."):
            news_data = get_all_news(hours_range)
            st.session_state.fetched_news = news_data
            
            # 株価情報の取得
            target_for_price = narrow_stocks if narrow_stocks else CORE_WATCHLIST.get(market_choice)
            current_market_prices = get_price_info(target_for_price, market_choice)
            
            all_news_text = ""
            for i, n in enumerate(news_data):
                all_news_text += f"No.{i}: {n['title']}\n{n['summary']}\n\n"
            
            if narrow_stocks:
                analysis_policy = f"【銘柄限定モード】指定銘柄「{narrow_stocks}」を徹底的に深掘りせよ。直接的なニュースがない場合でも、為替、金利、他社動向、地政学リスクからの『連想・間接的な影響』を必ず考察せよ。"
            else:
                analysis_policy = f"【全体モード】注目銘柄（{CORE_WATCHLIST.get(market_choice)}）を軸に分析せよ。材料株のディスカバリーも行え。"

            prompt = f"""
            あなたは機関投資家レベルの凄腕アナリストです。
            挨拶、免責事項、自己責任等の定型文は一切禁止。
            
            【現在の株価データ】
            {current_market_prices}
            
            【絶対ルール】
            1. {analysis_policy}
            2. 「材料がないから中立」という回答はプロとして失格。他セクターの動きやマクロ指標から、その銘柄にどう波及するかを必ず論理的に推測せよ。
            3. 現在の株価推移を考慮し、「テクニカル的な視点（トレンド、警戒ライン等）」も予測に含めよ。
            4. 文末に根拠番号「(No.Xより)」を明記せよ。
            
            見出しを【銘柄名(コード) | 株価 | 前日比】とし、「事実」「間接的影響・連想」「テクニカル/今後の予測」「ポジネガ」を端的に記載せよ。
            
            ニュースリスト:
            {all_news_text}
            """
            try:
                chat = model.start_chat(history=[])
                response = chat.send_message(prompt)
                st.session_state.analysis_text = response.text
                st.session_state.chat_session = chat
                st.session_state.messages = []
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
                    st.link_button("全文へ", n['link'])
                
    with col2:
        st.subheader("🤖 AI深層分析（連想・テクニカル）")
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
            
            if q := st.chat_input("このテクニカル予測の根拠を詳しく..."):
                st.session_state.messages.append({"role": "user", "content": q})
                with st.chat_message("user"): st.markdown(q)
                with st.chat_message("assistant"):
                    resp = st.session_state.chat_session.send_message(q)
                    st.markdown(resp.text)
                    st.session_state.messages.append({"role": "assistant", "content": resp.text})
