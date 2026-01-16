import streamlit as st
import google.generativeai as genai
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from PIL import Image
import re

# ==========================================
# 1. 初期設定（Secretsからの読み込み）
# ==========================================
st.set_page_config(page_title="AI Trainer Pro", layout="wide")

# ① Gemini APIキーの設定
if "GEMINI_API_KEY" in st.secrets:
    API_KEY = st.secrets["GEMINI_API_KEY"]
else:
    st.error("Secretsに 'GEMINI_API_KEY' が設定されていません。")
    st.stop()

genai.configure(api_key=API_KEY)

# ② モデルの定義（ご指定の Gemini 3 を使用）
# ※PermissionDeniedが出る場合は、AI Studio側でこのモデルの利用権限を確認してください
model = genai.GenerativeModel("gemini-3-flash-preview")

# ③ スプレッドシートURLの取得
if "connections" in st.secrets and "gsheets" in st.secrets.connections:
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
else:
    st.error("Secretsにスプレッドシートの接続情報[connections.gsheets]がありません。")
    st.stop()

# ④ Googleスプレッドシート接続
conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================
# 2. データ読み込み関数
# ==========================================
def load_data():
    try:
        profiles = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0)
        settings = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Settings", ttl=0)
        return profiles, settings
    except Exception as e:
        st.error(f"データの読み込みに失敗しました。URLや権限を確認してください: {e}")
        return pd.DataFrame(), pd.DataFrame()

# ==========================================
# 3. アプリのメインロジック
# ==========================================
st.title("🏃‍♂️ AI Trainer Pro")

# セッション状態の初期化
if "db" not in st.session_state:
    st.session_state.db = {"daily_message": "メニューを生成してください", "tasks": []}

tab1, tab2, tab3 = st.tabs(["プロフィール", "本日のメニュー", "項目管理"])

# --- Tab 1: プロフィール設定 ---
with tab1:
    profiles_df, _ = load_data()
    st.subheader("ユーザー設定")
    user_id = st.text_input("ログインIDを入力してください", value="User1")
    
    if st.button("設定を保存"):
        st.success("プロフィールの保存ロジックを実行しました（実装に合わせて調整してください）")

# --- Tab 2: 本日のメニュー生成 (Gemini 3 連携) ---
with tab2:
    st.subheader("AIトレーナーからの指示")
    
    if st.button("メニューを更新・生成"):
        with st.spinner("Gemini 3 が今日のメニューを構築中..."):
            try:
                # ユーザーの目標などをプロンプトに組み込む
                prompt = "今日の運動タスクを4つと、熱い励ましの伝言を [MESSAGE]...[/MESSAGE] というタグで囲んで出力してください。"
                res = model.generate_content(prompt)
                
                if not res.parts:
                    st.error("AIの回答がブロックされました。")
                else:
                    full_text = res.text
                    # メッセージの抽出
                    msg_match = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", full_text, re.DOTALL)
                    if msg_match:
                        st.session_state.db["daily_message"] = msg_match.group(1).strip()
                    else:
                        st.session_state.db["daily_message"] = full_text

                    # タスクの抽出
                    tasks = [l.strip("- *") for l in full_text.split("\n") if l.strip().startswith(("-", "*"))]
                    st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks[:4]]
                    st.rerun()
            except Exception as e:
                st.error(f"生成エラーが発生しました: {e}")
                if "PermissionDenied" in str(e):
                    st.warning("APIキーに Gemini 3 の利用権限がない可能性があります。Google AI Studioを確認してください。")

    # 表示部分
    st.info(st.session_state.db["daily_message"])
    for i, t in enumerate(st.session_state.db["tasks"]):
        st.checkbox(t["task"], key=f"task_{i}")

# --- Tab 3: 項目管理 (Settings) ---
with tab3:
    _, settings_df = load_data()
    st.subheader("マスタデータ管理")
    st.dataframe(settings_df)
    
    if st.button("スプレッドシートを更新"):
        try:
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=settings_df)
            st.success("Settingsシートを更新しました")
        except Exception as e:
            st.error(f"更新エラー: {e}")

