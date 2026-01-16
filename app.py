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

        prof = p_df[p_df['user_id'].astype(str) == str(user_id)].to_dict('records')
        if prof:
            p = prof[0]
            default_data["profile"] = {"height": p.get('height', 170), "weight": p.get('weight', 65), "goal": p.get('goal', "未設定")}
            default_data["line_config"] = {"access_token": p.get('line_token', ""), "user_id": p.get('line_user_id', ""), "enabled": p.get('line_enabled', False)}
            default_data["daily_message"] = p.get('daily_message', "準備はいいか！")

        if not h_df.empty:
            # 最新の履歴から達成率を取得
            default_data["history"] = h_df[h_df['user_id'].astype(str) == str(user_id)].set_index('date')['rate'].to_dict()
        if not m_df.empty:
            default_data["metrics_data"] = m_df[m_df['user_id'].astype(str) == str(user_id)]
        if not s_df.empty:
            default_data["metrics_defs"] = s_df[s_df['user_id'].astype(str) == str(user_id)]['metric_defs'].unique().tolist()
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

# --- 3. ログイン & セッション管理 ---
st.sidebar.title("🔑 ログイン")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    st.session_state.db = load_full_data_gs(login_id)
    st.session_state.current_user = login_id

# --- 4. サイドバー設定 ---
with st.sidebar.expander("🎯 プロフィール設定"):
    h_val = st.number_input("身長", value=float(st.session_state.db["profile"]["height"]))
    w_val = st.number_input("体重", value=float(st.session_state.db["profile"]["weight"]))
    g_val = st.text_area("目標", value=st.session_state.db["profile"]["goal"])
    if st.button("設定を保存"):
        df = pd.DataFrame([{"user_id": login_id, "height": h_val, "weight": w_val, "goal": g_val, 
                            "line_token": st.session_state.db["line_config"]["access_token"],
                            "line_user_id": st.session_state.db["line_config"]["user_id"],
                            "line_enabled": st.session_state.db["line_config"]["enabled"],
                            "daily_message": st.session_state.db["daily_message"]}])
        save_to_gs("Profiles", df, key_cols=['user_id'])
        st.session_state.db["profile"] = {"height": h_val, "weight": w_val, "goal": g_val}
        st.rerun()

with st.sidebar.expander("📊 記録項目の管理"):
    new_m = st.text_input("新規項目名")
    if st.button("追加") and new_m:
        st.session_state.db["metrics_defs"].append(new_m)
        df = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
        save_to_gs("Settings", df, key_cols=['user_id', 'metric_defs'])
        st.rerun()

with st.sidebar.expander("💬 LINE連携"):
    l_en = st.checkbox("有効化", value=st.session_state.db["line_config"]["enabled"])
    l_at = st.text_input("トークン", value=st.session_state.db["line_config"]["access_token"], type="password")
    l_ui = st.text_input("宛先ユーザーID", value=st.session_state.db["line_config"]["user_id"])
    if st.button("LINE設定保存"):
        st.session_state.db["line_config"] = {"access_token": l_at, "user_id": l_ui, "enabled": l_en}
        st.info("プロフィールの保存ボタンを押すと確定されます")

# --- 5. メイン画面 ---
st.title(f"🔥 AI Trainer Pro: {login_id}")
tabs = st.tabs(["📅 カレンダー", "📋 今日のメニュー", "📈 グラフ", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()

# --- Tab 1: カレンダー ---
with tabs[0]:
    st.header(f"🗓️ {today.strftime('%Y-%m')} 記録")
    # (カレンダー描画部分は簡略化して維持)

# --- Tab 2: 今日のメニュー (自由報告欄を追加) ---
with tabs[1]:
    st.info(f"**コーチからの伝言:** {st.session_state.db['daily_message']}")
    
    if st.button("メニュー更新・生成"):
        res = model.generate_content("タスク4つと励ましを [MESSAGE]...[/MESSAGE] で出力。")
        st.session_state.db["daily_message"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", full_text := res.text, re.DOTALL).group(1).strip()
        tasks = [l.strip("- *") for l in res.text.split("\n") if l.strip().startswith(("-", "*"))]
        st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks[:4]]
        st.rerun()

    col_l, col_r = st.columns([2, 1])
    with col_l:
        st.subheader("✅ タスクチェック")
        for i, t in enumerate(st.session_state.db["tasks"]):
            st.session_state.db["tasks"][i]["done"] = st.checkbox(t["task"], value=t["done"], key=f"tk_{i}")
        
        # 達成度の計算
        done_num = sum(1 for t in st.session_state.db["tasks"] if t["done"])
        total = len(st.session_state.db["tasks"])
        rate = done_num / total if total > 0 else 0
        
        st.divider()
        st.metric("本日の達成度", f"{int(rate*100)}%")
        st.progress(rate)
        
        # 【追加】自由報告欄（今日頑張ったこと）
        free_report = st.text_area("今日頑張ったこと（自由報告欄）", placeholder="例：今日はシュート練習を多めにやりました！")

    with col_r:
        st.subheader("📈 数値記録")
        today_metrics = {}
        for m in st.session_state.db["metrics_defs"]:
            today_metrics[m] = st.number_input(f"{m}", value=0.0, key=f"input_{m}")

    if st.button("🚀 成果を保存 ＆ LINE報告送信"):
        # 1. 履歴保存 (noteカラムとして自由報告も保存するのがおすすめ)
        h_df = pd.DataFrame([{"user_id": login_id, "date": str(today), "rate": rate, "note": free_report}])
        save_to_gs("History", h_df)
        
        # 2. 数値保存
        m_rows = [{"user_id": login_id, "date": str(today), "metric_name": k, "value": v} for k, v in today_metrics.items()]
        save_to_gs("Metrics", pd.DataFrame(m_rows), key_cols=['user_id', 'date', 'metric_name'])
        
        # 3. LINE送信
        config = st.session_state.db["line_config"]
        if config["enabled"] and config["access_token"]:
            with st.spinner("LINE送信中..."):
                prompt = f"達成率{int(rate*100)}%、今日の感想：『{free_report}』に基づく、保護者向けの温かいフィードバックを作成して。"
                feedback = model.generate_content(prompt).text
                msg = f"\n【{login_id} 本日の報告】\n達成率: {int(rate*100)}%\n頑張ったこと: {free_report}\n\nコーチより:\n{feedback}"
                
                requests.post("https://api.line.me/v2/bot/message/push", 
                              headers={"Authorization": f"Bearer {config['access_token']}", "Content-Type": "application/json"},
                              json={"to": config["user_id"], "messages": [{"type": "text", "text": msg}]})
                st.toast("LINE送信完了！")
        
        st.success("スプレッドシートに保存しました！")
        st.balloons()

# --- Tab 3以降 (グラフ、ロードマップ、相談) は前回同様 ---
