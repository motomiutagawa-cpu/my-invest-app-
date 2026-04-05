import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import google.generativeai as genai
from datetime import datetime

# 画面設定
st.set_page_config(page_title="急変動チャート分析", layout="wide")

st.title("📈 急変動チャート ＆ 過去ニュース照合AI")
st.markdown("過去のチャートから大きく動いた日を自動検知し、「なぜ動いたのか」をAIが過去データから照合します。")

# サイドバー
api_key = st.sidebar.text_input("APIキーを入力", type="password")

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ チャット・検知設定")
target_stock = st.sidebar.text_input("銘柄コード・ティッカー", value="7011", help="日本株は4桁の数字、米国株はティッカー")
period = st.sidebar.selectbox("表示期間", ["3mo", "6mo", "1y", "2y"], index=1)
threshold = st.sidebar.slider("急変動とみなすライン（±％）", min_value=1.0, max_value=20.0, value=5.0, step=0.5)

# 銘柄コードの整形
ticker_symbol = target_stock.strip()
if ticker_symbol.isdigit() and len(ticker_symbol) == 4:
    ticker_symbol = f"{ticker_symbol}.T"

# --- データ取得とチャート描画 ---
@st.cache_data(ttl=3600)
def get_stock_data(ticker, per):
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period=per)
        if df.empty:
            return None
        # 前日比（％）を計算
        df['Change_Pct'] = df['Close'].pct_change() * 100
        return df
    except:
        return None

df = get_stock_data(ticker_symbol, period)

if df is not None:
    # ローソク足チャートの作成
    fig = go.Figure(data=[go.Candlestick(x=df.index,
                    open=df['Open'],
                    high=df['High'],
                    low=df['Low'],
                    close=df['Close'],
                    name="価格")])

    # 急変動した日を抽出
    volatile_days = df[df['Change_Pct'].abs() >= threshold]

    # 急変動日にマーカー（ピン）を立てる
    if not volatile_days.empty:
        fig.add_trace(go.Scatter(
            x=volatile_days.index,
            y=volatile_days['High'] * 1.02, # ローソク足の少し上に表示
            mode='markers+text',
            marker=dict(symbol='triangle-down', size=12, color='blue'),
            text=[f"{val:+.1f}%" for val in volatile_days['Change_Pct']],
            textposition="top center",
            name="急変動サイン"
        ))

    fig.update_layout(
        title=f"【{target_stock}】のローソク足チャート（期間: {period}）",
        yaxis_title="株価",
        xaxis_rangeslider_visible=False,
        height=500,
        margin=dict(l=0, r=0, t=40, b=0)
    )
    
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader(f"⚠️ 基準（±{threshold}%）を超えた急変動日")

    if volatile_days.empty:
        st.info("指定した期間・条件で大きく動いた日はありませんでした。左の「検知ライン」を下げてみてください。")
    else:
        # 変動日のリストを表示
        for date, row in volatile_days.iterrows():
            date_str = date.strftime('%Y年%m月%d日')
            change = row['Change_Pct']
            close_price = row['Close']
            
            # 見た目を分かりやすくするためのカラム分け
            col1, col2, col3 = st.columns([1.5, 1, 3])
            
            with col1:
                st.write(f"**📅 {date_str}**")
            with col2:
                color = "red" if change > 0 else "blue"
                st.markdown(f"<span style='color:{color}; font-weight:bold;'>{change:+.2f}%</span> (￥{close_price:,.1f})", unsafe_allow_html=True)
            with col3:
                # この日の理由をAIに聞くボタン
                if st.button(f"🔍 なぜ動いた？（AI過去照合）", key=f"btn_{date_str}"):
                    if not api_key:
                        st.error("左のサイドバーにAPIキーを入力してください。")
                    else:
                        genai.configure(api_key=api_key)
                        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
                        
                        # AIへの指示（もとみさん専用ルール適用）
                        prompt = f"""
                        あなたは凄腕の投資アナリストです。
                        銘柄「{target_stock}」の株価が、【{date_str}】に前日比 {change:+.2f}% と急変動しました。
                        あなたの知識ベースから、この日（または前日の引け後）に発表された決算、IR、ニュース、マクロ要因などを特定し、なぜこれほど株価が動いたのかを解説してください。

                        【絶対遵守ルール】
                        1. 挨拶、前置き、自己責任等の免責文は一切書かず、すぐに事実を出力せよ。
                        2. 投資に関係ない話は禁止。ショート（空売り）の提案も禁止。
                        3. 見出しは **【{target_stock} | {date_str}の変動理由】** とすること。
                        4. その日に出た個別の材料（決算、修正、提携など）を最優先で解説し、該当がない場合はセクターやマクロの動きから理由を論理的に推測せよ。
                        5. 最後に、この材料が当時 **【ポジティブ / ネガティブ】** どちらに受け取られたのかを断言せよ。
                        """
                        
                        with st.spinner(f"{date_str} の過去ニュースと材料を検索・分析中..."):
                            try:
                                response = model.generate_content(prompt)
                                st.success("✅ 過去データの照合完了")
                                st.write(response.text)
                            except Exception as e:
                                st.error(f"分析エラー: {e}")
            st.divider()

else:
    st.warning("株価データが取得できませんでした。銘柄コードが正しいか確認してください。")
