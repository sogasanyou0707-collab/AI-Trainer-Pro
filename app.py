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
    # Gemini 3 を使用
    model = genai.GenerativeModel("gemini-3-flash-preview")
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"初期設定エラー: {e}")
    st.stop()

# --- 2. データ読み書き関数 ---
def load_full_data_gs(user_id):
    default_data = {
        "profile": {"height": 170.0, "weight": 65.0, "goal": "未設定"},
        "history": {},
        "metrics_data": pd.DataFrame(),
        "metrics_defs": ["体重"],
        "line_config": {"access_token": "", "user_id": "", "enabled": False},
        "daily_message": "準備はいいか！", "tasks": [], "roadmap": ""
    }
    try:
        p_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0)
        h_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="History", ttl=0)
        m_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Metrics", ttl=0)
        s_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Settings", ttl=0)

        # ユーザーデータの抽出
        uid_str = str(user_id)
        prof = p_df[p_df['user_id'].astype(str) == uid_str].to_dict('records')
        if prof:
            p = prof[0]
            default_data["profile"] = {"height": p.get('height', 170), "weight": p.get('weight', 65), "goal": p.get('goal', "未設定")}
            default_data["line_config"] = {"access_token": p.get('line_token', ""), "user_id": p.get('line_user_id', ""), "enabled": p.get('line_enabled', False)}
            default_data["daily_message"] = p.get('daily_message', "準備はいいか！")

        if not h_df.empty:
            # 日付をキー、達成率を値にした辞書
            h_sub = h_df[h_df['user_id'].astype(str) == uid_str]
            default_data["history"] = h_sub.set_index('date')['rate'].to_dict()
        
        if not m_df.empty:
            default_data["metrics_data"] = m_df[m_df['user_id'].astype(str) == uid_str]
        
        if not s_df.empty:
            raw_defs = s_df[s_df['user_id'].astype(str) == uid_str]['metric_defs'].dropna().tolist()
            default_data["metrics_defs"] = sorted(list(set(raw_defs)))

        if not default_data["metrics_defs"]: default_data["metrics_defs"] = ["体重"]
        return default_data
    except:
        return default_data

def save_to_gs(worksheet_name, new_df, key_cols=['user_id', 'date']):
    try:
        existing_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        if key_cols: combined = combined.drop_duplicates(subset=key_cols, keep='last')
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=combined)
        return True
    except Exception as e:
        st.error(f"保存失敗: {e}")
        return False

# --- 3. セッション管理 ---
st.sidebar.title("🔑 ログイン")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    st.session_state.db = load_full_data_gs(login_id)
    st.session_state.current_user = login_id

