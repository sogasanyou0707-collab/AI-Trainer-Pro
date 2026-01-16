import streamlit as st
import google.generativeai as genai
import re
from PIL import Image
import datetime
import calendar
import pandas as pd
import requests
from streamlit_gsheets import GSheetsConnection

# ==========================================
# 1. ページ基本設定 ＆ Secrets読み込み
# ==========================================
st.set_page_config(page_title="AI Trainer Pro: Ultimate", layout="wide")

try:
    # Secretsから各種情報を取得
    API_KEY = st.secrets["GEMINI_API_KEY"]
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    
    # Gemini設定 (Gemini 3を指定)
    genai.configure(api_key=API_KEY)
    # 接続テストも兼ねてモデルを定義
    model_name = "gemini-3-flash-preview"
    
    # スプレッドシート接続初期化
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"初期設定エラー: Secretsやネットワークを確認してください。 {e}")
    st.stop()

# ==========================================
# 2. データ読み書き関数 (列名不一致対策済み)
# ==========================================

def load_full_data_gs(user_id):
    """スプレッドシートからユーザーデータを一括取得"""
    default_data = {
        "profile": {"height": 170.0, "weight": 65.0, "goal": "未設定"},
        "history": {},
        "metrics_data": pd.DataFrame(),
        "metrics_defs": ["体重"],
        "line_config": {"access_token": "", "user_id": "", "enabled": False},
        "daily_message": "準備はいいか！限界を超えていこう！",
        "tasks": [], "roadmap": ""
    }
    try:
        # 各シートの読み込み（列名は小文字 user_id で統一）
        p_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0)
        h_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="History", ttl=0)
        m_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Metrics", ttl=0)
        s_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Settings", ttl=0)

        # データのフィルタリング (user_id が一致するもの)
        prof = p_df[p_df['user_id'].astype(str) == str(user_id)].to_dict('records')
        hist = h_df[h_df['user_id'].astype(str) == str(user_id)]
        metr = m_df[m_df['user_id'].astype(str) == str(user_id)]
        sett = s_df[s_df['user_id'].astype(str) == str(user_id)]

        if prof:
            p = prof[0]
            default_data["profile"] = {"height": p.get('height', 170), "weight": p.get('weight', 65), "goal": p.get('goal', "未設定")}
            default_data["line_config"] = {
                "access_token": p.get('line_token', ""),
                "user_id": p.get('line_user_id', ""),
                "enabled": p.get('line_enabled', False)
            }
            default_data["daily_message"] = p.get('daily_message', "準備はいいか！")

        if not hist.empty:
            default_data["history"] = hist.set_index('date')['rate'].to_dict()
        
        if not metr.empty:
            default_data["metrics_data"] = metr
            
        if not sett.empty:
            default_data["metrics_defs"] = sett['metric_defs'].unique().tolist()

        return default_data
    except Exception as e:
        return default_data

def save_to_gs(worksheet_name, new_df, key_cols=['user_id', 'date']):
    """スプレッドシートの指定シートを更新"""
    try:
        existing_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        if key_cols:
            combined = combined.drop_duplicates(subset=key_cols, keep='last')
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=combined)
        return True
    except Exception as e:
        st.error(f"保存エラー ({worksheet_name}): {e}")
        return False

# ==========================================
# 3. ログイン管理
# ==========================================

st.sidebar.title("🔑 ログイン")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.get("current_user") != login_id:
    st.session_state.db = load_full_data_gs(login_id)
    st.session_state.current_user = login_id

# AIコーチ設定
selected_coach = st.sidebar.selectbox("コーチ選択", ["熱血コーチ", "論理派トレーナー"])
uploaded_file = st.sidebar.file_uploader("写真分析 (食事・フォーム等)", type=["jpg", "jpeg", "png"])
ai_model = genai.GenerativeModel(model_name, system_instruction=f"あなたは{selected_coach}です。ユーザー:{login_id}、目標:{st.session_state.db['profile']['goal']}")

# ==========================================
# 4. サイドバー設定メニュー
# ==========================================

