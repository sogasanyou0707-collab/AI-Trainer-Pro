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
st.set_page_config(page_title="AI Trainer Pro: Stable Restart", layout="wide")

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    genai.configure(api_key=API_KEY)
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"初期設定エラー: {e}")
    st.stop()

# --- 2. モデル取得 ---
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
        # Profiles復元
        prof = p_df[p_df['user_id'].astype(str) == u_id].to_dict('records')
        if prof:
            p = prof[0]
            default_data["profile"] = {"height": p.get('height', 170), "weight": p.get('weight', 65), "goal": p.get('goal', "未設定")}
            default_data["line"] = {"token": p.get('line_token', ""), "uid": p.get('line_user_id', ""), "en": p.get('line_enabled', False)}
            default_data["daily_message"] = p.get('daily_message', "準備はいいか！")
            default_data["roadmap"] = p.get('roadmap', "") # ロードマップ読み込み
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
    system_instruction=f"あなたは{selected_coach}です。小学校6年生の男子が自宅で楽しく続けられるバスケ練習を指導してください。目標:{st.session_state.db['profile']['goal']}"
)

# --- 5. サイドバー機能 ---
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
        df_p = pd.DataFrame([{
            "user_id": login_id, "height": h_v, "weight": w_v, "goal": g_v,
            "line_token": l_at, "line_user_id": l_ui, "line_enabled": l_en,
            "daily_message": db["daily_message"], 
            "tasks_json": json.dumps(db["tasks"], ensure_ascii=False),
            "roadmap": db["roadmap"] # ロードマップも一緒に保存
        }])
        if save_to_gs("Profiles", df_p, key_cols=['user_id']):
            st.session_state.db["profile"] = {"height": h_v, "weight": w_v, "goal": g_v}
            st.success("保存しました！")

with st.sidebar.expander("📊 記録項目の追加・削除"):
    new_m = st.text_input("新規項目名（例：ハンドリングスピード）")
    if st.button("項目を追加") and new_m:
        if new_m not in st.session_state.db["metrics_defs"]:
            st.session_state.db["metrics_defs"].append(new_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df_s)
            st.rerun()
    
    if st.session_state.db["metrics_defs"]:
        del_m = st.selectbox("削除する項目", st.session_state.db["metrics_defs"])
        if st.button("選択項目を削除"):
            st.session_state.db["metrics_defs"].remove(del_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df_s)
            st.rerun()

st.sidebar.divider()
uploaded_file = st.sidebar.file_uploader("写真分析", type=["jpg", "png", "jpeg"])

# --- 6. メイン画面 ---
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
                rate = st.session_state.db["history"].get(d_str, -1)
                color = "#FF4B4B" if float(rate) >= 0.8 else "gray" if rate == -1 else "#007BFF"
                cols[i].markdown(f'<div style="background:{color};color:white;padding:10px;text-align:center;border-radius:5px;min-height:50px;">{day}</div>', unsafe_allow_html=True)

    st.divider()
    selected_date = st.date_input("詳細確認", value=today)
    sel_str = str(selected_date)
    if sel_str in st.session_state.db["notes"]:
        st.info(f"📝 **{sel_str} のメモ:**\n{st.session_state.db['notes'][sel_str]}")

# --- Tab 2: 今日のメニュー ---
with tabs[1]:
    st.info(f"**【{selected_coach}の伝言】**\n{st.session_state.db.get('daily_message')}")
    if st.button("AIメニューを生成"):
        res = model.generate_content("バスケ練習タスク4つを [MESSAGE]...[/MESSAGE] で出力。タスクは '-' で始めて。")
        st.session_state.db["daily_message"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", res.text, re.DOTALL).group(1).strip()
        tasks = [l.strip("- *123. ") for l in res.text.split("\n") if l.strip().startswith(("-", "*", "1."))][:4]
        st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks]
        st.rerun()

    col_l, col_r = st.columns([2, 1])
    with col_l:
        st.subheader("✅ 今日のタスク")
        for i, t in enumerate(st.session_state.db["tasks"]):
            st.session_state.db["tasks"][i]["done"] = st.checkbox(t["task"], value=t["done"], key=f"tk_{i}_{t['task']}")
        done_n = sum(1 for t in st.session_state.db["tasks"] if t["done"])
        rate = done_n / len(st.session_state.db["tasks"]) if st.session_state.db["tasks"] else 0
        st.metric("達成率", f"{int(rate*100)}%")
        st.progress(rate)
        free_report = st.text_area("頑張りメモ", placeholder="自由に入力")

    with col_r:
        st.subheader("📊 数値記録")
        today_metrics = {}
        for m in st.session_state.db["metrics_defs"]:
            today_metrics[m] = st.number_input(f"{m}", value=0.0, key=f"met_{m}")

    if st.button("🚀 保存 & LINE報告"):
        t_json = json.dumps(st.session_state.db["tasks"], ensure_ascii=False)
        # Profiles(タスクとロードマップ)
        save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "tasks_json": t_json, "roadmap": st.session_state.db["roadmap"]}]), key_cols=['user_id'])
        # History
        save_to_gs("History", pd.DataFrame([{"user_id": login_id, "date": str(today), "rate": rate, "note": free_report}]))
        # Metrics
        m_rows = [{"user_id": login_id, "date": str(today), "metric_name": k, "value": v} for k, v in today_metrics.items()]
        save_to_gs("Metrics", pd.DataFrame(m_rows), key_cols=['user_id', 'date', 'metric_name'])
        
        if l_en and l_at:
            msg = f"\n【{login_id} 報告】\n達成率: {int(rate*100)}%\n頑張り: {free_report}\n数値: {today_metrics}"
            requests.post("https://api.line.me/v2/bot/message/push", headers={"Authorization": f"Bearer {l_at}", "Content-Type": "application/json"}, json={"to": l_ui, "messages": [{"type": "text", "text": msg}]})
        st.success("全て保存完了！")
        st.balloons()
        st.rerun()

# --- Tab 3: グラフ ---
with tabs[2]:
    m_data = st.session_state.db.get("metrics_data", pd.DataFrame())
    if not m_data.empty:
        sel_metric = st.selectbox("表示項目", st.session_state.db["metrics_defs"])
        plot_df = m_data[m_data['metric_name'] == sel_metric].copy()
        if not plot_df.empty:
            plot_df['date'] = pd.to_datetime(plot_df['date'])
            st.line_chart(plot_df.sort_values('date').set_index('date')['value'])

# --- Tab 4: ロードマップ ---
with tabs[3]:
    if st.button("AIロードマップ生成"):
        res = model.generate_content("バスケ目標達成までの mindmap を Mermaid形式で。```mermaid...```で囲んで。")
        match = re.search(r"```mermaid\s*(.*?)\s*```", res.text, re.DOTALL)
        if match:
            st.session_state.db["roadmap"] = match.group(1)
            # 生成した瞬間にスプレッドシートにも保存
            save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "roadmap": st.session_state.db["roadmap"]}]), key_cols=['user_id'])
            st.rerun()
    if st.session_state.db.get("roadmap"):
        st.components.v1.html(f'<div class="mermaid" style="display:flex;justify-content:center;">{st.session_state.db["roadmap"]}</div><script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";mermaid.initialize({{startOnLoad:true}});</script>', height=500)

# --- Tab 5: 相談 ---
with tabs[4]:
    chat_in = st.chat_input("コーチに相談...")
    if chat_in:
        inputs = [chat_in, Image.open(uploaded_file)] if uploaded_file else [chat_in]
        st.chat_message("assistant").write(model.generate_content(inputs).text)
