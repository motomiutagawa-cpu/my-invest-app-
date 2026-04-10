import streamlit as st
import feedparser
import google.generativeai as genai
import asyncio
import edge_tts
import io
from datetime import datetime, timedelta, timezone
import time
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import requests

# 画面設定
st.set_page_config(page_title="AI投資アナリスト・もとみさん専用", layout="wide")

# --- 銘柄リスト ---
CORE_WATCHLIST = {
    "日本株": "三菱重工, 川崎重工, IHI, ソニーg, ソニーfg, トヨタ, 任天堂, アストロスケール, 安川電機, 住友電工, 古河電気工業, フジクラ, 東レ, 本田技研, 日立製作所, 東北電力, シマノ, acsl, 日東電工, 三菱UFJ, サンリオ, KDDI, 川崎汽船, 商船三井, 日本郵船, 三菱hcキャピタル, 三菱ケミカル, 伊藤忠, 日東紡績, 三菱マテリアル, 小松製作所, 三菱商事, オリックス, 楽天グループ, ディー・エヌ・エー, 三井不動産, 三井物産, igポート, Liberaware, メタプラネット, アドバンテスト, 東京エレクトロン, キーエンス, ファナック, 村田製作所, レーザーテック, イビデン, ディスコ, 信越化学工業, 第一生命, ヤマハ, 住友金属鉱山, エニーカラー, ソフトバンク, ソフトバンクg, キオクシア, 三井住友fg, みずほfg, 東邦銀行, アルコニックス, レンゴー, 楽天銀行, 細谷火工, QPSホールディングス, ブルーイノベーション, 名村造船所, カバー, inpex, ispace, スカパーjsat",
    "米国株": "AAPL, NVDA, GOOGL, AMZN, TSLA, MSFT, META, PLTR, RKLB, AVGO, BRK-B",
    "先物・商品": "^NK225, ^DJI, ^IXIC, CL=F, GC=F, ^TNX",
    "FX・為替": "USD/JPY, EUR/JPY, GBP/JPY, AUD/JPY, EUR/USD"
}

STOCK_NAME_MAP = {
    "三菱重工": "7011", "川崎重工": "7012", "ihi": "7013", "ソニーg": "6758", "ソニーfg": "5814",
    "トヨタ": "7203", "任天堂": "7974", "アストロスケール": "186A", "安川電機": "6506",
    "住友電工": "5802", "古河電気工業": "5801", "フジクラ": "5803", "東レ": "3402",
    "本田技研": "7267", "日立製作所": "6501", "東北電力": "9506", "シマノ": "7309",
    "三菱ufj": "8306", "サンリオ": "8136", "kddi": "9433", "川崎汽船": "9107",
    "商船三井": "9104", "日本郵船": "9101", "三菱商事": "8058", "アドバンテスト": "6857",
    "東京エレクトロン": "8035", "キーエンス": "6861", "レーザーテック": "6920",
    "エヌビディア": "NVDA", "アップル": "AAPL", "テスラ": "TSLA"
}

# --- 関数群 ---
def get_price_info(stock_str, market):
    items = [s.strip() for s in stock_str.replace("、", ",").split(",") if s.strip()]
    price_data = ""
    for item in items:
        raw_item = item.lower()
        ticker = STOCK_NAME_MAP.get(raw_item, item)
        if market == "日本株" and ticker.isdigit(): ticker = f"{ticker}.T"
        elif market == "FX・為替":
            ticker = ticker.replace("/", "") + "=X"
        try:
            df = yf.Ticker(ticker).history(period="2d")
            if len(df) >= 2:
                cur = df['Close'].iloc[-1]
                prev = df['Close'].iloc[-2]
                chg = ((cur - prev) / prev) * 100
                price_data += f"・{item}: {cur:,.1f} ({chg:+.2f}%)\n"
        except: continue
    return price_data

