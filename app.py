import streamlit as st
import google.generativeai as genai
import re
from PIL import Image
import datetime
import calendar
import pandas as pd
import requests
from streamlit_gsheets import GSheetsConnection

# --- 1. 初期設定 ---
st.set_page_config(page_title="AI Trainer Pro: Ultimate", layout="wide")

try:
    # Secretsから取得
    API_KEY = st.secrets["GEMINI_API_KEY"]
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    genai.configure(api_key=API_KEY)
    # ご指定のGemini 3モデル
    model = genai.GenerativeModel("gemini-3-flash-preview")
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"設定エラー: Secretsを確認してください。 {e}")
    st.stop()

# --- 2. データ読み書き関数 ---
def load_full_data(user_id):
    data = {
        "profile": {"height": 170.0, "weight": 65.0, "goal": "未設定"},
        "history": {}, "metrics_data": pd.DataFrame(), "metrics_defs": ["体重"],
        "line": {"token": "", "uid": "", "en": False},
        "msg": "準備はいいか！", "tasks": [], "roadmap": ""
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
            data["profile"] = {"height": p.get('height', 170), "weight": p.get('weight', 65), "goal": p.get('goal', "未設定")}
            data["line"] = {"token": p.get('line_token', ""), "uid": p.get('line_user_id', ""), "en": p.get('line_enabled', False)}
            data["msg"] = p.get('daily_message', "準備はいいか！")

        if not h_df.empty:
            data["history"] = h_df[h_df['user_id'].astype(str) == u_id].set_index('date')['rate'].to_dict()
        if not m_df.empty:
            data["metrics_data"] = m_df[m_df['user_id'].astype(str) == u_id]
        if not s_df.empty:
            data["metrics_defs"] = sorted(list(set(s_df[s_df['user_id'].astype(str) == u_id]['metric_defs'].dropna().tolist())))
        if not data["metrics_defs"]: data["metrics_defs"] = ["体重"]
        return data
    except:
        return data

def save_data(ws_name, df, keys=['user_id', 'date']):
    try:
        ex_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=ws_name, ttl=0)
        combined = pd.concat([ex_df, df], ignore_index=True).drop_duplicates(subset=keys, keep='last')
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_name, data=combined)
        return True
    except: return False

