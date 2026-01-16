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
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"初期設定エラー: {e}")
    st.stop()

# --- 2. モデル診断機能 (404エラー対策) ---
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
        "profile": {"height": 170.0, "weight": 65.0, "goal": "未設定"},
        "history": {}, "metrics_data": pd.DataFrame(), "metrics_defs": ["体重"],
        "line": {"token": "", "uid": "", "en": False},
        "daily_message": "準備はいいか！", "tasks": [], "roadmap": ""
    }
    try:
        p_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0)
        h_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="History", ttl=0)
        m_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Metrics", ttl=0)
        s_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Settings", ttl=0)

        u_id = str(user_id)
        # プロフィール
        prof = p_df[p_df['user_id'].astype(str) == u_id].to_dict('records')
        if prof:
            p = prof[0]
            default_data["profile"] = {"height": p.get('height', 170), "weight": p.get('weight', 65), "goal": p.get('goal', "未設定")}
            default_data["line"] = {"token": p.get('line_token', ""), "uid": p.get('line_user_id', ""), "en": p.get('line_enabled', False)}
            default_data["daily_message"] = p.get('daily_message', "準備はいいか！")

        # 履歴・グラフデータ
        if not h_df.empty:
            default_data["history"] = h_df[h_df['user_id'].astype(str) == u_id].set_index('date')['rate'].to_dict()
        if not m_df.empty:
            # グラフ用にuser_idでフィルタリング
            default_data["metrics_data"] = m_df[m_df['user_id'].astype(str) == u_id]
        if not s_df.empty:
            raw_defs = s_df[s_df['user_id'].astype(str) == u_id]['metric_defs'].dropna().tolist()
            default_data["metrics_defs"] = sorted(list(set(raw_defs)))
        
        if not default_data["metrics_defs"]: default_data["metrics_defs"] = ["体重"]
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

# --- 4. ログイン & コーチ選択 ---
st.sidebar.title("🔑 ログイン設定")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    st.session_state.db = load_full_data_gs(login_id)
    st.session_state.current_user = login_id

# 【復活】コーチ選択
st.sidebar.divider()
selected_coach = st.sidebar.selectbox("🤖 コーチを選択", ["熱血コーチ", "論理派トレーナー", "バスケットボール専門コーチ"])
selected_model_name = st.sidebar.selectbox("使用AIモデル(診断用)", available_models, index=0)

# モデルの初期化 (コーチの設定を注入)
model = genai.GenerativeModel(
    selected_model_name,
    system_instruction=f"あなたは{selected_coach}です。ユーザーID:{login_id}、目標:{st.session_state.db['profile']['goal']}に合わせて指導してください。"
)

# --- 5. サイドバー機能 (プロフィール・項目・LINE・画像) ---
with st.sidebar.expander("👤 プロフィール設定"):
    p_d = st.session_state.db["profile"]
    h_v = st.number_input("身長 (cm)", value=float(p_d["height"]))
    w_v = st.number_input("体重 (kg)", value=float(p_d["weight"]))
    g_v = st.text_area("目標", value=p_d["goal"])
    if st.button("プロフィールの保存"):
        df_p = pd.DataFrame([{"user_id": login_id, "height": h_v, "weight": w_v, "goal": g_v, 
                              "line_token": st.session_state.db["line"]["token"],
                              "line_user_id": st.session_state.db["line"]["uid"],
                              "line_enabled": st.session_state.db["line"]["en"],
                              "daily_message": st.session_state.db["daily_message"]}])
        save_to_gs("Profiles", df_p, key_cols=['user_id'])
        st.session_state.db["profile"] = {"height": h_v, "weight": w_v, "goal": g_v}
        st.success("保存完了")

with st.sidebar.expander("📊 項目追加・削除"):
    new_m = st.text_input("項目名").strip()
    if st.button("追加") and new_m:
        if new_m not in st.session_state.db["metrics_defs"]:
            st.session_state.db["metrics_defs"].append(new_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df_s)
            st.rerun()
    if st.session_state.db["metrics_defs"]:
        st.divider()
        del_m = st.selectbox("削除項目", st.session_state.db["metrics_defs"])
        if st.button("削除実行"):
            st.session_state.db["metrics_defs"].remove(del_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df_s)
            st.rerun()

with st.sidebar.expander("💬 LINE報告設定"):
    l_en = st.checkbox("有効化", value=st.session_state.db["line"]["en"])
    l_at = st.text_input("トークン", value=st.session_state.db["line"]["token"], type="password")
    l_ui = st.text_input("ユーザーID", value=st.session_state.db["line"]["uid"])
    if st.button("LINE保存"):
        st.session_state.db["line"] = {"token": l_at, "uid": l_ui, "en": l_en}
        st.info("プロフィール保存で確定")

st.sidebar.divider()
uploaded_file = st.sidebar.file_uploader("写真分析 (食事・フォーム)", type=["jpg", "png", "jpeg"])

