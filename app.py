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
st.set_page_config(page_title="AI Trainer Pro: Final Beta", layout="wide")

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    genai.configure(api_key=API_KEY)
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"初期設定エラー: {e}")
    st.stop()

# --- 2. データ復元・保存ロジック（ここを大幅強化） ---
def load_data(user_id):
    u_id_key = str(user_id).strip().lower()
    
    # 全データを初期化
    db = {
        "profile": {"height": 170.0, "weight": 65.0, "goal": "目標未設定"},
        "line": {"token": "", "uid": "", "en": False},
        "history": {}, "notes": {}, "metrics_data": pd.DataFrame(),
        "metrics_defs": ["体重"], "daily_message": "メニューを生成してください",
        "tasks": [], "roadmap": ""
    }

    try:
        # 強制的に最新データを読み込み (ttl=0)
        p_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0).copy()
        s_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Settings", ttl=0).copy()
        h_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="History", ttl=0).copy()
        m_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Metrics", ttl=0).copy()

        # 全シートの列名を「小文字・空白なし」に統一
        for df in [p_df, s_df, h_df, m_df]:
            df.columns = [str(c).lower().strip() for c in df.columns]
            if 'user_id' in df.columns:
                df['user_id_fixed'] = df['user_id'].astype(str).str.strip().str.lower()

        # 1. Profiles (プロフィール、ロードマップ、タスク)
        match_p = p_df[p_df['user_id_fixed'] == u_id_key].to_dict('records')
        if match_p:
            p = match_p[0]
            db["profile"] = {"height": p.get('height', 170.0), "weight": p.get('weight', 65.0), "goal": p.get('goal', "")}
            db["line"] = {"token": p.get('line_token', ""), "uid": p.get('line_user_id', ""), "en": str(p.get('line_enabled', '')).lower() == 'true'}
            db["daily_message"] = p.get('daily_message', db["daily_message"])
            db["roadmap"] = str(p.get('roadmap', "")) if pd.notna(p.get('roadmap')) else ""
            t_json = p.get('tasks_json', "[]")
            db["tasks"] = json.loads(t_json) if t_json and str(t_json) != "nan" else []

        # 2. Settings (追加項目：ハンドリングスピード等)
        if not s_df.empty:
            user_metrics = s_df[s_df['user_id_fixed'] == u_id_key]['metric_defs'].dropna().unique().tolist()
            if user_metrics:
                db["metrics_defs"] = sorted(list(set(user_metrics + ["体重"])))

        # 3. History & Metrics
        if not h_df.empty:
            sub_h = h_df[h_df['user_id_fixed'] == u_id_key]
            db["history"] = sub_h.set_index('date')['rate'].to_dict()
            db["notes"] = sub_h.set_index('date')['note'].to_dict()
        if not m_df.empty:
            db["metrics_data"] = m_df[m_df['user_id_fixed'] == u_id_key]

        return db
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
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

