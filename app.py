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

# 画面設定 (必ず一番上)
st.set_page_config(page_title="AI投資アナリスト・もとみさん専用", layout="wide")

# --- グローバル設定・関数 ---
CORE_WATCHLIST = {
    "日本株": "三菱重工, 川崎重工, IHI, ソニーg, ソニーfg, トヨタ, 任天堂, アストロスケール, 安川電機, 住友電工, 古河電気工業, フジクラ, 東レ, 本田技研, 日立製作所, 東北電力, シマノ, acsl, 日東電工, 三菱UFJ, サンリオ, KDDI, 川崎汽船, 商船三井, 日本郵船, 三菱hcキャピタル, 三菱ケミカル, 伊藤忠, 日東紡績, 三菱マテリアル, 小松製作所, 三菱商事, オリックス, 楽天グループ, ディー・エヌ・エー, 三井不動産, 三井物産, igポート, Liberaware, メタプラネット, アドバンテスト, 東京エレクトロン, キーエンス, ファナック, 村田製作所, レーザーテック, イビデン, ディスコ, 信越化学工業, 第一生命, ヤマハ, 住友金属鉱山, エニーカラー, ソフトバンク, ソフトバンクg, キオクシア, 三井住友fg, みずほfg, 東邦銀行, アルコニックス, レンゴー, 楽天銀行, 細谷火工, QPSホールディングス, ブルーイノベーション, 名村造船所, カバー, inpex, ispace, スカパーjsat",
    "米国株": "AAPL, NVDA, GOOGL, AMZN, TSLA, MSFT, META, PLTR, RKLB, AVGO, BRK-B",
    "先物・商品": "^NK225, ^DJI, ^IXIC, CL=F, GC=F, ^TNX",
    "FX・為替": "USD/JPY, EUR/JPY, GBP/JPY, AUD/JPY, EUR/USD"
}

STOCK_NAME_MAP = {
    "三菱重工": "7011", "川崎重工": "7012", "ihi": "7013", "ソニーg": "6758", "ソニーfg": "5814",
    "トヨタ": "7203", "トヨタ自動車": "7203", "任天堂": "7974", "アストロスケール": "186A", 
    "安川電機": "6506", "住友電工": "5802", "古河電気工業": "5801", "古河電工": "5801", "フジクラ": "5803", 
    "東レ": "3402", "本田技研": "7267", "ホンダ": "7267", "日立製作所": "6501", "日立": "6501", 
    "東北電力": "9506", "シマノ": "7309", "acsl": "6232", "日東電工": "6988", "三菱ufj": "8306", 
    "サンリオ": "8136", "kddi": "9433", "川崎汽船": "9107", "商船三井": "9104", "日本郵船": "9101",
    "三菱hcキャピタル": "8593", "三菱ケミカル": "4188", "伊藤忠": "8001", "伊藤忠商事": "8001", 
    "日東紡績": "3110", "日東紡": "3110", "三菱マテリアル": "5711", "小松製作所": "6301", "コマツ": "6301",
    "三菱商事": "8058", "オリックス": "8591", "楽天グループ": "4755", "楽天": "4755", 
    "ディー・エヌ・エー": "2432", "dena": "2432", "三井不動産": "8801", "三井物産": "8031", 
    "igポート": "3791", "liberaware": "218A", "メタプラネット": "3350", "アドバンテスト": "6857", 
    "東京エレクトロン": "8035", "キーエンス": "6861", "ファナック": "6954", "村田製作所": "6981", 
    "レーザーテック": "6920", "イビデン": "4062", "ディスコ": "6146", "信越化学工業": "4063", "信越化学": "4063",
    "第一生命": "8750", "ヤマハ": "7951", "住友金属鉱山": "5713", "エニーカラー": "5032", "anycolor": "5032",
    "ソフトバンク": "9434", "ソフトバンクg": "9984", "三井住友fg": "8316", "みずほfg": "8411", 
    "東邦銀行": "8346", "アルコニックス": "3036", "レンゴー": "3941", "楽天銀行": "5838", 
    "細谷火工": "4274", "qpsホールディングス": "5595", "qps": "5595", "ブルーイノベーション": "5597", 
    "名村造船所": "7014", "カバー": "5253", "cover": "5253", "inpex": "1605", "ispace": "9348", 
    "スカパーjsat": "9412", "スカパー": "9412",
    "アップル": "AAPL", "エヌビディア": "NVDA", "グーグル": "GOOGL", "アマゾン": "AMZN", 
    "テスラ": "TSLA", "マイクロソフト": "MSFT", "メタ": "META", "パランティア": "PLTR", 
    "ロケットラボ": "RKLB", "ブロードコム": "AVGO", "バークシャー": "BRK-B"
}

