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
st.set_page_config(page_title="AI Trainer Pro: Ultimate v1.6", layout="wide")

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    genai.configure(api_key=API_KEY)
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"初期設定エラー: {e}")
    st.stop()

@st.cache_resource
def get_available_models():
    try:
        models = [m.name.replace("models/", "") for m in genai.list_models() 
                  if "generateContent" in m.supported_generation_methods]
        return models
    except:
        return ["gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-pro"]

available_models = get_available_models()

# --- 2. データ読み書き関数 (最強の復旧ロジック) ---
def load_full_data_gs(user_id):
    # IDを「小文字の文字列」として完全に正規化
    u_id_search = str(user_id).strip().lower()
    
    default_data = {
        "profile": {"height": 170.0, "weight": 65.0, "goal": "バスケのスキルアップ"},
        "history": {}, "notes": {}, "metrics_data": pd.DataFrame(), "metrics_defs": ["体重"],
        "line": {"token": "", "uid": "", "en": False},
        "daily_message": "今日も最高の練習を！", "tasks": [], "roadmap": ""
    }
    
    try:
        # シート読み込み。列名を正規化(小文字)
        def get_df(ws):
            df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=ws, ttl=0)
            df.columns = [str(c).lower().strip() for c in df.columns]
            # user_id列を比較用に文字列化
            if 'user_id' in df.columns:
                df['user_id_str'] = df['user_id'].astype(str).str.strip().str.lower()
            return df

        p_df = get_df("Profiles")
        h_df = get_df("History")
        m_df = get_df("Metrics")
        s_df = get_df("Settings")

        # Profiles検索
        p_match = p_df[p_df['user_id_str'] == u_id_search].to_dict('records')
        if p_match:
            p = p_match[0]
            default_data["profile"] = {"height": p.get('height', 170), "weight": p.get('weight', 65), "goal": p.get('goal', "未設定")}
            default_data["line"] = {"token": p.get('line_token', ""), "uid": p.get('line_user_id', ""), "en": (str(p.get('line_enabled', '')).lower() == 'true')}
            default_data["daily_message"] = p.get('daily_message', "準備はいいか！")
            default_data["roadmap"] = str(p.get('roadmap', "")) if pd.notna(p.get('roadmap')) else ""
            t_json = p.get('tasks_json', "[]")
            default_data["tasks"] = json.loads(t_json) if t_json and str(t_json) != "nan" else []

        # Settings復元 (追加項目：ハンドリングスピード等)
        if not s_df.empty:
            items = s_df[s_df['user_id_str'] == u_id_search]['metric_defs'].dropna().unique().tolist()
            if items:
                default_data["metrics_defs"] = sorted(list(set(items + ["体重"])))

        # 履歴・グラフデータ
        if not h_df.empty:
            sub_h = h_df[h_df['user_id_str'] == u_id_search]
            default_data["history"] = sub_h.set_index('date')['rate'].to_dict()
            default_data["notes"] = sub_h.set_index('date')['note'].to_dict()
        if not m_df.empty:
            default_data["metrics_data"] = m_df[m_df['user_id_str'] == u_id_search]

        return default_data
    except Exception as e:
        st.error(f"読み込みエラー詳細: {e}")
        return default_data

def save_to_gs(worksheet_name, new_df, key_cols=['user_id', 'date']):
    try:
        new_df.columns = [c.lower().strip() for c in new_df.columns]
        existing_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
        existing_df.columns = [c.lower().strip() for c in existing_df.columns]
        combined = pd.concat([existing_df, new_df], ignore_index=True).drop_duplicates(subset=[k.lower() for k in key_cols], keep='last')
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=combined)
        return True
    except:
        return False

# --- 3. ログイン & UI ---
st.sidebar.title("🔑 ログイン設定")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    st.session_state.db = load_full_data_gs(login_id)
    st.session_state.current_user = login_id

st.sidebar.divider()
selected_coach = st.sidebar.selectbox("🤖 コーチ", ["バスケットコーチ", "熱血コーチ", "論理派トレーナー"])
selected_model = st.sidebar.selectbox("🚀 AIモデル", available_models, index=0)
model = genai.GenerativeModel(selected_model, system_instruction=f"あなたは{selected_coach}です。目標:{st.session_state.db['profile']['goal']}")

# --- 4. サイドバー機能 (設定・項目管理・画像) ---
with st.sidebar.expander("👤 プロフィール・LINE設定"):
    db = st.session_state.db
    h_v = st.number_input("身長 (cm)", value=float(db["profile"]["height"]))
    w_v = st.number_input("体重 (kg)", value=float(db["profile"]["weight"]))
    g_v = st.text_area("目標", value=db["profile"]["goal"])
    l_at = st.text_input("LINEトークン", value=db["line"]["token"], type="password")
    l_ui = st.text_input("宛先UID", value=db["line"]["uid"])
    l_en = st.checkbox("LINE報告有効", value=db["line"]["en"])
    
    if st.button("全設定を保存"):
        t_json = json.dumps(db["tasks"], ensure_ascii=False)
        df_p = pd.DataFrame([{
            "user_id": login_id, "height": h_v, "weight": w_v, "goal": g_v,
            "line_token": l_at, "line_user_id": l_ui, "line_enabled": l_en,
            "daily_message": db["daily_message"], "tasks_json": t_json, "roadmap": db["roadmap"]
        }])
        if save_to_gs("Profiles", df_p, key_cols=['user_id']):
            st.session_state.db["profile"] = {"height": h_v, "weight": w_v, "goal": g_v}
            st.session_state.db["line"] = {"token": l_at, "uid": l_ui, "en": l_en}
            st.success("保存完了！")