# --- 6. メイン画面 (タブ構成) ---
st.title(f"🏃‍♂️ AI Trainer Pro: {login_id}")
tabs = st.tabs(["📅 カレンダー", "📋 今日のメニュー", "📈 グラフ", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()

# --- Tab 1: カレンダー ---
with tabs[0]:
    st.header(f"🗓️ {today.strftime('%Y-%m')} 記録")
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
                cols[i].markdown(f'<div style="background:{color};color:white;padding:10px;text-align:center;border-radius:5px;">{day}</div>', unsafe_allow_html=True)

# --- Tab 2: 今日のメニュー ---
with tabs[1]:
    st.info(f"**【{selected_coach}より】** {st.session_state.db.get('daily_message', '生成してください')}")
    if st.button("メニュー生成"):
        try:
            res = model.generate_content(f"目標に基づき、タスク4つと励ましを [MESSAGE]...[/MESSAGE] で出力。タスクは必ず '-' で始めてください。")
            full_text = res.text
            st.session_state.db["daily_message"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", full_text, re.DOTALL).group(1).strip()
            # タスク抽出の強化
            tasks = [l.strip("- *1234. ") for l in full_text.split("\n") if l.strip().startswith(("-", "*", "1.", "2."))]
            st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks if t][:4]
            st.rerun()
        except Exception as e: st.error(f"生成エラー: {e}")

    col_l, col_r = st.columns([2, 1])
    with col_l:
        st.subheader("✅ 本日のタスク")
        if not st.session_state.db["tasks"]: st.warning("メニューを生成してください")
        for i, t in enumerate(st.session_state.db["tasks"]):
            # keyにタスク名も含めることで表示崩れを防止
            st.session_state.db["tasks"][i]["done"] = st.checkbox(t["task"], value=t["done"], key=f"tk_{i}_{login_id}_{t['task']}")
        
        done_n = sum(1 for t in st.session_state.db["tasks"] if t["done"])
        total_n = len(st.session_state.db["tasks"])
        rate = done_n / total_n if total_n > 0 else 0
        st.metric("達成率", f"{int(rate*100)}%")
        st.progress(rate)
        free_note = st.text_area("今日頑張ったこと", placeholder="自由に入力")

    with col_r:
        st.subheader("📈 数値記録")
        today_m = {m: st.number_input(f"{m}", value=0.0, key=f"iv_{m}_{login_id}") for m in st.session_state.db["metrics_defs"]}

    if st.button("🚀 保存 & LINE報告"):
        save_to_gs("History", pd.DataFrame([{"user_id": login_id, "date": str(today), "rate": rate, "note": free_note}]))
        save_to_gs("Metrics", pd.DataFrame([{"user_id": login_id, "date": str(today), "metric_name": k, "value": v} for k, v in today_m.items()]), key_cols=['user_id', 'date', 'metric_name'])
        
        config = st.session_state.db["line"]
        if config["en"] and config["token"]:
            feedback = model.generate_content(f"達成率{int(rate*100)}%、感想：『{free_note}』へのフィードバックを。").text
            msg = f"\n【{login_id} 報告】\n達成率: {int(rate*100)}%\n頑張り: {free_report}\n\nコーチより:\n{feedback}"
            requests.post("https://api.line.me/v2/bot/message/push", headers={"Authorization": f"Bearer {config['token']}", "Content-Type": "application/json"}, json={"to": config["uid"], "messages": [{"type": "text", "text": msg}]})
            st.toast("LINE送信完了")
        st.balloons()
        st.rerun()

# --- Tab 3: グラフ (表示ロジック強化) ---
with tabs[2]:
    st.header("📈 成長グラフ")
    m_df = st.session_state.db.get("metrics_data", pd.DataFrame())
    if not m_df.empty:
        sel_metric = st.selectbox("表示項目を選択", st.session_state.db["metrics_defs"])
        # データの抽出と型変換
        plot_df = m_df[m_df['metric_name'] == sel_metric].copy()
        if not plot_df.empty:
            plot_df['date'] = pd.to_datetime(plot_df['date'])
            plot_df = plot_df.sort_values('date')
            st.line_chart(plot_df.set_index('date')['value'])
        else:
            st.info(f"'{sel_metric}' のデータがまだありません。")
    else:
        st.info("データがありません。保存ボタンで最初の記録をしてください。")

# --- Tab 4: ロードマップ (Mermaid) ---
with tabs[3]:
    if st.button("最新ロードマップ生成"):
        res = model.generate_content("目標達成までの戦略をMermaidのmindmap形式で。```mermaid...```で囲んで。")
        match = re.search(r"```mermaid\s*(.*?)\s*```", res.text, re.DOTALL)
        if match: st.session_state.db["roadmap"] = match.group(1)
    if st.session_state.db.get("roadmap"):
        st.components.v1.html(f'<div class="mermaid" style="display:flex;justify-content:center;">{st.session_state.db["roadmap"]}</div><script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";mermaid.initialize({{startOnLoad:true}});</script>', height=500)

# --- Tab 5: 相談 ---
with tabs[4]:
    st.header("💬 AI相談 & 画像分析")
    chat_in = st.chat_input("相談内容を入力してください")
    if chat_in:
        ins = [chat_in, Image.open(uploaded_file)] if uploaded_file else [chat_in]
        with st.chat_message("assistant"):
            st.write(model.generate_content(ins).text)
