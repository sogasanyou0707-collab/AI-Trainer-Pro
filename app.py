import streamlit as st
import google.generativeai as genai
import re
from PIL import Image
import datetime
import calendar
import pandas as pd
import requests
from streamlit_gsheets import GSheetsConnection

# --- 1. ページ基本設定 & Secrets読み込み ---
st.set_page_config(page_title="AI Trainer Pro: Ultimate", layout="wide")

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-3-flash-preview")
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"初期設定エラー: {e}")
    st.stop()

# --- 2. データ読み書き関数 ---
def load_full_data_gs(user_id):
    default_data = {
        "profile": {"height": 170.0, "weight": 65.0, "goal": "未設定"},
        "history": {},
        "metrics_data": pd.DataFrame(),
        "metrics_defs": ["体重"],
        "line_config": {"access_token": "", "user_id": "", "enabled": False},
        "daily_message": "準備はいいか！", "tasks": [], "roadmap": ""
    }
    try:
        p_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0)
        h_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="History", ttl=0)
        m_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Metrics", ttl=0)
        s_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Settings", ttl=0)

        # ユーザーデータの抽出
        prof = p_df[p_df['user_id'].astype(str) == str(user_id)].to_dict('records')
        if prof:
            p = prof[0]
            default_data["profile"] = {"height": p.get('height', 170), "weight": p.get('weight', 65), "goal": p.get('goal', "未設定")}
            default_data["line_config"] = {"access_token": p.get('line_token', ""), "user_id": p.get('line_user_id', ""), "enabled": p.get('line_enabled', False)}
            default_data["daily_message"] = p.get('daily_message', "準備はいいか！")

        if not h_df.empty:
            default_data["history"] = h_df[h_df['user_id'].astype(str) == str(user_id)].set_index('date')['rate'].to_dict()
        if not m_df.empty:
            default_data["metrics_data"] = m_df[m_df['user_id'].astype(str) == str(user_id)]
        
        if not s_df.empty:
            # 【修正】重複を排除してリスト化
            raw_defs = s_df[s_df['user_id'].astype(str) == str(user_id)]['metric_defs'].dropna().tolist()
            default_data["metrics_defs"] = sorted(list(set(raw_defs))) # 重複削除

        if not default_data["metrics_defs"]: default_data["metrics_defs"] = ["体重"]
        return default_data
    except:
        return default_data

def save_to_gs(worksheet_name, new_df, key_cols=['user_id', 'date']):
    try:
        existing_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        if key_cols: combined = combined.drop_duplicates(subset=key_cols, keep='last')
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=combined)
        return True
    except Exception as e:
        st.error(f"保存失敗: {e}")
        return False

# --- 3. ログイン & セッション管理 ---
st.sidebar.title("🔑 ログイン")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    st.session_state.db = load_full_data_gs(login_id)
    st.session_state.current_user = login_id

# --- 4. サイドバー設定 ---
with st.sidebar.expander("📊 記録項目の管理"):
    new_m = st.text_input("新規項目名（重複不可）").strip()
    if st.button("追加") and new_m:
        # 【重要】重複チェック
        if new_m in st.session_state.db["metrics_defs"]:
            st.error("その項目は既に追加されています。")
        else:
            st.session_state.db["metrics_defs"].append(new_m)
            # 重複のないリストを作成
            unique_defs = sorted(list(set(st.session_state.db["metrics_defs"])))
            df = pd.DataFrame({"user_id": [login_id]*len(unique_defs), "metric_defs": unique_defs})
            # Settingsシートを更新（既存の項目を含めて上書き）
            if save_to_gs("Settings", df, key_cols=['user_id', 'metric_defs']):
                st.success(f"項目 '{new_m}' を追加しました")
                st.rerun()

# --- Tab 2: 今日のメニュー (数値入力部分) ---
# ... (他タブは省略)
with st.container(): # 描画の安定性を高める
    # 数値入力部分
    col_r = st.columns([1])[0] # レイアウトに合わせて調整
    with col_r:
        st.subheader("📈 数値記録")
        today_metrics = {}
        # ユニークな項目名に対してのみ入力欄を作成
        for m in st.session_state.db["metrics_defs"]:
            if m: # 空文字でない場合のみ
                # keyにインデックスを付与してさらに安全にする
                today_metrics[m] = st.number_input(f"{m}", value=0.0, key=f"input_v_{m}")