with st.sidebar.expander("📊 項目管理"):
    new_m = st.text_input("項目追加")
    if st.button("追加") and new_m:
        if new_m not in db["metrics_defs"]:
            db["metrics_defs"].append(new_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(db["metrics_defs"]), "metric_defs": db["metrics_defs"]})
            save_to_gs("Settings", df_s, key_cols=['user_id', 'metric_defs'])
            st.rerun()
    if db["metrics_defs"]:
        del_m = st.selectbox("項目削除", db["metrics_defs"])
        if st.button("削除"):
            db["metrics_defs"].remove(del_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(db["metrics_defs"]), "metric_defs": db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df_s)
            st.rerun()

st.sidebar.divider()
uploaded_file = st.sidebar.file_uploader("写真分析 (食事等)", type=["jpg", "png", "jpeg"])

# --- 5. メイン画面 ---
st.title(f"🔥 AI Trainer Pro: {login_id}")
tabs = st.tabs(["📅 カレンダー", "📋 今日のメニュー", "📈 グラフ", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()

# --- Tab 1: カレンダー (描画修正) ---
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
    sel_date = st.date_input("詳細日付表示", value=today)
    if str(sel_date) in db["notes"]:
        st.info(f"📝 **メモ:** {db['notes'][str(sel_date)]}")

# --- Tab 2: 今日のメニュー (保存・復元強化) ---
with tabs[1]:
    st.info(f"**コーチ:** {db.get('daily_message')}")
    if st.button("メニュー生成"):
        res = model.generate_content("バスケ練習タスク4つを [MESSAGE]...[/MESSAGE] で。")
        db["daily_message"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", res.text, re.DOTALL).group(1).strip()
        tasks = [l.strip("- *") for l in res.text.split("\n") if l.strip().startswith(("-", "*"))]
        db["tasks"] = [{"task": t, "done": False} for t in tasks][:4]
        # 生成直後にProfilesへ自動保存して永続化
        save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "tasks_json": json.dumps(db["tasks"], ensure_ascii=False), "daily_message": db["daily_message"]}]), key_cols=['user_id'])
        st.rerun()

    col_l, col_r = st.columns([2, 1])
    with col_l:
        for i, t in enumerate(db["tasks"]):
            db["tasks"][i]["done"] = st.checkbox(t["task"], value=t["done"], key=f"tk_{i}_{t['task']}")
        done_n = sum(1 for t in db["tasks"] if t["done"])
        rate = done_n / len(db["tasks"]) if db["tasks"] else 0
        st.metric("達成率", f"{int(rate*100)}%")
        free_note = st.text_area("頑張りメモ")

    with col_r:
        st.subheader("数値記録")
        today_m = {m: st.number_input(m, value=0.0, key=f"iv_{m}") for m in db["metrics_defs"]}

    if st.button("🚀 保存 & 報告"):
        t_json = json.dumps(db["tasks"], ensure_ascii=False)
        save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "tasks_json": t_json, "daily_message": db["daily_message"], "roadmap": db["roadmap"]}]), key_cols=['user_id'])
        save_to_gs("History", pd.DataFrame([{"user_id": login_id, "date": str(today), "rate": rate, "note": free_note}]))
        save_to_gs("Metrics", pd.DataFrame([{"user_id": login_id, "date": str(today), "metric_name": k, "value": v} for k, v in today_m.items()]), key_cols=['user_id', 'date', 'metric_name'])
        
        if db["line"]["en"] and db["line"]["token"]:
            m_dt = "\n".join([f"・{k}: {v}" for k, v in today_m.items() if v > 0])
            msg = f"【{login_id} 報告】\n達成率: {int(rate*100)}%\n記録:\n{m_dt}\nメモ:\n{free_note}"
            requests.post("https://api.line.me/v2/bot/message/push", headers={"Authorization": f"Bearer {db['line']['token']}", "Content-Type": "application/json"}, json={"to": db["line"]["uid"], "messages": [{"type": "text", "text": msg}]})
        st.success("全て保存完了！")
        st.rerun()

# --- Tab 3: グラフ & Tab 4: ロードマップ (描画修正) ---
with tabs[2]: # グラフ
    m_data = db.get("metrics_data", pd.DataFrame())
    if not m_data.empty:
        sel = st.selectbox("項目", db["metrics_defs"])
        plot_df = m_data[m_data['metric_name'] == sel].copy()
        if not plot_df.empty:
            plot_df['date'] = pd.to_datetime(plot_df['date'])
            st.line_chart(plot_df.sort_values('date').set_index('date')['value'])

with tabs[3]: # ロードマップ
    if st.button("ロードマップ生成"):
        res = model.generate_content("目標達成戦略をMermaid mindmapで。```mermaid...```で囲んで。")
        match = re.search(r"```mermaid\s*(.*?)\s*```", res.text, re.DOTALL)
        if match:
            db["roadmap"] = match.group(1)
            save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "roadmap": db["roadmap"]}]), key_cols=['user_id'])
            st.rerun()
    if db.get("roadmap"):
        st.components.v1.html(f'<div class="mermaid" style="display:flex;justify-content:center;">{db["roadmap"]}</div><script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";mermaid.initialize({{startOnLoad:true, theme: "neutral"}});</script>', height=500)

with tabs[4]: # 相談
    chat_in = st.chat_input("相談を入力")
    if chat_in:
        inputs = [chat_in, Image.open(uploaded_file)] if uploaded_file else [chat_in]
        st.chat_message("assistant").write(model.generate_content(inputs).text)
