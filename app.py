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

# --- 1. 基本設定 ---
st.set_page_config(page_title="AI Trainer Pro: Ultimate v2.5", layout="wide")

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    genai.configure(api_key=API_KEY)
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"接続設定を確認してください: {e}")
    st.stop()

# --- 2. データ読み込み関数 ---
def load_app_data(user_id):
    u_id_key = str(user_id).strip().lower()
    db = {
        "profile": {"height": 170.0, "weight": 65.0, "goal": ""},
        "line": {"token": "", "uid": "", "en": False},
        "history": {}, "notes": {}, "metrics_data": pd.DataFrame(),
        "metrics_defs": ["体重"], "daily_message": "メニューを生成してください",
        "tasks": [], "roadmap": ""
    }
    try:
        # キャッシュ無効化で読み込み
        p_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0).copy()
        s_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Settings", ttl=0).copy()
        h_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="History", ttl=0).copy()
        m_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Metrics", ttl=0).copy()

        # 列名・IDの正規化
        for df in [p_df, s_df, h_df, m_df]:
            df.columns = [str(c).lower().strip() for c in df.columns]
            if 'user_id' in df.columns:
                df['uid_match'] = df['user_id'].astype(str).str.strip().str.lower()

        # Profiles
        match_p = p_df[p_df['uid_match'] == u_id_key].to_dict('records')
        if match_p:
            p = match_p[0]
            db["profile"] = {"height": float(p.get('height', 170)), "weight": float(p.get('weight', 65)), "goal": str(p.get('goal', ""))}
            db["line"] = {"token": str(p.get('line_token', "")), "uid": str(p.get('line_user_id', "")), "en": str(p.get('line_enabled', '')).lower() == 'true'}
            db["daily_message"] = str(p.get('daily_message', db["daily_message"]))
            db["roadmap"] = str(p.get('roadmap', ""))
            t_json = p.get('tasks_json', "[]")
            db["tasks"] = json.loads(t_json) if t_json and str(t_json) != "nan" else []

        # Settings
        if not s_df.empty:
            m_items = s_df[s_df['uid_match'] == u_id_key]['metric_defs'].dropna().unique().tolist()
            if m_items: db["metrics_defs"] = sorted(list(set(m_items + ["体重"])))

        # History & Metrics
        if not h_df.empty:
            sub_h = h_df[h_df['uid_match'] == u_id_key]
            db["history"] = sub_h.set_index('date')['rate'].to_dict()
            db["notes"] = sub_h.set_index('date')['note'].to_dict()
        if not m_df.empty:
            db["metrics_data"] = m_df[m_df['uid_match'] == u_id_key]

        return db
    except:
        return db

def save_to_gs(worksheet, df, keys=['user_id', 'date']):
    try:
        df.columns = [str(c).lower().strip() for c in df.columns]
        old_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet, ttl=0).copy()
        old_df.columns = [str(c).lower().strip() for c in old_df.columns]
        combined = pd.concat([old_df, df], ignore_index=True).drop_duplicates(subset=[k.lower() for k in keys], keep='last')
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet, data=combined)
        return True
    except:
        return False

# --- 3. ログイン ＆ セッション管理 ---
st.sidebar.title("🔑 ログイン設定")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    # ログイン時にデータをSession Stateに強制セット
    db = load_app_data(login_id)
    st.session_state.db = db
    st.session_state.current_user = login_id
    
    # ウィジェットの初期値をSession Stateに強制注入
    st.session_state["h_val"] = float(db["profile"]["height"])
    st.session_state["w_val"] = float(db["profile"]["weight"])
    st.session_state["g_val"] = db["profile"]["goal"]
    st.session_state["l_token"] = db["line"]["token"]
    st.session_state["l_uid"] = db["line"]["uid"]
    st.session_state["l_en"] = db["line"]["en"]

db = st.session_state.db
model = genai.GenerativeModel("gemini-1.5-flash")

# --- 4. サイドバー：復旧機能 ---
st.sidebar.divider()
selected_coach = st.sidebar.selectbox("🤖 コーチ選択", ["バスケットコーチ", "熱血コーチ", "論理派トレーナー"])

with st.sidebar.expander("👤 プロフィール・LINE・項目設定", expanded=True):
    h_input = st.number_input("身長 (cm)", key="h_val", step=0.1)
    w_input = st.number_input("体重 (kg)", key="w_val", step=0.1)
    g_input = st.text_area("目標", key="g_val")
    
    st.divider()
    l_at = st.text_input("LINEトークン", key="l_token", type="password")
    l_ui = st.text_input("宛先UID", key="l_uid")
    l_en = st.checkbox("LINE報告有効", key="l_en")
    
    if st.button("全設定を保存して同期"):
        t_json = json.dumps(db["tasks"], ensure_ascii=False)
        df_p = pd.DataFrame([{
            "user_id": login_id, "height": h_input, "weight": w_input, "goal": g_input,
            "line_token": l_at, "line_user_id": l_ui, "line_enabled": l_en,
            "daily_message": db["daily_message"], "tasks_json": t_json, "roadmap": db["roadmap"]
        }])
        if save_to_gs("Profiles", df_p, keys=['user_id']):
            st.session_state.db = load_app_data(login_id)
            st.success("同期完了！")
            st.rerun()

    st.divider()
    new_m = st.text_input("項目追加")
    if st.button("追加") and new_m:
        db["metrics_defs"].append(new_m)
        df_s = pd.DataFrame({"user_id": [login_id]*len(db["metrics_defs"]), "metric_defs": db["metrics_defs"]})
        save_to_gs("Settings", df_s, keys=['user_id', 'metric_defs'])
        st.rerun()
    
    # 【復旧】項目削除
    if db["metrics_defs"]:
        del_m = st.selectbox("項目削除", db["metrics_defs"])
        if st.button("削除実行"):
            db["metrics_defs"].remove(del_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(db["metrics_defs"]), "metric_defs": db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df_s)
            st.rerun()

