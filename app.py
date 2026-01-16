import streamlit as st
import google.generativeai as genai
import re
import json
import pandas as pd
import datetime
import calendar
import requests
from PIL import Image
from streamlit_gsheets import GSheetsConnection

# --- 1. ページ基本設定 ---
st.set_page_config(page_title="AI Trainer Pro: Ultimate", layout="wide")

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    genai.configure(api_key=API_KEY)
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"初期設定エラー: {e}")
    st.stop()

# --- 2. モデル取得機能 ---
@st.cache_resource
def get_available_models():
    try:
        models = [m.name.replace("models/", "") for m in genai.list_models() 
                  if "generateContent" in m.supported_generation_methods]
        return models
    except:
        return ["gemini-1.5-flash", "gemini-pro"]

available_models = get_available_models()

# --- 3. データ読み書き関数 ---
def load_full_data_gs(user_id):
    default_data = {
        "profile": {"height": 170.0, "weight": 65.0, "goal": "バスケの基礎力アップ"},
        "history": {}, "notes": {}, "metrics_data": pd.DataFrame(), "metrics_defs": ["体重"],
        "line": {"token": "", "uid": "", "en": False},
        "daily_message": "今日も最高の練習にしよう！", "tasks": [], "roadmap": ""
    }
    try:
        p_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0)
        h_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="History", ttl=0)
        m_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Metrics", ttl=0)
        s_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Settings", ttl=0)

        u_id = str(user_id)
        prof = p_df[p_df['user_id'].astype(str) == u_id].to_dict('records')
        
        if prof:
            p = prof[0]
            default_data["profile"] = {"height": p.get('height', 170), "weight": p.get('weight', 65), "goal": p.get('goal', "未設定")}
            default_data["line"] = {"token": p.get('line_token', ""), "uid": p.get('line_user_id', ""), "en": p.get('line_enabled', False)}
            default_data["daily_message"] = p.get('daily_message', "準備はいいか！")
            t_json = p.get('tasks_json', "[]")
            default_data["tasks"] = json.loads(t_json) if t_json else []

        if not h_df.empty:
            user_hist = h_df[h_df['user_id'].astype(str) == u_id]
            default_data["history"] = user_hist.set_index('date')['rate'].to_dict()
            default_data["notes"] = user_hist.set_index('date')['note'].to_dict()
            
        if not m_df.empty:
            default_data["metrics_data"] = m_df[m_df['user_id'].astype(str) == u_id]
            
        if not s_df.empty:
            raw_defs = s_df[s_df['user_id'].astype(str) == u_id]['metric_defs'].dropna().tolist()
            if raw_defs:
                default_data["metrics_defs"] = sorted(list(set(raw_defs)))
        
        return default_data
    except:
        return default_data

def save_to_gs(worksheet_name, new_df, key_cols=['user_id', 'date']):
    try:
        existing_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
        combined = pd.concat([existing_df, new_df], ignore_index=True).drop_duplicates(subset=key_cols, keep='last')
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=combined)
        return True
    except:
        return False

# --- 4. ログイン ---
st.sidebar.title("🔑 AI Trainer Pro")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    st.session_state.db = load_full_data_gs(login_id)
    st.session_state.current_user = login_id

selected_coach = st.sidebar.selectbox("🤖 コーチを選択", ["バスケットボール専門コーチ", "熱血コーチ", "論理派トレーナー"])
selected_model = st.sidebar.selectbox("AIモデル", available_models, index=0)

model = genai.GenerativeModel(
    selected_model, 
    system_instruction=f"あなたは{selected_coach}です。小学校6年生の男子が、自宅で毎日楽しく続けられるバスケ練習を指導してください。目標:{st.session_state.db['profile']['goal']}"
)

# --- 5. サイドバー設定 ---
with st.sidebar.expander("👤 プロフィール・LINE設定"):
    db = st.session_state.db
    h_v = st.number_input("身長 (cm)", value=float(db["profile"]["height"]))
    w_v = st.number_input("体重 (kg)", value=float(db["profile"]["weight"]))
    g_v = st.text_area("目標", value=db["profile"]["goal"])
    st.divider()
    l_en = st.checkbox("LINE報告を有効化", value=db["line"]["en"])
    l_at = st.text_input("LINEトークン", value=db["line"]["token"], type="password")
    l_ui = st.text_input("宛先UID", value=db["line"]["uid"])
    
    if st.button("設定を保存"):
        t_json = json.dumps(db["tasks"], ensure_ascii=False)
        df_p = pd.DataFrame([{
            "user_id": login_id, "height": h_v, "weight": w_v, "goal": g_v,
            "line_token": l_at, "line_user_id": l_ui, "line_enabled": l_en,
            "daily_message": db["daily_message"], "tasks_json": t_json
        }])
        if save_to_gs("Profiles", df_p, key_cols=['user_id']):
            st.session_state.db["profile"] = {"height": h_v, "weight": w_v, "goal": g_v}
            st.success("保存完了！")

with st.sidebar.expander("📊 記録項目の管理"):
    new_m = st.text_input("新規項目名（ハンドリング等）")
    if st.button("項目を追加") and new_m:
        if new_m not in db["metrics_defs"]:
            db["metrics_defs"].append(new_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(db["metrics_defs"]), "metric_defs": db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df_s)
            st.rerun()
    
    if db["metrics_defs"]:
        st.divider()
        del_m = st.selectbox("削除する項目", db["metrics_defs"])
        if st.button("選択項目を削除"):
            db["metrics_defs"].remove(del_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(db["metrics_defs"]), "metric_defs": db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df_s)
            st.rerun()

st.sidebar.divider()
uploaded_file = st.sidebar.file_uploader("写真分析（食事やフォーム）", type=["jpg", "png", "jpeg"])

# --- 6. メイン画面 ---
st.title(f"🏃‍♂️ AI Trainer Pro: {login_id}")
tabs = st.tabs(["📅 カレンダー", "📋 今日のメニュー", "📈 グラフ", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()

# --- Tab 1: カレンダー ---
with tabs[0]:
    st.header(f"🗓️ {today.strftime('%Y年 %m月')}")
    cal = calendar.monthcalendar(today.year, today.month)
    cols_h = st.columns(7)
    for i, d in enumerate(["月", "火", "水", "木", "金", "土", "日"]): cols_h[i].write(f"**{d}**")
    for week in cal:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day != 0:
                d_str = f"{today.year}-{today.month:02d}-{day:02d}"
                rate = db["history"].get(d_str, -1)
                color = "#FF4B4B" if float(rate) >= 0.8 else "gray" if rate == -1 else "#007BFF"
                cols[i].markdown(f'<div style="background:{color};color:white;padding:10px;text-align:center;border-radius:5px;min-height:50px;">{day}</div>', unsafe_allow_html=True)

# --- Tab 2: 今日のメニュー ---
with tabs[1]:
    st.info(f"**【コーチからの伝言】**\n{db.get('daily_message', '生成してください')}")
    
    if st.button("AIメニューを新しく生成"):
        res = model.generate_content("バスケの室内練習タスクを4つ [MESSAGE]...[/MESSAGE] で出力。'-'で始めて。")
        db["daily_message"] = re.search(r"\[MESSAGE\](.*