# --- 3. ログイン管理 ---
st.sidebar.title("🔑 ログイン")
login_id = st.sidebar.text_input("ユーザーID", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    st.session_state.db = load_data(login_id)
    st.session_state.current_user = login_id

db = st.session_state.db

# モデル設定
selected_model = st.sidebar.selectbox("🚀 AIモデル", ["gemini-1.5-flash", "gemini-pro"], index=0)
model = genai.GenerativeModel(selected_model)

# --- 4. サイドバー：各種設定 ---
with st.sidebar.expander("👤 プロフィール・LINE・項目"):
    new_h = st.number_input("身長 (cm)", value=float(db["profile"]["height"]))
    new_w = st.number_input("体重 (kg)", value=float(db["profile"]["weight"]))
    new_g = st.text_area("目標", value=db["profile"]["goal"])
    l_at = st.text_input("LINEトークン", value=db["line"]["token"], type="password")
    l_ui = st.text_input("宛先UID", value=db["line"]["uid"])
    l_en = st.checkbox("LINE有効", value=db["line"]["en"])
    
    if st.button("全設定を保存"):
        t_json = json.dumps(db["tasks"], ensure_ascii=False)
        df_p = pd.DataFrame([{
            "user_id": login_id, "height": new_h, "weight": new_w, "goal": new_g,
            "line_token": l_at, "line_user_id": l_ui, "line_enabled": l_en,
            "daily_message": db["daily_message"], "tasks_json": t_json, "roadmap": db["roadmap"]
        }])
        if save_to_gs("Profiles", df_p, keys=['user_id']):
            st.session_state.db = load_data(login_id) # 再読み込み
            st.success("保存完了！")

    st.divider()
    new_m = st.text_input("追加項目 (例:ハンドリング)")
    if st.button("項目追加") and new_m:
        db["metrics_defs"].append(new_m)
        df_s = pd.DataFrame({"user_id": [login_id]*len(db["metrics_defs"]), "metric_defs": db["metrics_defs"]})
        save_to_gs("Settings", df_s, keys=['user_id', 'metric_defs'])
        st.rerun()

# 【重要】デバッグ用パネル（不具合時はここを確認してください）
with st.sidebar.expander("🛠️ 通信診断"):
    st.write("読み込んだ項目名:", db["metrics_defs"])
    st.write("ロードマップ文字数:", len(db["roadmap"]))
    if st.button("強制再読み込み"):
        st.session_state.db = load_data(login_id)
        st.rerun()

# --- 5. メイン画面 ---
tabs = st.tabs(["📅 カレンダー", "📋 メニュー", "📈 グラフ", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()

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

with tabs[1]: # メニュー
    st.info(f"**コーチ:** {db.get('daily_message')}")
    if st.button("メニュー生成"):
        res = model.generate_content("バスケ練習タスク4つを [MESSAGE]...[/MESSAGE] で。")
        db["daily_message"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", res.text, re.DOTALL).group(1).strip()
        tasks = [l.strip("- *") for l in res.text.split("\n") if l.strip().startswith(("-", "*"))]
        db["tasks"] = [{"task": t, "done": False} for t in tasks][:4]
        # 生成直後にProfilesへ保存
        save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "tasks_json": json.dumps(db["tasks"], ensure_ascii=False), "daily_message": db["daily_message"]}]), keys=['user_id'])
        st.rerun()

    col_l, col_r = st.columns([2, 1])
    with col_l:
        for i, t in enumerate(db["tasks"]):
            db["tasks"][i]["done"] = st.checkbox(t["task"], value=t["done"], key=f"tk_{i}_{t['task']}")
        done_n = sum(1 for t in db["tasks"] if t["done"])
        rate = done_n / len(db["tasks"]) if db["tasks"] else 0
        st.metric("達成率", f"{int(rate*100)}%")
        free_note = st.text_area("メモ", value=db["notes"].get(str(today), ""))

    with col_r:
        st.write("📊 数値入力")
        today_m = {m: st.number_input(m, value=0.0, key=f"iv_{m}") for m in db["metrics_defs"]}

    if st.button("🚀 保存 & 報告"):
        t_json = json.dumps(db["tasks"], ensure_ascii=False)
        save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "tasks_json": t_json, "daily_message": db["daily_message"], "roadmap": db["roadmap"]}]), keys=['user_id'])
        save_to_gs("History", pd.DataFrame([{"user_id": login_id, "date": str(today), "rate": rate, "note": free_note}]))
        save_to_gs("Metrics", pd.DataFrame([{"user_id": login_id, "date": str(today), "metric_name": k, "value": v} for k, v in today_m.items()]), keys=['user_id', 'date', 'metric_name'])
        
        if db["line"]["en"] and db["line"]["token"]:
            m_dt = "\n".join([f"・{k}: {v}" for k, v in today_m.items() if v > 0])
            msg = f"【{login_id} 報告】\n達成率: {int(rate*100)}%\n記録:\n{m_dt}\nメモ:\n{free_note}"
            requests.post("https://api.line.me/v2/bot/message/push", headers={"Authorization": f"Bearer {db['line']['token']}", "Content-Type": "application/json"}, json={"to": db["line"]["uid"], "messages": [{"type": "text", "text": msg}]})
        st.success("同期完了！")
        st.rerun()

with tabs[2]: # グラフ
    if not db["metrics_data"].empty:
        sel = st.selectbox("項目を選択", db["metrics_defs"])
        plot_df = db["metrics_data"][db["metrics_data"]['metric_name'] == sel].copy()
        if not plot_df.empty:
            plot_df['date'] = pd.to_datetime(plot_df['date'])
            st.line_chart(plot_df.sort_values('date').set_index('date')['value'])

with tabs[3]: # ロードマップ
    if st.button("ロードマップ生成"):
        res = model.generate_content("バスケ目標達成戦略をMermaid mindmapで。```mermaid...```で囲んで。")
        match = re.search(r"```mermaid\s*(.*?)\s*```", res.text, re.DOTALL)
        if match:
            db["roadmap"] = match.group(1)
            save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "roadmap": db["roadmap"]}]), keys=['user_id'])
            st.rerun()
    if db.get("roadmap"):
        st.components.v1.html(f'<div class="mermaid" style="display:flex;justify-content:center;">{db["roadmap"]}</div><script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";mermaid.initialize({{startOnLoad:true, theme: "neutral"}});</script>', height=500)

with tabs[4]: # 相談
    chat_in = st.chat_input("相談を入力")
    if chat_in:
        uploaded_file = st.sidebar.file_uploader("写真アップ", type=["jpg","png","jpeg"], key="chat_up")
        inputs = [chat_in, Image.open(uploaded_file)] if uploaded_file else [chat_in]
        st.chat_message("assistant").write(model.generate_content(inputs).text)