def get_price_info(stock_str, market):
    items = [s.strip() for s in stock_str.replace("、", ",").split(",") if s.strip()]
    price_data = ""
    for item in items:
        raw_item = item.lower()
        ticker_symbol = STOCK_NAME_MAP.get(raw_item, item)
        
        if "/" in ticker_symbol or market == "FX・為替":
            ticker_symbol = ticker_symbol.replace("/", "").replace(" ", "")
            if not ticker_symbol.endswith("=X"): ticker_symbol += "=X"
        elif market == "日本株" and len(ticker_symbol) == 4 and ticker_symbol.isdigit():
            ticker_symbol = f"{ticker_symbol}.T"
        elif market == "日本株" and len(ticker_symbol) == 4 and ticker_symbol[:-1].isdigit() and ticker_symbol[-1].isalpha():
            ticker_symbol = f"{ticker_symbol}.T"
        
        try:
            tk = yf.Ticker(ticker_symbol)
            df = tk.history(period="5d")
            if not df.empty and len(df) >= 2:
                cur_price = df['Close'].iloc[-1]
                prev_price = df['Close'].iloc[-2]
                change = ((cur_price - prev_price) / prev_price) * 100
                price_data += f"・{item}: {cur_price:,.1f} ({change:+.2f}%)\n"
        except: continue
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
                
                if "福島" in entry.title or "カメラ" in entry.title:
                    continue
                    
                news_list.append({"title": entry.title, "summary": entry.get("summary", ""), "link": entry.link, "source": "Yahoo" if "yahoo" in url else "ロイター" if "reuters" in url else "PR TIMES", "time": pub_time.astimezone(timezone(timedelta(hours=9))).strftime('%m/%d %H:%M') if pub_struct else "--:--"})
                seen_links.add(entry.link)
        except: continue
    return news_list

def analyze_single_article(title, summary, api_key):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
    
    # トリプルクォート排除
    prompt_lines = [
        "この記事を投資家視点で端的に要約し、影響を予測してください。挨拶や免責文は一切不要。",
        "【出力フォーマット】",
        "【要約】（事実を3行で端的に）",
        "【対象】（影響を最も受ける「具体的な銘柄名」「セクター名」または「全体相場」を明記）",
        "【判定】ポジティブ / ネガティブ / 中立",
        "【予想インパクト】（対象に対して）+〇%上昇予測 / -〇%下落予測 など大胆に数値を提示",
        "【タイトル】: " + title,
        "【本文】: " + summary
    ]
    prompt = "\n".join(prompt_lines)
    
    try:
        return model.generate_content(prompt).text
    except:
        try:
            model = genai.GenerativeModel("gemini-pro")
            return model.generate_content(prompt).text
        except Exception as e:
            return f"エラー: {e}"

@st.cache_data(ttl=3600)
def get_stock_data(ticker, per):
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period=per)
        if df.empty:
            return None
        df['Change_Pct'] = df['Close'].pct_change() * 100
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['Color'] = df.apply(lambda row: '#00C896' if row['Close'] >= row['Open'] else '#F92855', axis=1)
        return df
    except:
        return None

# --- 共通サイドバー ---
st.sidebar.markdown("### 🔄 アプリモード切替")
app_mode = st.sidebar.radio("使いたいツールを選択してください", ["📰 ニュース・相場分析", "📈 急変動チャートAI照合"])
st.sidebar.markdown("---")
api_key = st.sidebar.text_input("APIキーを入力", type="password")
st.sidebar.markdown("---")

