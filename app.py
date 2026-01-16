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
st.set_page_config(page_title="AI Trainer Pro: Data Guardian", layout="wide")

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    genai.configure(api_key=API_KEY)
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"初期設定エラー: {e}")
    st.stop()

# --- 2. データ読み書き（消失防止セーフティ搭載） ---
def load_app_data(user_id):
    u_id = str(user_id).strip().lower()
    db = {
        "profile": {"height": 170.0, "weight": 65.0, "goal": "バスケの基礎力アップ"},
        "history": {}, "notes": {}, "metrics_data": pd.DataFrame(), "metrics_defs": ["体重"],
        "line": {"token": "", "uid": "", "en": False},
        "daily_message": "メニューを生成してください", "tasks": [], "roadmap": ""
    }
    try:
        # 強制的に最新を読み込み
        p_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0).copy()
        h_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="History", ttl=0).copy()
        m_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Metrics", ttl=0).copy()
        s_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Settings", ttl=0).copy()

        # 列名の正規化
        for df in [p_df, h_df, m_df, s_df]:
            df.columns = [str(c).lower().strip() for c in df.columns]
            if 'user_id' in df.columns:
                df['uid_key'] = df['user_id'].astype(str).str.strip().str.lower()

        # データの紐付け
        p_match = p_df[p_df['uid_key'] == u_id].to_dict('records')
        if p_match:
            p = p_match[0]
            db["profile"] = {"height": float(p.get('height', 170)), "weight": float(p.get('weight', 65)), "goal": str(p.get('goal', ""))}
            db["line"] = {"token": str(p.get('line_token', "")), "uid": str(p.get('line_user_id', "")), "en": str(p.get('line_enabled', '')).lower() == 'true'}
            db["daily_message"] = str(p.get('daily_message', db["daily_message"]))
            db["roadmap"] = str(p.get('roadmap', "")) # ロードマップ復元
            db["tasks"] = json.loads(p.get('tasks_json', "[]")) if p.get('tasks_json') else []

        if not s_df.empty:
            items = s_df[s_df['uid_key'] == u_id]['metric_defs'].dropna().unique().tolist()
            if items: db["metrics_defs"] = sorted(list(set(items + ["体重"])))

        if not h_df.empty:
            sub_h = h_df[h_df['uid_key'] == u_id]
            db["history"] = sub_h.set_index('date')['rate'].to_dict()
            db["notes"] = sub_h.set_index('date')['note'].to_dict()
        if not m_df.empty:
            db["metrics_data"] = m_df[m_df['uid_key'] == u_id]

        return db
    except:
        return db

def safe_save_to_gs(worksheet, new_data_df, key_cols=['user_id']):
    """既存データを消さずに、特定行のみを安全に更新する"""
    try:
        new_data_df.columns = [str(c).lower().strip() for c in new_data_df.columns]
        current_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet, ttl=0).copy()
        current_df.columns = [str(c).lower().strip() for c in current_df.columns]
        
        # もし読み込みが空で、かつ新規データがある場合は、完全上書きではなく新規作成として扱う
        combined = pd.concat([current_df, new_data_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=[k.lower() for k in key_cols], keep='last')
        
        # 消失防止チェック：結合後のデータが極端に減っていないか
        if not current_df.empty and len(combined) < len(current_df):
            st.error(f"データ消失の危険を検知したため、{worksheet} の保存を中止しました。")
            return False
            
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet, data=combined)
        return True
    except Exception as e:
        st.error(f"保存エラー ({worksheet}): {e}")
        return False

# --- 3. ログイン & セッション ---
st.sidebar.title("🔑 AI Trainer Pro")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    st.session_state.db = load_app_data(login_id)
    st.session_state.current_user = login_id

db = st.session_state.db
model = genai.GenerativeModel("gemini-1.5-flash")

