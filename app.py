import streamlit as st
import feedparser
import google.generativeai as genai

# 画面の基本設定（横幅を広く使う設定）
st.set_page_config(page_title="AI投資ダッシュボード", layout="wide")
st.title("📊 最新ニュース＆AIポジネガ判定")

# 左側のサイドバーにAPIキー入力欄を設置
api_key = st.sidebar.text_input("Google AI StudioのAPIキーを入力", type="password")

# 監視する銘柄リスト（もとみさんの最重要注目銘柄から抜粋・追加可能）
WATCHLIST = [
    # 最重要注目銘柄
    "三菱重工", "川崎重工", "IHI", "ソニーg", "ソニーfg", "任天堂", 
    "アストロスケール", "安川電機", "住友電工", "古河電気工業", "フジクラ", "東レ", 
    "本田技研", "日立製作所", "東北電力", "シマノ", "acsl", "日東電工", "三菱UFJ", 
    "サンリオ", "KDDI", "川崎汽船", "商船三井", "日本郵船", "VALUENEX",
    
    # 注目銘柄
    "三菱hcキャピタル", "三菱ケミカル", "伊藤忠", "日東紡績", "三菱マテリアル", 
    "小松製作所", "三菱商事", "オリックス", "楽天グループ", "ディー・エヌ・エー", 
    "三井不動産", "三井物産", "igポート", "Liberaware", "メタプラネット", 
    "アドバンテスト", "東京エレクトロン", "キーエンス", "ファナック", "村田製作所", 
    "レーザーテック", "イビデン", "ディスコ", "信越化学工業", "第一生命", "ヤマハ", 
    "住友金属鉱山", "エニーカラー", "ソフトバンク", "ソフトバンクg", "キオクシア", 
    "三井住友fg", "みずほfg", "東邦銀行", "アルコニックス", "レンゴー", "楽天銀行", 
    "細谷火工", "QPSホールディングス", "ブルーイノベーション", "名村造船所", 
    "カバー", "inpex", "ispace", "スカパーjsat"
]


def get_news():
    """RSSを利用してニュースを取得し、対象銘柄が含まれるか判定する関数"""
    # Yahoo!ファイナンスのビジネスカテゴリRSS等を利用
    rss_urls = [
        "https://news.yahoo.co.jp/rss/topics/business.xml",
        # 必要に応じて株探などのRSS URLを追加
    ]
    
    target_news = []
    for url in rss_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries[:30]: # 最新30件をチェック
            # タイトルに監視銘柄が含まれているかチェック
            if any(stock in entry.title for stock in WATCHLIST):
                target_news.append({"title": entry.title, "link": entry.link})
    
    return target_news

# 「分析開始」ボタンが押された時の処理
if st.sidebar.button("ニュースを取得＆分析"):
    if not api_key:
        st.error("左側のメニューにAPIキーを入力してください。")
    else:
        # Gemini APIの初期設定
        genai.configure(api_key=api_key)
        # 安定して賢いモデルを指定
        model = genai.GenerativeModel("gemini-1.5-pro-latest") 

        with st.spinner("ニュースを収集中..."):
            news_items = get_news()

        if not news_items:
            st.info("※上記以外の銘柄については、本日特筆すべき個別材料はありません（全体相場・マクロ要因に連動して推移）")
        else:
            # 画面を左右に分割（折りたたみスマホを開いた時やPC向け）
            col1, col2 = st.columns([1, 1])
            
            news_text_for_ai = ""

            with col1:
                st.subheader("📰 関連ニュース一覧")
                for item in news_items:
                    st.markdown(f"- [{item['title']}]({item['link']})")
                    news_text_for_ai += f"・{item['title']}\n"

            with col2:
                st.subheader("🤖 AI分析結果")
                with st.spinner("AIがポジネガ判定中..."):
                    # いつもの抽出ルールをプロンプトとして設定
                    prompt = f"""
                    以下のニュースの見出しリストから、投資判断に直結する分析を行ってください。
                    
                    【ニュースリスト】
                    {news_text_for_ai}
                    
                    【出力ルール】
                    セクター単位でのまとめではなく、「個別銘柄名」を見出しにして一つずつ記載すること。
                    決算発表、業績修正、株式分割、自社株買い、業務提携、新技術の発表、アナリストのレーティング変更、配当落ちなど、その企業単独の材料を優先して抽出すること。
                    各ニュースの事実を端的に記載し、最後にその材料が株価に与える影響（ポジティブかネガティブか）を1〜2行で客観的に添えること。
                    投資判断に不要な前置きや挨拶は一切省き、すぐにニュースの一覧から出力すること。
                    """
                    
                    try:
                        # Temperatureを0にして事実のみを出力させる
                        response = model.generate_content(prompt, generation_config={"temperature": 0.0})
                        st.write(response.text)
                    except Exception as e:
                        st.error(f"エラーが発生しました: {e}")