# ==========================================
# モード1: ニュース・相場分析
# ==========================================
if app_mode == "📰 ニュース・相場分析":
    st.title("🌐 AI投資ニュース・プロ分析")
    
    market_choice = st.sidebar.radio("分析対象を選択", ["日本株", "米国株", "先物・商品", "FX・為替"], horizontal=True)
    hours_range = st.sidebar.slider("過去何時間分を取得しますか？", 1, 72, 24)
    
    st.sidebar.markdown("---")
    with st.sidebar.expander("🔍 注目セクターを選択"):
        SECTOR_OPTIONS = ["防衛", "宇宙", "重工", "海運", "物流", "エネルギー", "資源・素材", "半導体", "ハイテク・AI", "金融・銀行", "商社", "自動車", "不動産", "電力・インフラ", "化学・素材"]
        col_s1, col_s2 = st.columns(2)
        if col_s1.button("全選択", key="sec_all"):
            for s in SECTOR_OPTIONS: st.session_state[f"sec_{s}"] = True
        if col_s2.button("全解除", key="sec_none"):
            for s in SECTOR_OPTIONS: st.session_state[f"sec_{s}"] = False
        selected_sectors = [s for s in SECTOR_OPTIONS if st.checkbox(s, key=f"sec_{s}", value=st.session_state.get(f"sec_{s}", False))]

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎯 特定銘柄を深掘り")
    narrow_stocks = st.sidebar.text_area("銘柄名・コードを入力（ここに入力がある場合は最優先）", placeholder="例: 三菱重工, NVDA")

    if "analysis_text" not in st.session_state: st.session_state.analysis_text = None
    if "fetched_news" not in st.session_state: st.session_state.fetched_news = []
    if "individual_summaries" not in st.session_state: st.session_state.individual_summaries = {}
    if "messages" not in st.session_state: st.session_state.messages = []
    if "chat_session" not in st.session_state: st.session_state.chat_session = None

    if st.sidebar.button(f"{market_choice} 分析を開始"):
        if not api_key: st.error("APIキーを入れてください。")
        else:
            st.session_state.analysis_text = None
            st.session_state.chat_session = None
            st.session_state.messages = []
            genai.configure(api_key=api_key)
            
            with st.spinner("情報を戦略的に精査中..."):
                try:
                    news_data = get_all_news(hours_range)
                    st.session_state.fetched_news = news_data
                    st.session_state.individual_summaries = {}
                    
                    target_list = narrow_stocks if narrow_stocks else CORE_WATCHLIST.get(market_choice)
                    realtime_prices = get_price_info(target_list, market_choice)
                    
                    all_news_text = ""
                    for i, n in enumerate(news_data):
                        all_news_text += f"No.{i}: {n['title']}\n{n['summary']}\n\n"
                    
                    if narrow_stocks:
                        policy = "【厳守：銘柄指定モード】あなたは指定された『" + narrow_stocks + "』に関する情報のみを分析する。これ以外の銘柄や、これに無関係なセクター情報は一切出力するな。"
                    elif selected_sectors:
                        policy = "【厳守：セクター限定モード】選択されたセクター『" + ", ".join(selected_sectors) + "』に関する情報のみを出力せよ。無関係な他セクターの情報は一切不要。"
                    else:
                        policy = "【通常モード】注目銘柄（" + target_list + "）を中心に分析しつつ、材料が出た他銘柄もディスカバリーして幅広く報告せよ。"

                    # トリプルクォート排除
                    main_prompt_lines = [
                        "あなたはプロの投資アナリストです。以下の【絶対遵守ルール】に従って出力せよ。",
                        "【絶対遵守ルール】",
                        "1. 挨拶、前置き、自己責任などの免責文は一切書かず、すぐに結果を出力せよ。",
                        "2. " + policy,
                        "3. 【ハイブリッド出力】全体に波及するマクロニュースはセクター（【セクター：〇〇】）でまとめ、個別に大きな材料がある銘柄は個別に見出しを立てて詳しく分析せよ。",
                        "4. 【見出しとデータ】見出しは必ず **【銘柄名(コード) | 現在価格 | 騰落率】** とし、価格データを正確に記載せよ。",
                        "5. 【判定とインパクト】各分析の冒頭に必ず **【判定：ポジティブ/ネガティブ/中立】** と **【予想インパクト：+〇%上昇予測 / -〇%下落予測】** を断言せよ。",
                        "6. 【経済指標・連想・テクニカル】直接のニュースがない場合でも、為替や金利、経済指標（CPI、雇用統計、要人発言など）、同業種の動向から「間接的な影響」と「テクニカル予測」を必ず考察せよ。FX・為替の分析時は特に経済指標を最重視すること。",
                        "7. 【引用バグの防止】文末に必ず情報源として「(No.Xより)」と添えること。この「X」は入力されたニュースリストのインデックス番号（0, 1, 2...）のみを使うこと。証券コード（例: 6501）をニュース番号と混同して記載するのは絶対厳禁。",
                        "【現在の株価・騰落率】",
                        realtime_prices,
                        "ニュースリスト:",
                        all_news_text
                    ]
                    prompt = "\n".join(main_prompt_lines)
                    
                    try:
                        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
                        chat = model.start_chat(history=[])
                        response = chat.send_message(prompt)
                    except:
                        model = genai.GenerativeModel("gemini-pro")
                        chat = model.start_chat(history=[])
                        response = chat.send_message(prompt)
                    
                    if response.text:
                        st.session_state.analysis_text = response.text
                        st.session_state.chat_session = chat
                    else:
                        st.error("AIからの応答が空でした。")
                except Exception as e: 
                    st.error(f"分析処理中にエラーが発生しました: {e}")

    if st.session_state.analysis_text:
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("📊 ニュースフィード")
            with st.container(height=800):
                for i, n in enumerate(st.session_state.fetched_news):
                    with st.expander(f"No.{i}: 📌 [{n['time']}] {n['title']}"):
                        st.write(n['summary'])
                        if st.button(f"✨ AI要約 (No.{i})", key=f"btn_news_{i}"):
                            with st.spinner("要約中..."):
                                st.session_state.individual_summaries[i] = analyze_single_article(n['title'], n['summary'], api_key)
                        if i in st.session_state.individual_summaries:
                            st.info(st.session_state.individual_summaries[i])
                        st.link_button("全文へ", n['link'])
                    
        with col2:
            st.subheader("🤖 AI戦略分析")
            with st.container(height=800):
                with st.spinner("音声を生成中..."):
                    try:
                        audio_bytes = asyncio.run(generate_voice(st.session_state.analysis_text))
                        st.audio(audio_bytes, format='audio/mp3')
                    except Exception as e: 
                        st.warning("音声生成をスキップしました。")
                
                st.write(st.session_state.analysis_text)
                st.markdown("---")
                for m in st.session_state.messages:
                    with st.chat_message(m["role"]): st.markdown(m["content"])
                
                if q := st.chat_input("さらに深掘り..."):
                    st.session_state.messages.append({"role": "user", "content": q})
                    with st.chat_message("user"): st.markdown(q)
                    with st.chat_message("assistant"):
                        if st.session_state.chat_session:
                            try:
                                resp = st.session_state.chat_session.send_message(q)
                                st.markdown(resp.text)
                                st.session_state.messages.append({"role": "assistant", "content": resp.text})
                            except Exception as e:
                                st.error(f"チャットエラー: {e}")
                        else: 
                            st.error("分析を開始してください。")