# --- 4. メインタイトル & タブ ---
st.title(f"🔥 AI Trainer Pro: {login_id}")
tabs = st.tabs(["📅 カレンダー", "📋 今日のメニュー", "📈 グラフ", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()
today_str = str(today)

# --- Tab 1: カレンダー (実装完了版) ---
with tabs[0]:
    st.header(f"🗓️ {today.strftime('%Y年 %m月')} の記録")
    
    # 曜日ラベル
    days_tags = ["月", "火", "水", "木", "金", "土", "日"]
    cols = st.columns(7)
    for i, day_tag in enumerate(days_tags):
        cols[i].markdown(f"<div style='text-align:center; font-weight:bold;'>{day_tag}</div>", unsafe_allow_html=True)
    
    # カレンダーグリッド描画
    cal = calendar.monthcalendar(today.year, today.month)
    for week in cal:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day == 0:
                cols[i].write("")
            else:
                d_str = f"{today.year}-{today.month:02d}-{day:02d}"
                rate = st.session_state.db["history"].get(d_str, -1)
                
                # 色分け
                bg_color = "transparent"
                text_color = "black"
                label = ""
                if rate != -1:
                    r = float(rate)
                    if r >= 0.8: bg_color, label = "#FF4B4B", "🔥"
                    elif r >= 0.5: bg_color, label = "#FFD700", f"{int(r*100)}%"
                    else: bg_color, label = "#007BFF", f"{int(r*100)}%"
                    text_color = "white"
                
                cols[i].markdown(
                    f"<div style='border:1px solid #ddd; border-radius:5px; padding:10px; text-align:center; background-color:{bg_color}; color:{text_color}; min-height:60px;'>"
                    f"<span style='font-size:0.8rem;'>{day}</span><br><b>{label}</b>"
                    f"</div>", unsafe_allow_html=True
                )

# --- Tab 2: 今日のメニュー (達成度計算の修正) ---
with tabs[1]:
    st.info(f"**コーチからの伝言:** {st.session_state.db.get('daily_message', '準備はいいか！')}")
    
    if st.button("AIメニューを生成・更新"):
        res = model.generate_content("目標に基づき、タスク4つと励ましを [MESSAGE]...[/MESSAGE] で出力。")
        st.session_state.db["daily_message"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", res.text, re.DOTALL).group(1).strip()
        tasks_found = [l.strip("- *1234. ") for l in res.text.split("\n") if l.strip().startswith(("-", "*", "1.", "2."))]
        st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks_found[:4]]
        st.rerun()

    col_l, col_r = st.columns([2, 1])
    with col_l:
        st.subheader("✅ タスクチェック")
        # チェックボックスの状態をセッション内で即座に反映させる
        for i, t in enumerate(st.session_state.db["tasks"]):
            st.session_state.db["tasks"][i]["done"] = st.checkbox(t["task"], value=t["done"], key=f"tk_{i}_{login_id}")
        
        # 達成度のリアルタイム計算
        done_num = sum(1 for t in st.session_state.db["tasks"] if t["done"])
        total_num = len(st.session_state.db["tasks"])
        current_rate = done_num / total_num if total_num > 0 else 0
        
        st.divider()
        st.metric("本日の達成度", f"{int(current_rate * 100)}%")
        st.progress(current_rate)
        
        free_report = st.text_area("今日頑張ったこと（自由報告欄）", placeholder="例：今日はシュート練習を頑張りました！")

    with col_r:
        st.subheader("📈 数値記録")
        today_metrics = {}
        for m in st.session_state.db["metrics_defs"]:
            today_metrics[m] = st.number_input(f"{m}", value=0.0, key=f"input_{m}_{login_id}")

    if st.button("🚀 今日の成果を保存 & LINE報告"):
        # 保存
        h_df = pd.DataFrame([{"user_id": login_id, "date": today_str, "rate": current_rate, "note": free_report}])
        save_to_gs("History", h_df)
        
        m_rows = [{"user_id": login_id, "date": today_str, "metric_name": k, "value": v} for k, v in today_metrics.items()]
        save_to_gs("Metrics", pd.DataFrame(m_rows), key_cols=['user_id', 'date', 'metric_name'])
        
        # LINE報告
        config = st.session_state.db["line_config"]
        if config["enabled"] and config["access_token"]:
            prompt = f"達成率{int(current_rate*100)}%、今日の感想：『{free_report}』。保護者向けの温かいフィードバックを作成して。"
            feedback = model.generate_content(prompt).text
            msg = f"\n【{login_id} 報告】\n達成率: {int(current_rate*100)}%\n頑張り: {free_report}\n\nコーチより:\n{feedback}"
            requests.post("https://api.line.me/v2/bot/message/push", 
                          headers={"Authorization": f"Bearer {config['access_token']}", "Content-Type": "application/json"},
                          json={"to": config["user_id"], "messages": [{"type": "text", "text": msg}]})
            st.toast("LINE送信完了！")
        
        st.session_state.db["history"][today_str] = current_rate # カレンダーへ即時反映
        st.success("スプレッドシートに保存しました！")
        st.balloons()

# --- Tab 3: グラフ (表示ロジック修正) ---
with tabs[2]:
    st.header("📈 成長の軌跡")
    m_df = st.session_state.db.get("metrics_data", pd.DataFrame())
    if not m_df.empty:
        metric_list = st.session_state.db["metrics_defs"]
        selected_m = st.selectbox("表示する項目を選択", metric_list)
        
        plot_df = m_df[m_df['metric_name'] == selected_m].sort_values('date')
        if not plot_df.empty:
            st.line_chart(plot_df.set_index('date')['value'])
        else:
            st.info("選択した項目のデータがまだありません。")
    else:
        st.info("データがありません。まずは数値を記録して保存してください。")

# --- Tab 4: ロードマップ (Mermaid完全版) ---
with tabs[3]:
    st.header("🚀 成功へのロードマップ")
    if st.button("ロードマップをAIで生成"):
        with st.spinner("AIが戦略を練っています..."):
            res = model.generate_content("目標達成に向けたステップを、Mermaid形式のmindmapで出力してください。```mermaid...```で囲んで。")
            match = re.search(r"```mermaid\s*(.*?)\s*```", res.text, re.DOTALL)
            if match:
                st.session_state.db["roadmap"] = match.group(1)
                st.rerun()

    if st.session_state.db.get("roadmap"):
        mermaid_code = st.session_state.db["roadmap"]
        st.components.v1.html(f"""
            <div class="mermaid" style="display: flex; justify-content: center;">
                {mermaid_code}
            </div>
            <script type="module">
                import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                mermaid.initialize({{ startOnLoad: true, theme: 'neutral' }});
            </script>
        """, height=600)

# --- Tab 5: 相談 (画像分析) ---
with tabs[4]:
    # サイドバーに設置したアップローダーをここでも参照
    # （コード冒頭のサイドバー部分で uploaded_file を定義している想定）
    st.subheader("💬 コーチに相談")
    chat_input = st.chat_input("フォームや食事の写真をサイドバーから上げて相談してね！")
    # (チャット履歴管理部分は以前と同様)