# --- 3. ログイン管理 ---
st.sidebar.title("🔑 ログイン")
login_id = st.sidebar.text_input("ユーザーID", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    st.session_state.db = load_full_data(login_id)
    st.session_state.current_user = login_id

# --- 4. メイン画面レイアウト ---
st.title(f"🔥 AI Trainer Pro: {login_id}")
# プロフィールをタブの先頭に配置
tabs = st.tabs(["👤 プロフィール", "📅 カレンダー", "📋 今日のメニュー", "📈 グラフ", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()

# --- Tab 0: プロフィール (再表示) ---
with tabs[0]:
    st.header("ユーザー設定")
    p = st.session_state.db["profile"]
    col1, col2 = st.columns(2)
    new_h = col1.number_input("身長 (cm)", value=float(p["height"]))
    new_w = col1.number_input("体重 (kg)", value=float(p["weight"]))
    new_g = col2.text_area("現在の目標", value=p["goal"])
    
    if st.button("プロフィールの保存"):
        df = pd.DataFrame([{"user_id": login_id, "height": new_h, "weight": new_w, "goal": new_g,
                            "line_token": st.session_state.db["line"]["token"], 
                            "line_user_id": st.session_state.db["line"]["uid"],
                            "line_enabled": st.session_state.db["line"]["en"],
                            "daily_message": st.session_state.db["msg"]}])
        if save_data("Profiles", df, keys=['user_id']):
            st.session_state.db["profile"] = {"height": new_h, "weight": new_w, "goal": new_g}
            st.success("保存完了！")

# --- Tab 1: カレンダー ---
with tabs[1]:
    st.header(f"🗓️ {today.strftime('%Y年 %m月')}")
    cal = calendar.monthcalendar(today.year, today.month)
    cols = st.columns(7)
    for i, dname in enumerate(["月", "火", "水", "木", "金", "土", "日"]): cols[i].write(f"**{dname}**")
    for week in cal:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day != 0:
                d_str = f"{today.year}-{today.month:02d}-{day:02d}"
                rate = st.session_state.db["history"].get(d_str, -1)
                color = "#FF4B4B" if float(rate) >= 0.8 else "gray" if rate == -1 else "#007BFF"
                cols[i].markdown(f'<div style="border:1px solid #ddd;padding:10px;text-align:center;border-radius:5px;background-color:{color};color:white;">{day}</div>', unsafe_allow_html=True)

# --- Tab 2: 今日のメニュー (チェックボックス修正) ---
with tabs[2]:
    st.info(f"**コーチ:** {st.session_state.db['msg']}")
    if st.button("AIメニューを生成"):
        res = model.generate_content(f"目標:{st.session_state.db['profile']['goal']} に合わせて、具体的な運動タスクを4つと励ましを [MESSAGE]...[/MESSAGE] で出力して。")
        st.session_state.db["msg"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", res.text, re.DOTALL).group(1).strip()
        tasks = [l.strip("- *1234. ") for l in res.text.split("\n") if l.strip().startswith(("-", "*", "1.", "2."))]
        st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks[:4]]
        st.rerun()

    if st.session_state.db["tasks"]:
        st.subheader("✅ 本日のタスクリスト")
        # タスクの内容をチェックボックスの横に表示
        for i, t_item in enumerate(st.session_state.db["tasks"]):
            # keyをユニークにするためにIDも含める
            st.session_state.db["tasks"][i]["done"] = st.checkbox(label=t_item["task"], value=t_item["done"], key=f"tk_{i}_{login_id}")
        
        done_n = sum(1 for t in st.session_state.db["tasks"] if t["done"])
        total_n = len(st.session_state.db["tasks"])
        cur_rate = done_n / total_n
        
        st.metric("達成度", f"{int(cur_rate*100)}%")
        st.progress(cur_rate)
        
        f_report = st.text_area("今日頑張ったこと", placeholder="例：フォームが安定してきた！")
        
        if st.button("成果を保存 ＆ 報告"):
            save_data("History", pd.DataFrame([{"user_id": login_id, "date": str(today), "rate": cur_rate, "note": f_report}]))
            st.balloons()
            st.success("スプレッドシートに保存しました！")
    else:
        st.warning("まだメニューがありません。「生成」ボタンを押してください。")

# --- Tab 3: グラフ ---
with tabs[3]:
    st.header("📈 数値グラフ")
    m_df = st.session_state.db["metrics_data"]
    if not m_df.empty:
        sel_m = st.selectbox("項目選択", st.session_state.db["metrics_defs"])
        plot_df = m_df[m_df['metric_name'] == sel_m].sort_values('date')
        st.line_chart(plot_df.set_index('date')['value'])
    else: st.info("データがありません")

# --- Tab 4: ロードマップ ---
with tabs[4]:
    if st.button("ロードマップ生成"):
        res = model.generate_content("目標達成までのステップをMermaidのmindmap形式で。```mermaid...```で囲んで。")
        match = re.search(r"```mermaid\s*(.*?)\s*```", res.text, re.DOTALL)
        if match: st.session_state.db["roadmap"] = match.group(1)
        st.rerun()
    if st.session_state.db.get("roadmap"):
        st.components.v1.html(f'<div class="mermaid">{st.session_state.db["roadmap"]}</div><script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";mermaid.initialize({{startOnLoad:true}});</script>', height=500)

# --- Tab 5: 相談 ---
with tabs[5]:
    st.sidebar.subheader("📸 写真分析")
    up_file = st.sidebar.file_uploader("写真をアップロード", type=["jpg", "png"])
    p_chat = st.chat_input("相談を入力...")
    if p_chat:
        ins = [p_chat, Image.open(up_file)] if up_file else [p_chat]
        st.write(f"**AI:** {model.generate_content(ins).text}")
