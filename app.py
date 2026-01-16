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

# --- 1. 初期設定 ---
st.set_page_config(page_title="AI Trainer Pro: Ultimate v1.2", layout="wide")

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    genai.configure(api_key=API_KEY)
    # 安定性を考慮し 1.5-flash を使用
    model = genai.GenerativeModel("gemini-1.5-flash")
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"初期設定エラー: {e}")
    st.stop()

# --- 2. データ読み書き関数 (復元ロジック最強化) ---
def load_full_data_gs(user_id):
    u_id = str(user_id).strip()
    default_data = {
        "profile": {"height": 170.0, "weight": 65.0, "goal": "バスケ上達"},
        "history": {}, "notes": {}, "metrics_data": pd.DataFrame(), "metrics_defs": ["体重"],
        "line": {"token": "", "uid": "", "en": False},
        "daily_message": "今日も最高の練習を！", "tasks": [], "roadmap": ""
    }
    try:
        # ttl=0 でキャッシュを無効化し最新を取得
        p_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0)
        h_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="History", ttl=0)
        m_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Metrics", ttl=0)
        s_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Settings", ttl=0)

        # 列名を正規化
        for df in [p_df, h_df, m_df, s_df]:
            df.columns = [c.lower().strip() for c in df.columns]

        # Profilesの復元 (ロードマップ・タスク・LINE)
        prof = p_df[p_df['user_id'].astype(str) == u_id].to_dict('records')
        if prof:
            p = prof[0]
            default_data["profile"] = {"height": p.get('height', 170), "weight": p.get('weight', 65), "goal": p.get('goal', "未設定")}
            default_data["line"] = {"token": p.get('line_token', ""), "uid": p.get('line_user_id', ""), "en": p.get('line_enabled', False)}
            default_data["daily_message"] = p.get('daily_message', "準備はいいか！")
            default_data["roadmap"] = str(p.get('roadmap', ""))
            t_json = p.get('tasks_json', "[]")
            default_data["tasks"] = json.loads(t_json) if t_json and t_json != "nan" else []

        # 歴史・メモ
        if not h_df.empty:
            sub_h = h_df[h_df['user_id'].astype(str) == u_id]
            default_data["history"] = sub_h.set_index('date')['rate'].to_dict()
            default_data["notes"] = sub_h.set_index('date')['note'].to_dict()

        # グラフデータ
        if not m_df.empty:
            default_data["metrics_data"] = m_df[m_df['user_id'].astype(str) == u_id]

        # 【復元】追加項目の復元 (Settingsシート)
        if not s_df.empty:
            user_items = s_df[s_df['user_id'].astype(str) == u_id]['metric_defs'].dropna().unique().tolist()
            if user_items:
                default_data["metrics_defs"] = sorted(user_items)

        return default_data
    except:
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

# --- 3. セッション & ログイン ---
st.sidebar.title("🔑 ログイン")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    st.session_state.db = load_full_data_gs(login_id)
    st.session_state.current_user = login_id

# コーチ選択の保持
selected_coach = st.sidebar.selectbox("🤖 コーチ選択", ["バスケットコーチ", "熱血コーチ", "論理派トレーナー"])

# --- 4. サイドバー機能 (復旧：項目削除・画像) ---
with st.sidebar.expander("👤 各種設定"):
    p_d = st.session_state.db["profile"]
    h_v = st.number_input("身長 (cm)", value=float(p_d["height"]))
    w_v = st.number_input("体重 (kg)", value=float(p_d["weight"]))
    g_v = st.text_area("目標", value=p_d["goal"])
    l_at = st.text_input("LINEトークン", value=st.session_state.db["line"]["token"], type="password")
    l_ui = st.text_input("宛先UID", value=st.session_state.db["line"]["uid"])
    l_en = st.checkbox("LINE報告有効", value=st.session_state.db["line"]["en"])
    
    if st.button("設定を保存"):
        t_json = json.dumps(st.session_state.db["tasks"], ensure_ascii=False)
        df_p = pd.DataFrame([{
            "user_id": login_id, "height": h_v, "weight": w_v, "goal": g_v,
            "line_token": l_at, "line_user_id": l_ui, "line_enabled": l_en,
            "daily_message": st.session_state.db["daily_message"], 
            "tasks_json": t_json, "roadmap": st.session_state.db["roadmap"]
        }])
        save_to_gs("Profiles", df_p, key_cols=['user_id'])
        st.success("保存完了！")

with st.sidebar.expander("📊 項目管理（追加・削除）"):
    new_m = st.text_input("新規項目名")
    if st.button("追加") and new_m:
        if new_m not in st.session_state.db["metrics_defs"]:
            st.session_state.db["metrics_defs"].append(new_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            save_to_gs("Settings", df_s, key_cols=['user_id', 'metric_defs'])
            st.rerun()
    
    # 【復旧】項目削除機能
    if len(st.session_state.db["metrics_defs"]) > 0:
        st.divider()
        del_m = st.selectbox("削除する項目を選択", st.session_state.db["metrics_defs"])
        if st.button("選択した項目を削除"):
            st.session_state.db["metrics_defs"].remove(del_m)
            # Settingsシートは全入れ替えのため直接update
            df_s = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df_s)
            st.rerun()