with st.sidebar.expander("🎯 プロフィール設定"):
    h_val = st.number_input("身長 (cm)", value=float(st.session_state.db["profile"]["height"]))
    w_val = st.number_input("体重 (kg)", value=float(st.session_state.db["profile"]["weight"]))
    g_val = st.text_area("目標", value=st.session_state.db["profile"]["goal"])
    if st.button("プロフィールの保存"):
        df = pd.DataFrame([{
            "user_id": login_id, "height": h_val, "weight": w_val, "goal": g_val,
            "line_token": st.session_state.db["line_config"]["access_token"],
            "line_user_id": st.session_state.db["line_config"]["user_id"],
            "line_enabled": st.session_state.db["line_config"]["enabled"],
            "daily_message": st.session_state.db["daily_message"]
        }])
        if save_to_gs("Profiles", df, key_cols=['user_id']):
            st.session_state.db["profile"] = {"height": h_val, "weight": w_val, "goal": g_val}
            st.success("保存しました！")

with st.sidebar.expander("📊 記録項目の管理"):
    new_m = st.text_input("追加する項目")
    if st.button("項目追加") and new_m:
        if new_m not in st.session_state.db["metrics_defs"]:
            st.session_state.db["metrics_defs"].append(new_m)
            df = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df)
            st.rerun()

# ==========================================
# 5. メイン画面
# ==========================================

st.title(f"🔥 AI Trainer Pro: {login_id}")
tabs = st.tabs(["📅 カレンダー", "📋 メニュー", "📈 グラフ", "🏆 称号", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()

# --- Tab 1: カレンダー ---
with tabs[0]:
    cal_grid = calendar.monthcalendar(today.year, today.month)
    cols = st.columns(7)
    for i, d in enumerate(["月", "火", "水", "木", "金", "土", "日"]): cols[i].centered_text = d
    for week in cal_grid:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day != 0:
                d_key = f"{today.year}-{today.month:02d}-{day:02d}"
                rate = st.session_state.db["history"].get(d_key, -1)
                color = "#FF4B4B" if float(rate) >= 0.8 else "gray"
                cols[i].markdown(f'<div style="border:1px solid #ddd;text-align:center;padding:5px;border-radius:5px;background-color:{color if rate != -1 else "transparent"};color:{"white" if rate != -1 else "black"};">{day}</div>', unsafe_allow_html=True)

# --- Tab 2: 今日のメニュー ---
with tabs[1]:
    st.info(f"**コーチより:** {st.session_state.db['daily_message']}")
    if st.button("メニュー生成"):
        res = ai_model.generate_content("タスク4つと励ましを [MESSAGE]...[/MESSAGE] で出力して。")
        st.session_state.db["daily_message"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", res.text, re.DOTALL).group(1).strip()
        tasks = [l.strip("- *") for l in res.text.split("\n") if l.strip().startswith(("-", "*"))]
        st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks[:4]]
        st.rerun()

    for i, t in enumerate(st.session_state.db["tasks"]):
        st.session_state.db["tasks"][i]["done"] = st.checkbox(t["task"], value=t["done"], key=f"tk_{i}")

    if st.button("本日の成果を保存"):
        done = sum(1 for t in st.session_state.db["tasks"] if t["done"])
        rate = done / len(st.session_state.db["tasks"]) if st.session_state.db["tasks"] else 0
        h_df = pd.DataFrame([{"user_id": login_id, "date": str(today), "rate": rate}])
        save_to_gs("History", h_df)
        st.balloons()
        st.success("スプレッドシートに記録しました！")

# --- Tab 5: ロードマップ (Mermaid) ---
with tabs[4]:
    if st.button("ロードマップ生成"):
        res = ai_model.generate_content("目標達成への道筋をMermaid形式のmindmapで作成して。```mermaid...```で囲むこと。")
        match = re.search(r"```mermaid\s*(.*?)\s*```", res.text, re.DOTALL)
        if match: st.session_state.db["roadmap"] = match.group(1)
    
    if st.session_state.db.get("roadmap"):
        st.components.v1.html(f"""
            <div class="mermaid">{st.session_state.db["roadmap"]}</div>
            <script type="module">
                import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                mermaid.initialize({{ startOnLoad: true }});
            </script>
        """, height=500)

# --- Tab 6: 相談 (画像分析対応) ---
with tabs[5]:
    chat_input = st.chat_input("コーチに相談...")
    if chat_input:
        inputs = [chat_input, Image.open(uploaded_file)] if uploaded_file else [chat_input]
        response = ai_model.generate_content(inputs)
        st.write(f"**AIコーチ:** {response.text}")