async def generate_voice(text):
    communicate = edge_tts.Communicate(text.replace("#", ""), "ja-JP-NanamiNeural", rate="+30%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": audio_data += chunk["data"]
    return audio_data

def get_all_news(hours):
    rss_urls = [
        "https://news.yahoo.co.jp/rss/topics/business.xml",
        "https://jp.reuters.com/rss/businessNews",
        "https://finance.yahoo.com/news/rssindex",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"
    ]
    news_list, seen = [], set()
    threshold = datetime.now(timezone.utc) - timedelta(hours=hours)
    for url in rss_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries[:30]:
            if entry.link in seen: continue
            news_list.append({
                "title": entry.title,
                "summary": entry.get("summary", ""),
                "link": entry.link,
                "source": "US" if "yahoo.com" in url or "cnbc" in url else "JP",
                "time": entry.get("published", "")
            })
            seen.add(entry.link)
    return news_list

def analyze_single_article(title, summary, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"投資家視点で要約し、影響を予測せよ。挨拶不要。\n【要約】3行\n【判定】ポジティブ/ネガティブ\n【タイトル】{title}\n【本文】{summary}"
    return model.generate_content(prompt).text

@st.cache_data(ttl=3600)
def get_stock_data(ticker, per):
    df = yf.Ticker(ticker).history(period=per)
    if df.empty: return None
    df['Change_Pct'] = df['Close'].pct_change() * 100
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['Color'] = df.apply(lambda r: '#00C896' if r['Close'] >= r['Open'] else '#F92855', axis=1)
    return df
# --- サイドバー ---
st.sidebar.markdown("### 🔄 アプリモード")
app_mode = st.sidebar.radio("ツール選択", ["📰 ニュース・相場分析", "📈 急変動チャートAI照合"])
api_key = st.sidebar.text_input("APIキー", type="password")

if app_mode == "📰 ニュース・相場分析":
    st.title("🌐 AI投資ニュース・プロ分析")
    market_choice = st.sidebar.radio("対象", ["日本株", "米国株", "先物・商品", "FX・為替"], horizontal=True)
    hours = st.sidebar.slider("取得時間", 1, 72, 24)
    narrow_stocks = st.sidebar.text_area("特定銘柄（最優先）")

    if "analysis_text" not in st.session_state: st.session_state.analysis_text = None
    if "fetched_news" not in st.session_state: st.session_state.fetched_news = []
    if "individual_summaries" not in st.session_state: st.session_state.individual_summaries = {}

    if st.sidebar.button("分析開始"):
        if not api_key: st.error("APIキーを入力してください")
        else:
            with st.spinner("情報を精査中..."):
                news_data = get_all_news(hours)
                st.session_state.fetched_news = news_data
                target_list = narrow_stocks if narrow_stocks else CORE_WATCHLIST[market_choice]
                prices = get_price_info(target_list, market_choice)
                news_text = "\n".join([f"No.{i}: {n['title']}\n{n['summary']}" for i, n in enumerate(news_data)])
                
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                prompt = f"プロのアナリストとして、{target_list}を中心に分析せよ。挨拶・免責不要。見出しは【銘柄名 | 現在値 | 騰落率】。判定とインパクトを断言せよ。\n価格データ:\n{prices}\nニュース:\n{news_text}"
                response = model.generate_content(prompt)
                st.session_state.analysis_text = response.text

    if st.session_state.analysis_text:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📊 ニュースフィード")
            for i, n in enumerate(st.session_state.fetched_news):
                with st.expander(f"No.{i}: [{n['source']}] {n['title']}"):
                    st.write(n['summary'])
                    if st.button(f"要約 (No.{i})", key=f"sum_{i}"):
                        st.session_state.individual_summaries[i] = analyze_single_article(n['title'], n['summary'], api_key)
                    if i in st.session_state.individual_summaries: st.info(st.session_state.individual_summaries[i])
                    st.link_button("全文へ", n['link'])
        with c2:
            st.subheader("🤖 AI戦略分析")
            if st.button("音声を再生"):
                audio = asyncio.run(generate_voice(st.session_state.analysis_text))
                st.audio(audio, format='audio/mp3')
            st.write(st.session_state.analysis_text)
elif app_mode == "📈 急変動チャートAI照合":
    st.title("📈 急変動チャート ＆ AIテクニカル予想")
    st.sidebar.markdown("### ⚙️ 設定")
    market_type = st.sidebar.radio("市場", ["日本株", "米国株", "FX"])
    target = st.sidebar.text_input("銘柄名・コード", value="三菱重工")
    period = st.sidebar.selectbox("期間", ["3mo", "6mo", "1y", "2y"], index=1)
    threshold = st.sidebar.slider("検知ライン(%)", 1.0, 20.0, 5.0, 0.5)

    # 銘柄名からの変換
    raw_target = target.strip()
    ticker = STOCK_NAME_MAP.get(raw_target, raw_target)
    
    if market_type == "日本株" and ticker.isdigit(): ticker += ".T"
    elif market_type == "FX": ticker = ticker.replace("/", "") + "=X"
    elif market_type == "米国株" and raw_target not in STOCK_NAME_MAP:
        try:
            res = requests.get(f"https://query2.finance.yahoo.com/v1/finance/search?q={raw_target}", headers={'User-Agent': 'Mozilla/5.0'}).json()
            if res.get('quotes'): ticker = res['quotes'][0]['symbol']
        except: pass

    df = get_stock_data(ticker, period)

    if df is not None:
        # チャート表示
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.03)
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], increasing_line_color='#00C896', decreasing_line_color='#F92855'), row=1, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=df['Color']), row=2, col=1)
        
        v_days = df[df['Change_Pct'].abs() >= threshold]
        if not v_days.empty:
            fig.add_trace(go.Scatter(x=v_days.index, y=v_days['High'] * 1.02, mode='markers+text', marker=dict(symbol='triangle-down', size=10, color='white'), text=[f"{x:+.1f}%" for x in v_days['Change_Pct']], textposition="top center"), row=1, col=1)
        
        fig.update_layout(template='plotly_dark', xaxis_rangeslider_visible=False, height=600)
        st.plotly_chart(fig, use_container_width=True)

        # AIテクニカル分析ボタン
        st.markdown("---")
        st.subheader("🔮 AIテクニカル予想")
        if st.button("チャートパターンを分析", type="primary"):
            if not api_key: st.error("APIキーを入力してください")
            else:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                chart_info = df.tail(60)[['Open', 'High', 'Low', 'Close', 'Volume']].to_string()
                prompt = f"プロの視点で「{target}」のチャートパターンを分析し、今後の予想をせよ。冒頭で【判定: 上昇/下落/もみ合い】を断言。空売り推奨禁止。挨拶不要。\n{chart_info}"
                with st.spinner("分析中..."): st.info(model.generate_content(prompt).text)

        # 答え合わせ（新しい順）
        st.markdown("---")
        st.subheader(f"⚠️ 過去の急変動の理由 (±{threshold}%以上)")
        if v_days.empty: st.info("該当なし")
        else:
            for date, row in v_days.sort_index(ascending=False).iterrows():
                d_str = date.strftime('%Y/%m/%d')
                chg = row['Change_Pct']
                st.markdown(f"### {'🟢' if chg > 0 else '🔴'} {d_str} ┃ {chg:+.2f}%")
                if st.button(f"🔍 {d_str} の変動理由を調査", key=f"q_{d_str}"):
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel("gemini-1.5-flash")
                    prompt = f"銘柄「{target}」が{d_str}に{chg:+.2f}%動いた理由を特定せよ。挨拶不要。材料がポジティブかネガティブか断言せよ。"
                    with st.spinner("調査中..."): st.write(model.generate_content(prompt).text)
                st.divider()
    else: st.warning("データを取得できませんでした。")
