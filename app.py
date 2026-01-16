import streamlit as st
import google.generativeai as genai
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import re

# 1. ページ設定（必ず一番上に書く）
st.set_page_config(page_title="AI Trainer Pro", layout="wide")

# 2. 初期設定（Secretsから読み込み）
try:
    # APIキーの取得
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
    else:
        st.error("Secretsに 'GEMINI_API_KEY' が設定されていません。")
        st.stop()

    genai.configure(api_key=API_KEY)
    
    # ご指定のモデル「Gemini 3」を使用
    # ※正式名称が異なる場合、ここでエラーが出やすいため try で囲んでいます
    try:
        model = genai.GenerativeModel("gemini-3-flash-preview")
    except:
        model = None

    # スプレッドシートURLの取得
    if "connections" in st.secrets and "gsheets" in st.secrets.connections:
        SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    else:
        st.error("SecretsにスプレッドシートのURLが見つかりません。")
        st.stop()

    conn = st.connection("gsheets", type=GSheetsConnection)

except Exception as e:
    st.error(f"初期設定でエラーが発生しました: {e}")

# 3. アプリのタイトル
st.title("🏃‍♂️ AI Trainer Pro")

# 4. タブの作成（これを最初に定義することで、表示が消えるのを防ぎます）
tab1, tab2, tab3 = st.tabs(["プロフィール", "カレンダー", "項目管理"])

# --- Tab 1: プロフィール ---
with tab1:
    st.subheader("ユーザープロフィール")
    try:
        profiles_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0)
        user_id = st.text_input("ユーザーID", value="User1")
        if not profiles_df.empty:
            st.dataframe(profiles_df)
        else:
            st.info("Profilesシートにデータがありません。")
    except Exception as e:
        st.warning(f"プロフィールの読み込みに失敗しました: {e}")

# --- Tab 2: カレンダー (メニュー生成) ---
with tab2:
    st.subheader("🗓 今日のメニュー")
    if "db" not in st.session_state:
        st.session_state.db = {"daily_message": "ボタンを押してメニューを生成してください", "tasks": []}

    if st.button("Gemini 3 でメニュー生成"):
        if model is None:
            st.error("Gemini 3 モデルの初期化に失敗しています。モデル名を確認してください。")
        else:
            with st.spinner("AIがトレーニングを構築中..."):
                try:
                    res = model.generate_content("タスク4つと励ましを [MESSAGE]...[/MESSAGE] で出力して。")
                    full_text = res.text
                    msg_match = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", full_text, re.DOTALL)
                    st.session_state.db["daily_message"] = msg_match.group(1).strip() if msg_match else full_text
                    tasks = [l.strip("- *") for l in full_text.split("\n") if l.strip().startswith(("-", "*"))]
                    st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks[:4]]
                    st.rerun()
                except Exception as e:
                    st.error(f"AI生成エラー: {e}")

    st.info(st.session_state.db["daily_message"])
    for i, t in enumerate(st.session_state.db["tasks"]):
        st.checkbox(t["task"], key=f"task_{i}")

# --- Tab 3: 項目管理 ---
with tab3:
    st.subheader("設定マスタ")
    try:
        settings_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Settings", ttl=0)
        st.dataframe(settings_df)
    except Exception as e:
        st.warning(f"Settingsシートの読み込みに失敗しました: {e}")