# ==========================================
# モード2: 急変動チャート分析
# ==========================================
elif app_mode == "📈 急変動チャートAI照合":
    st.title("📈 急変動チャート ＆ AIテクニカル予想")
    st.info("💡 **ヒント:** チャート上の「▼マーク」の急変理由は、画面を下へスクロールした先のリストから確認できます！")

    st.sidebar.markdown("### ⚙️ チャート検知設定")
    target_stock = st.sidebar.text_input("銘柄名・コードを入力", value="三菱重工", help="例: 三菱重工, 7011, エヌビディア, NVDA")
    period = st.sidebar.selectbox("表示期間", ["3mo", "6mo", "1y", "2y"], index=1)
    
    threshold = st.sidebar.slider("急変動とみなすライン（±％）", min_value=1.0, max_value=20.0, value=5.0, step=0.5)

    raw_target = target_stock.strip().lower()
    ticker_symbol = STOCK_NAME_MAP.get(raw_target, target_stock.strip())

    if ticker_symbol.isdigit() and len(ticker_symbol) == 4:
        ticker_symbol = f"{ticker_symbol}.T"
    elif len(ticker_symbol) == 4 and ticker_symbol[:-1].isdigit() and ticker_symbol[-1].isalpha():
        ticker_symbol = f"{ticker_symbol}.T"

    df = get_stock_data(ticker_symbol, period)

    if df is not None:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.03)

        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            increasing_line_color='#00C896', increasing_fillcolor='#00C896',
            decreasing_line_color='#F92855', decreasing_fillcolor='#F92855',
            name="価格"
        ), row=1, col=1)

        fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='#F2B33D', width=1.2), name='MA5'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#8A5EE6', width=1.2), name='MA20'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='#3283F6', width=1.2), name='MA60'), row=1, col=1)

        fig.add_trace(go.Bar(
            x=df.index, y=df['Volume'], 
            marker_color=df['Color'], 
            name="出来高"
        ), row=2, col=1)

        volatile_days = df[df['Change_Pct'].abs() >= threshold]
        if not volatile_days.empty:
            fig.add_trace(go.Scatter(
                x=volatile_days.index,
                y=volatile_days['High'] * 1.02,
                mode='markers+text',
                marker=dict(symbol='triangle-down', size=12, color='white'),
                text=[f"{val:+.1f}%" for val in volatile_days['Change_Pct']],
                textfont=dict(color="white"),
                textposition="top center",
                name="急変動"
            ), row=1, col=1)

        fig.update_layout(
            template='plotly_dark',
            title=f"【{target_stock} ({ticker_symbol})】 日足チャート",
            xaxis_rangeslider_visible=False,
            height=500,
            margin=dict(l=10, r=10, t=50, b=10),
            showlegend=False,
            hovermode='x unified',
            plot_bgcolor='#131722',
            paper_bgcolor='#131722'
        )
        
        fig.update_xaxes(showgrid=True, gridcolor='#2B2B2B', zeroline=False)
        fig.update_yaxes(showgrid=True, gridcolor='#2B2B2B', zeroline=False)

        st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.subheader("🔮 今のチャートから未来を予想（テクニカルAI分析）")
        if st.button("AIにチャートパターンを分析させる", type="primary"):
            if not api_key:
                st.error("左のサイドバーにAPIキーを入力してください。")
            else:
                recent_df = df.tail(60)[['Open', 'High', 'Low', 'Close', 'Volume']]
                chart_data_str = recent_df.to_string()
                
                genai.configure(api_key=api_key)
                try:
                    model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
                except:
                    model = genai.GenerativeModel("gemini-pro")
                
                # トリプルクォート排除
                tech_prompt_lines = [
                    "あなたはプロのテクニカルアナリストです。",
                    "以下のデータは、銘柄「" + target_stock + "」の直近60日間の四本値と出来高です。",
                    "このデータから、以下を分析してください。",
                    "1. 現在形成されている「チャートパターン」（ダブルボトム、ダブルトップ、三尊、トレンドラインの支持・抵抗、もみ合いなど）を具体的に見つけ出すこと。",
                    "2. それを踏まえた今後の短期的な株価予想。",
                    "【絶対遵守ルール】",
                    "・挨拶、免責文（投資は自己責任等）は一切不要。すぐに結論を出力せよ。",
                    "・必ず冒頭で【判定: 上昇予測 / 下落予測 / もみ合い】を断言すること。",
                    "・買い目線、売り目線の両方を含めるが、ショート（空売り）の推奨は絶対に行わないこと。",
                    "・なぜそう判断したのか、チャートの日付や価格の推移を根拠に論理的に解説すること。",
                    "【直近60日間のデータ】",
                    chart_data_str
                ]
                tech_prompt = "\n".join(tech_prompt_lines)
                
                with st.spinner("AIがチャートの形状（パターン）を分析中..."):
                    try:
                        response = model.generate_content(tech_prompt)
                        st.success("✅ チャートパターン分析完了")
                        st.info(response.text)
                    except Exception as e:
                        st.error(f"分析エラー: {e}")

        st.markdown("---")
        st.subheader("⚠️ 過去の急変動の答え合わせ（±" + str(threshold) + "%以上）")

        if volatile_days.empty:
            st.info("指定した期間・条件で大きく動いた日はありませんでした。左の「検知ライン」を下げてみてください。")
      
