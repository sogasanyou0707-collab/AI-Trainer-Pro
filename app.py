import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import requests
import google.generativeai as genai
from datetime import datetime
import os

# ==========================================
# 1. ページ設定 & デザイン (モバイル対応CSS)
# ==========================================
st.set_page_config(page_title="AI Trainer バスケ管理", layout="centered")

st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: white !important;
        color: black !important;
    }
    h1, h2, h3, p, span, label, li, .stMarkdown {
        color: black !important;
    }
    button, div.stButton > button {
        background-color: white !important;
        color: black !important;
        border: 2px solid black !important;
        border-radius: 8px !important;
        font-weight: bold !important;
    }
    input, textarea, div[data-baseweb="input"], div[data-baseweb="select"] > div {
        background-color: white !important;
        color: black !important;
        border: 1px solid black !important;
    }
    .stProgress > div > div > div > div { background-color: black !important; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 定数 & キャッシュ管理
# ==========================================
CONFIG_FILE = "app_settings.json"

def load_local_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"selected_model": "gemini-3-pro"}

def save_local_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

# ==========================================
# 3. 外部データ・AIロジック
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)

def get_latest_models():
    """Gemini APIから最新モデルを取得（1.5系除外）"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        return [m.name.replace('models/', '') for m in genai.list_models() 
                if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    except: return ["gemini-3-pro"]

def ai_coach_feedback(report, model_name, goal):
    """AIによるコーチング提案"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel(model_name)
        prompt = f"あなたはバスケットボールの専門コーチです。目標「{goal}」を持つ選手に対し、以下の練習報告へのフィードバックと明日やるべきタスクを3つ提案してください。\n\n報告:\n{report}"
        return model.generate_content(prompt).text
    except Exception as e: return f"AIコーチエラー: {e}"

# ==========================================
# 4. データ読み込み & ユーザー選択
# ==========================================
profiles_df = conn.read(worksheet="Profiles", ttl=0)
history_df = conn.read(worksheet="History", ttl=0)
metrics_df = conn.read(worksheet="Metrics", ttl=0)

st.title("🏀 AI Trainer Pro")

# ユーザー・日付選択
col_u, col_d = st.columns(2)
with col_u:
    user_list = profiles_df["user_id"].dropna().unique().tolist() if not profiles_df.empty else []
    selected_user = st.selectbox("👤 ユーザー", options=user_list)
with col_d:
    selected_date = st.date_input("📅 日付", value=datetime.now())
    date_str = selected_date.strftime("%Y-%m-%d")

# ユーザー情報の特定
u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0]

# ==========================================
# 5. ユーザー詳細 (自動同期)
# ==========================================
with st.expander("⚙️ ユーザープロフィール・設定", expanded=False):
    st.write(f"**目標:** {u_prof.get('goal', '未設定')}")
    st.write(f"**担当コーチ:** {u_prof.get('coach_name', '未設定')}")
    metrics_str = st.text_input("計測項目 (カンマ区切り)", value=u_prof.get("tracked_metrics", "シュート率"))

# ==========================================
# 6. 今日のタスク & 練習記録
# ==========================================
st.subheader("📋 今日の練習タスク")
tasks_json = u_prof.get("tasks_json", "[]")
done_tasks = []
try:
    tasks_list = json.loads(tasks_json)
    for i, t in enumerate(tasks_list):
        if st.checkbox(t, key=f"t_{i}"):
            done_tasks.append(t)
    if tasks_list:
        rate = len(done_tasks)/len(tasks_list)
        st.progress(rate)
        st.write(f"達成率: {int(rate*100)}%")
except: st.write("タスク形式エラー")

st.divider()

st.subheader("📝 練習の振り返り")
user_rate = st.slider("自己評価", 1, 5, 3)
user_note = st.text_area("今日の内容・気づき", height=150)

# 動的メトリクス入力
metric_vals = {}
for m in metrics_str.split(","):
    m = m.strip()
    if m: metric_vals[m] = st.number_input(f"{m} の結果", value=0.0)

# ==========================================
# 7. アクションボタン (LINE送信 & AIコーチ)
# ==========================================
local_cfg = load_local_config()

if st.button("🚀 記録を保存してLINE報告", use_container_width=True):
    # LINE送信ロジック (E列, F列の値を使用)
    line_token = u_prof.get("line_token") # ProfilesシートのE列想定
    line_id = u_prof.get("line_user_id")   # ProfilesシートのF列想定
    
    if line_token and line_id:
        msg = f"【バスケ報告】{date_str}\n評価: {user_rate}\n内容: {user_note}\n完了: {', '.join(done_tasks)}"
        headers = {"Authorization": f"Bearer {line_token}", "Content-Type": "application/json"}
        payload = {"to": line_id, "messages": [{"type": "text", "text": msg}]}
        requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
        st.success("LINE送信 & 保存完了！")
    else:
        st.warning("LINE情報がProfilesシートに見つかりません。")

if st.button("💡 AIコーチに相談する", use_container_width=True):
    with st.spinner("AIコーチが思考中..."):
        advice = ai_coach_feedback(user_note, local_cfg["selected_model"], u_prof.get("goal"))
        st.markdown("### 🤖 AIコーチのアドバイス")
        st.info(advice)

# ==========================================
# 8. サイドバー (モデル選択)
# ==========================================
with st.sidebar:
    st.header("⚙️ System")
    models = get_latest_models()
    selected_m = st.selectbox("AIモデル選択", models, index=0)
    if selected_m != local_cfg["selected_model"]:
        local_cfg["selected_model"] = selected_m
        save_local_config(local_cfg)
        st.toast("モデル設定を更新しました")
    
    if st.button("🔄 シートを再読込"):
        st.rerun()

st.caption(f"Status: {local_cfg['selected_model']} Active")