st.sidebar.divider()
st.sidebar.subheader("📸 写真分析")
uploaded_file = st.sidebar.file_uploader("写真をアップロード (食事・フォーム等)", type=["jpg", "jpeg", "png"])

# --- 5. メイン画面 ---
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
                cols[i].markdown(f'<div style="background:{color};color:white;padding:10px;text-align:center;border-radius:5px;min-height:50px;">{day}</div>', unsafe_allow_html=True)
    st.divider()
    sel_date = st.date_input("振り返り日付選択", value=today)
    if str(sel_date) in st.session_state.db["notes"]:
        st.info(f"📝 **メモ:** {st.session_state.db['notes'][str(sel_date)]}")

# --- Tab 2: メニュー ---
with tabs[1]:
    st.info(f"**【コーチより】** {st.session_state.db.get('daily_message')}")
    if st.button("AIメニュー生成"):
        res = model.generate_content("バスケ練習タスク4つと励ましを [MESSAGE]...[/MESSAGE] で。")
        st.session_state.db["daily_message"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", res.text, re.DOTALL).group(1).strip()
        tasks = [l.strip("- *123. ") for l in res.text.split("\n") if l.strip().startswith(("-", "*", "1."))]
        st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks][:4]
        st.rerun()
    
    for i, t in enumerate(st.session_state.db["tasks"]):
        st.session_state.db["tasks"][i]["done"] = st.checkbox(t["task"], value=t["done"], key=f"tk_{i}_{t['task']}")
    
    done_n = sum(1 for t in st.session_state.db["tasks"] if t["done"])
    rate = done_n / len(st.session_state.db["tasks"]) if st.session_state.db["tasks"] else 0
    st.metric("達成率", f"{int(rate*100)}%")
    
    col_r1, col_r2 = st.columns([2, 1])
    with col_r1: free_note = st.text_area("頑張りメモ", value=st.session_state.db["notes"].get(str(today), ""))
    with col_r2: 
        st.write("📊 数値記録")
        today_metrics = {m: st.number_input(m, value=0.0, key=f"m_{m}") for m in st.session_state.db["metrics_defs"]}

    if st.button("保存 & 報告"):
        t_json = json.dumps(st.session_state.db["tasks"], ensure_ascii=False)
        # Profilesへの保存時に最新のroadmapとタスクを同期
        save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "tasks_json": t_json, "daily_message": st.session_state.db["daily_message"], "roadmap": st.session_state.db["roadmap"]}]), key_cols=['user_id'])
        save_to_gs("History", pd.DataFrame([{"user_id": login_id, "date": str(today), "rate": rate, "note": free_note}]))
        save_to_gs("Metrics", pd.DataFrame([{"user_id": login_id, "date": str(today), "metric_name": k, "value": v} for k, v in today_metrics.items()]), key_cols=['user_id', 'date', 'metric_name'])
        
        if l_en and l_at:
            requests.post("https://api.line.me/v2/bot/message/push", headers={"Authorization": f"Bearer {l_at}", "Content-Type": "application/json"}, json={"to": l_ui, "messages": [{"type": "text", "text": f"達成率{int(rate*100)}%\n頑張り:{free_note}"}]})
        st.success("保存完了！")
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
    else: st.info("データがありません。")

# --- Tab 4: ロードマップ (復旧) ---
with tabs[3]:
    if st.button("AIロードマップ生成"):
        res = model.generate_content("目標達成までの長期戦略をMermaidのmindmap形式で。```mermaid...```で囲んで出力。")
        match = re.search(r"```mermaid\s*(.*?)\s*```", res.text, re.DOTALL)
        if match:
            st.session_state.db["roadmap"] = match.group(1)
            # 即時Profilesへ保存
            save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "roadmap": st.session_state.db["roadmap"]}]), key_cols=['user_id'])
            st.rerun()
    
    if st.session_state.db.get("roadmap"):
        st.components.v1.html(f"""
            <div class="mermaid" style="display:flex;justify-content:center;">
                {st.session_state.db["roadmap"]}
            </div>
            <script type="module">
                import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                mermaid.initialize({{ startOnLoad: true, theme: 'neutral' }});
            </script>
        """, height=500)

# --- Tab 5: 相談 (【復旧】画像分析対応) ---
with tabs[4]:
    st.header("💬 AIコーチ相談 & 画像分析")
    chat_in = st.chat_input("相談を入力してください (写真はサイドバーからアップ)")
    if chat_in:
        # 画像がアップロードされていれば一緒に送信
        inputs = [chat_in]
        if uploaded_file:
            inputs.append(Image.open(uploaded_file))
            st.info("写真を分析しています...")
        
        with st.chat_message("assistant"):
            st.write(model.generate_content(inputs).text)