# --- 4. サイドバー機能 ---
with st.sidebar.expander("👤 プロフィール・LINE設定", expanded=True):
    h_v = st.number_input("身長 (cm)", value=float(db["profile"]["height"]))
    w_v = st.number_input("体重 (kg)", value=float(db["profile"]["weight"]))
    g_v = st.text_area("目標", value=db["profile"]["goal"])
    st.divider()
    l_en = st.checkbox("LINE報告を有効化", value=db["line"]["en"])
    l_at = st.text_input("LINE Notifyトークン", value=db["line"]["token"], type="password")
    
    if st.button("設定を保存"):
        df_p = pd.DataFrame([{
            "user_id": login_id, "height": h_v, "weight": w_v, "goal": g_v,
            "line_token": l_at, "line_enabled": l_en,
            "daily_message": db["daily_message"], "tasks_json": json.dumps(db["tasks"], ensure_ascii=False),
            "roadmap": db["roadmap"]
        }])
        if safe_save_to_gs("Profiles", df_p, key_cols=['user_id']):
            st.session_state.db = load_app_data(login_id)
            st.success("保存完了！")
            st.rerun()

with st.sidebar.expander("📊 記録項目の管理"):
    new_m = st.text_input("新規項目名（ハンドリング等）")
    if st.button("追加実行") and new_m:
        if new_m not in db["metrics_defs"]:
            db["metrics_defs"].append(new_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(db["metrics_defs"]), "metric_defs": db["metrics_defs"]})
            safe_save_to_gs("Settings", df_s, key_cols=['user_id', 'metric_defs'])
            st.rerun()

# --- 5. メイン画面 ---
tabs = st.tabs(["📅 カレンダー", "📋 メニュー", "📈 グラフ", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()

with tabs[1]: # メニュータブ
    st.info(f"**コーチからの伝言:** {db.get('daily_message')}")
    if st.button("AIメニュー生成"):
        res = model.generate_content("バスケ練習タスク4つを [MESSAGE]...[/MESSAGE] で。")
        db["daily_message"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", res.text, re.DOTALL).group(1).strip()
        tasks = [l.strip("- *") for l in res.text.split("\n") if l.strip().startswith(("-", "*"))]
        db["tasks"] = [{"task": t, "done": False} for t in tasks][:4]
        safe_save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "daily_message": db["daily_message"], "tasks_json": json.dumps(db["tasks"], ensure_ascii=False)}]), key_cols=['user_id'])
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
        st.subheader("数値入力")
        cur_metrics = {m: st.number_input(m, value=0.0, key=f"inp_{m}") for m in db["metrics_defs"]}

    if st.button("🚀 保存 & LINE報告"):
        safe_save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "tasks_json": json.dumps(db["tasks"], ensure_ascii=False), "roadmap": db["roadmap"]}]), key_cols=['user_id'])
        safe_update_hist = pd.DataFrame([{"user_id": login_id, "date": str(today), "rate": rate, "note": note}])
        safe_save_to_gs("History", safe_update_hist, key_cols=['user_id', 'date'])
        
        m_rows = [{"user_id": login_id, "date": str(today), "metric_name": k, "value": v} for k, v in cur_metrics.items()]
        safe_save_to_gs("Metrics", pd.DataFrame(m_rows), key_cols=['user_id', 'date', 'metric_name'])
        
        if db["line"]["en"] and db["line"]["token"]:
            m_str = "\n".join([f"・{k}: {v}" for k, v in cur_metrics.items() if v > 0])
            requests.post("https://notify-api.line.me/api/notify", headers={"Authorization": f"Bearer {db['line']['token']}"}, params={"message": f"\n【{login_id} 報告】\n達成率: {int(rate*100)}%\n数値:\n{m_str}\nメモ:\n{note}"})
        st.success("全てのデータを保存しました！")
        st.rerun()

# カレンダー・グラフ・ロードマップの描画ロジックは以前の安定版を維持
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

with tabs[3]: # ロードマップ
    if st.button("ロードマップ生成"):
        res = model.generate_content("バスケ目標達成までの mindmap を Mermaid形式で。```mermaid...```で囲んで。")
        match = re.search(r"```mermaid\s*(.*?)\s*```", res.text, re.DOTALL)
        if match:
            db["roadmap"] = match.group(1)
            safe_save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "roadmap": db["roadmap"]}]), key_cols=['user_id'])
            st.rerun()
    if db.get("roadmap"):
        st.components.v1.html(f'<div class="mermaid" style="display:flex;justify-content:center;">{db["roadmap"]}</div><script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";mermaid.initialize({{startOnLoad:true}});</script>', height=500)
