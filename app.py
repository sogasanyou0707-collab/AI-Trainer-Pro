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
    # ご指定のモデル（Gemini 3）
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
        "daily_message": "準備はいいか！", "tasks": [], "roadmap": "", "messages": []
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
            default_data["history"] = h_df[h_df['user_id'].astype(str) == str(user_id)].set_index('date')['rate'].to_dict()
        if not m_df.empty:
            default_data["metrics_data"] = m_df[m_df['user_id'].astype(str) == str(user_id)]
        
        if not s_df.empty:
            # 重複を排除して読み込み
            raw_defs = s_df[s_df['user_id'].astype(str) == str(user_id)]['metric_defs'].dropna().tolist()
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

# --- 3. ログイン & セッション管理 ---
st.sidebar.title("🔑 ログイン")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    st.session_state.db = load_full_data_gs(login_id)
    st.session_state.current_user = login_id

# --- 4. サイドバー設定（プロフィール・項目管理・画像） ---
with st.sidebar.expander("🎯 プロフィール設定"):
    h_val = st.number_input("身長", value=float(st.session_state.db["profile"]["height"]))
    w_val = st.number_input("体重", value=float(st.session_state.db["profile"]["weight"]))
    g_val = st.text_area("目標", value=st.session_state.db["profile"]["goal"])
    if st.button("プロフィールの保存"):
        df = pd.DataFrame([{"user_id": login_id, "height": h_val, "weight": w_val, "goal": g_val, 
                            "line_token": st.session_state.db["line_config"]["access_token"],
                            "line_user_id": st.session_state.db["line_config"]["user_id"],
                            "line_enabled": st.session_state.db["line_config"]["enabled"],
                            "daily_message": st.session_state.db["daily_message"]}])
        save_to_gs("Profiles", df, key_cols=['user_id'])
        st.session_state.db["profile"] = {"height": h_val, "weight": w_val, "goal": g_val}
        st.success("保存完了！")

with st.sidebar.expander("📊 記録項目の管理", expanded=True):
    # 追加機能
    new_m = st.text_input("新規項目名").strip()
    if st.button("追加") and new_m:
        if new_m not in st.session_state.db["metrics_defs"]:
            st.session_state.db["metrics_defs"].append(new_m)
            df = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df)
            st.rerun()
    
    # 【追加】削除機能
    if len(st.session_state.db["metrics_defs"]) > 0:
        st.divider()
        del_m = st.selectbox("削除する項目を選択", st.session_state.db["metrics_defs"])
        if st.button("選択した項目を削除"):
            st.session_state.db["metrics_defs"].remove(del_m)
            # 削除後のリストでスプレッドシートを更新
            df = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            # Settingsは全入れ替えのため update を使用
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df)
            st.warning(f"'{del_m}' を削除しました")
            st.rerun()

# 【復活】画像分析用アップローダー
st.sidebar.divider()
st.sidebar.subheader("📸 写真分析 (食事・フォーム)")
uploaded_file = st.sidebar.file_uploader("写真をアップロード", type=["jpg", "jpeg", "png"])

with st.sidebar.expander("💬 LINE連携設定"):
    l_en = st.checkbox("有効化", value=st.session_state.db["line_config"]["enabled"])
    l_at = st.text_input("トークン", value=st.session_state.db["line_config"]["access_token"], type="password")
    l_ui = st.text_input("ユーザーID", value=st.session_state.db["line_config"]["user_id"])

# --- 5. メイン画面 ---
st.title(f"🔥 AI Trainer Pro: {login_id}")
tabs = st.tabs(["📅 カレンダー", "📋 今日のメニュー", "📈 グラフ", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()

# --- Tab 2: 今日のメニュー (数値入力・達成率・自由報告・LINE) ---
with tabs[1]:
    st.info(f"**コーチからの伝言:** {st.session_state.db['daily_message']}")
    
    if st.button("AIメニューを生成"):
        res = model.generate_content("タスク4つと励ましを [MESSAGE]...[/MESSAGE] で出力。")
        st.session_state.db["daily_message"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", res.text, re.DOTALL).group(1).strip()
        tasks = [l.strip("- *") for l in res.text.split("\n") if l.strip().startswith(("-", "*"))]
        st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks[:4]]
        st.rerun()

    col_l, col_r = st.columns([2, 1])
    with col_l:
        st.subheader("✅ タスクチェック")
        for i, t in enumerate(st.session_state.db["tasks"]):
            st.session_state.db["tasks"][i]["done"] = st.checkbox(t["task"], value=t["done"], key=f"tk_{i}_{login_id}")
        
        done_num = sum(1 for t in st.session_state.db["tasks"] if t["done"])
        total = len(st.session_state.db["tasks"])
        rate = done_num / total if total > 0 else 0
        
        st.divider()
        st.metric("本日の達成度", f"{int(rate*100)}%")
        st.progress(rate)
        # 【復活】自由報告欄
        free_report = st.text_area("今日頑張ったこと（自由報告欄）", placeholder="例：今日は3ポイントシュートの練習を30分頑張りました！")

    with col_r:
        st.subheader("📈 数値記録")
        today_metrics = {}
        # ユニークなキーで入力欄を生成
        for m in st.session_state.db["metrics_defs"]:
            today_metrics[m] = st.number_input(f"{m}", value=0.0, key=f"input_v_{m}_{login_id}")

    if st.button("🚀 成果を保存 ＆ LINE報告送信"):
        save_to_gs("History", pd.DataFrame([{"user_id": login_id, "date": str(today), "rate": rate, "note": free_report}]))
        m_rows = [{"user_id": login_id, "date": str(today), "metric_name": k, "value": v} for k, v in today_metrics.items()]
        save_to_gs("Metrics", pd.DataFrame(m_rows), key_cols=['user_id', 'date', 'metric_name'])
        
        # LINE送信処理
        config = st.session_state.db["line_config"]
        if config["enabled"] and config["access_token"]:
            prompt = f"達成率{int(rate*100)}%、今日の感想：『{free_report}』に基づく熱い激励メッセージを保護者向けに作成して。"
            feedback = model.generate_content(prompt).text
            msg = f"\n【{login_id} 報告】\n達成率: {int(rate*100)}%\n頑張り: {free_report}\n\nコーチより:\n{feedback}"
            requests.post("https://api.line.me/v2/bot/message/push", 
                          headers={"Authorization": f"Bearer {config['access_token']}", "Content-Type": "application/json"},
                          json={"to": config["user_id"], "messages": [{"type": "text", "text": msg}]})
            st.toast("LINE送信完了！")
        
        st.success("スプレッドシートに保存しました！")
        st.balloons()

# --- Tab 6: 相談 (画像分析機能) ---
with tabs[4]:
    st.header("💬 コーチに相談・写真分析")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for m in st.session_state.chat_history:
        with st.chat_message(m["role"]): st.markdown(m["content"])

    if prompt := st.chat_input("フォームの改善点や食事のアドバイスを聞いてみよう"):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        # 【復活】画像がある場合は画像と一緒にGemini 3へ投げる
        inputs = [prompt]
        if uploaded_file:
            inputs.append(Image.open(uploaded_file))
            st.info("写真を分析しています...")

        response = model.generate_content(inputs)
        st.session_state.chat_history.append({"role": "assistant", "content": response.text})
        with st.chat_message("assistant"): st.markdown(response.text)

# (グラフ・ロードマップ・カレンダーのコードは前回通り)