st.sidebar.divider()
uploaded_file = st.sidebar.file_uploader("📸 写真分析 (食事・フォーム)", type=["jpg", "png", "jpeg"])

with st.sidebar.expander("🛠️ システム診断"):
    st.write(f"ID: `{login_id}`")
    st.write(f"ロードマップ保持: {'あり' if db['roadmap'] else 'なし'}")
    st.write(f"読み込み項目: {db['metrics_defs']}")
    if st.button("強制データ更新"):
        st.session_state.db = load_app_data(login_id)
        st.rerun()

# --- 5. メイン画面 ---
tabs = st.tabs(["📅 カレンダー", "📋 メニュー", "📈 グラフ", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()

# --- 各タブの内容 ---
with tabs[0]: # カレンダー
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
                cols[i].markdown(f'<div style="background:{color};color:white;padding:10px;text-align:center;border-radius:5px;">{day}</div>', unsafe_allow_html=True)

with tabs[1]: # 今日のメニュー
    st.info(f"**コーチからの伝言:** {db.get('daily_message')}")
    if st.button("AIメニューを生成"):
        res = model.generate_content("目標達成のためのタスク4つと励ましを [MESSAGE]...[/MESSAGE] で。")
        db["daily_message"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", res.text, re.DOTALL).group(1).strip()
        tasks = [l.strip("- *") for l in res.text.split("\n") if l.strip().startswith(("-", "*"))]
        db["tasks"] = [{"task": t, "done": False} for t in tasks][:4]
        save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "tasks_json": json.dumps(db["tasks"], ensure_ascii=False), "daily_message": db["daily_message"]}]), keys=['user_id'])
        st.rerun()

    col_l, col_r = st.columns([2, 1])
    with col_l:
        for i, t in enumerate(db["tasks"]):
            db["tasks"][i]["done"] = st.checkbox(t["task"], value=t["done"], key=f"tk_{i}_{t['task']}")
        done_n = sum(1 for t in db["tasks"] if t["done"])
        rate = done_n / len(db["tasks"]) if db["tasks"] else 0
        st.metric("達成率", f"{int(rate*100)}%")
        note = st.text_area("頑張りメモ")

    with col_r:
        # 【解決】追加された「ハンドリングスピード」等が確実にここに並ぶ
        st.write("📊 数値記録")
        cur_m = {m: st.number_input(m, value=0.0, key=f"inp_{m}") for m in db["metrics_defs"]}

    if st.button("🚀 保存 & LINE報告"):
        t_json = json.dumps(db["tasks"], ensure_ascii=False)
        save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "tasks_json": t_json, "roadmap": db["roadmap"]}]), keys=['user_id'])
        save_to_gs("History", pd.DataFrame([{"user_id": login_id, "date": str(today), "rate": rate, "note": note}]))
        save_to_gs("Metrics", pd.DataFrame([{"user_id": login_id, "date": str(today), "metric_name": k, "value": v} for k, v in cur_m.items()]), keys=['user_id', 'date', 'metric_name'])
        
        if db["line"]["en"] and db["line"]["token"]:
            m_str = "\n".join([f"・{k}: {v}" for k, v in cur_m.items() if v > 0])
            requests.post("https://api.line.me/v2/bot/message/push", headers={"Authorization": f"Bearer {db['line']['token']}", "Content-Type": "application/json"}, 
                          json={"to": db["line"]["uid"], "messages": [{"type": "text", "text": f"【{login_id} 報告】\n達成率: {int(rate*100)}%\n記録:\n{m_str}\nメモ:\n{note}"}]})
        st.success("全て同期完了！")
        st.rerun()

with tabs[2]: # グラフ
    if not db["metrics_data"].empty:
        sel = st.selectbox("表示項目", db["metrics_defs"])
        plot_df = db["metrics_data"][db["metrics_data"]['metric_name'] == sel].copy()
        if not plot_df.empty:
            plot_df['date'] = pd.to_datetime(plot_df['date'])
            st.line_chart(plot_df.sort_values('date').set_index('date')['value'])

with tabs[3]: # ロードマップ
    if st.button("AIロードマップ生成"):
        res = model.generate_content("バスケ目標達成までの戦略をMermaid mindmapで。```mermaid...```で囲んで。")
        match = re.search(r"```mermaid\s*(.*?)\s*```", res.text, re.DOTALL)
        if match:
            db["roadmap"] = match.group(1)
            save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "roadmap": db["roadmap"]}]), keys=['user_id'])
            st.rerun()
    if db.get("roadmap"):
        st.components.v1.html(f'<div class="mermaid" style="display:flex;justify-content:center;">{db["roadmap"]}</div><script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";mermaid.initialize({{startOnLoad:true, theme: "neutral"}});</script>', height=500)

with tabs[4]: # 相談
    chat_in = st.chat_input("相談を入力...")
    if chat_in:
        inputs = [chat_in, Image.open(uploaded_file)] if uploaded_file else [chat_in]
        st.chat_message("assistant").write(model.generate_content(inputs).text)
