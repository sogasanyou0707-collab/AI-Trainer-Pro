import streamlit as st
import pandas as pd
import datetime
import time
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection

# --- 0. 基本設定 & CSS ---
st.set_page_config(page_title="Coach App", layout="centered")

genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

st.markdown("""
    <style>
    .status-box { background-color: #e1e4eb !important; color: #000 !important; padding: 12px; border-radius: 10px; border-left: 5px solid #ff4b4b; margin-bottom: 10px; }
    div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; overflow-x: auto !important; gap: 8px !important; }
    div[data-testid="stHorizontalBlock"] > div { min-width: 65px !important; }
    .stCheckbox { background-color: #f0f2f6; padding: 10px; border-radius: 8px; margin-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. データ接続 ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=5)
def load_all_data():
    try:
        p = conn.read(worksheet="Profiles")
        m = conn.read(worksheet="Metrics")
        h = conn.read(worksheet="History")
        p.columns = [c.strip().lower() for c in p.columns]
        m.columns = [c.strip().lower() for c in m.columns]
        h.columns = [c.strip().lower() for c in h.columns]
        if 'date' in m.columns: m['date'] = pd.to_datetime(m['date']).dt.date
        if 'date' in h.columns: h['date'] = pd.to_datetime(h['date']).dt.date
        return p, m, h
    except: return None, None, None

profiles_df, metrics_df, history_df = load_all_data()

# --- 2. AIタスク生成ロジック ---
def generate_daily_tasks(coach, goal):
    prompt = f"あなたはバスケの{coach}です。目標は『{goal}』。今日取り組むべき具体的な練習タスクを4つ、箇条書きで提案してください。1つ15文字以内で。余計な説明は不要です。"
    try:
        response = model.generate_content(prompt)
        tasks = [t.strip("- ").strip() for t in response.text.strip().split("\n") if t][:4]
        return tasks
    except:
        return ["ハンドリング練習", "フリースロー10本", "体幹トレーニング", "動画でフォーム確認"]

# --- 3. メイン画面 ---
st.title("🏀 AI Basketball Coach")

user_list = profiles_df['user_id'].unique().tolist()
selected_user = st.selectbox("👤 ユーザーを選択", user_list)
user_info = profiles_df[profiles_df['user_id'] == selected_user].iloc[0]

# --- 4. カレンダー表示 (達成度連動型) ---
st.subheader("🗓️ 進捗カレンダー")
today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(13, -1, -1)]

if "selected_date" not in st.session_state:
    st.session_state.selected_date = today

cols = st.columns(14)
for i, d in enumerate(date_range):
    # Metricsからその日の達成度を取得
    day_metrics = metrics_df[(metrics_df['user_id'] == selected_user) & (metrics_df['date'] == d)]
    achieve_row = day_metrics[day_metrics['metric_name'] == '達成度']
    
    val = achieve_row.iloc[0]['value'] if not achieve_row.empty else 0
    icon = "🔥" if val >= 100 else ("🟡" if val > 0 else "⚪")
    
    if cols[i].button(f"{d.strftime('%a')}\n{icon}\n{d.day}", key=f"d_{i}", 
                       type="primary" if st.session_state.selected_date == d else "secondary"):
        st.session_state.selected_date = d
        st.rerun()

st.divider()

# --- 5. 本日のトレーニングメニュー ---
st.subheader("🔥 今日のメニュー")

# AIタスクの保持
if "daily_tasks" not in st.session_state or st.session_state.get("last_task_date") != today:
    st.session_state.daily_tasks = generate_daily_tasks(user_info['coach_name'], user_info['goal'])
    st.session_state.last_task_date = today

# チェックボックス
checks = []
for i, task in enumerate(st.session_state.daily_tasks):
    checks.append(st.checkbox(task, key=f"task_{i}"))

# 達成度計算
achievement = int((sum(checks) / 4) * 100)
st.progress(achievement / 100)
st.write(f"現在の達成度: **{achievement}%**")

# --- 6. 追加数値 ＆ フリー入力 ---
st.divider()
st.subheader("📊 記録と振り返り")
col_a, col_b = st.columns(2)
with col_a:
    hand_val = st.number_input("ハンドリング(秒)", min_value=0.0, value=20.0, step=0.1)
with col_b:
    weight_val = st.number_input("体重 (kg) ※任意", min_value=0.0, value=0.0, step=0.1)

free_comment = st.text_area("今日頑張ったこと・気づき", placeholder="例：左手のドリブルが安定してきた！")

# --- 7. 保存処理 ---
@st.dialog("コーチの分析レポート")
def show_feedback(msg, coach):
    st.write(f"### 🔥 {coach}")
    st.info(msg)
    if st.button("明日も頑張る"): st.rerun()

if st.button("今日の成果を報告する", use_container_width=True, type="primary"):
    with st.spinner("コーチが今日の動きを分析中..."):
        # AIフィードバック生成（数値と感想をAIに渡す）
        stats = {"is_first_time": metrics_df[metrics_df['user_id']==selected_user].empty, "best": 18.0, "avg": 19.5} # 簡略化
        feedback_prompt = f"今日の達成度は{achievement}%、ハンドリングは{hand_val}秒。感想：{free_comment}。これらを踏まえて分析・提案してください。"
        # (実際は以前のget_ai_feedback関数を呼ぶ)
        coach_msg = "素晴らしい！チェックを全部埋めましたね。その調子ですよ！" 

        # データ一括保存
        new_data = [
            {"user_id": selected_user, "date": today, "metric_name": "達成度", "value": achievement},
            {"user_id": selected_user, "date": today, "metric_name": "ハンドリング", "value": hand_val}
        ]
        if weight_val > 0:
            new_data.append({"user_id": selected_user, "date": today, "metric_name": "体重", "value": weight_val})
        
        updated_metrics = pd.concat([metrics_df, pd.DataFrame(new_data)], ignore_index=True)
        conn.update(worksheet="Metrics", data=updated_metrics)
        
        # History保存
        new_history = pd.DataFrame([{"user_id": selected_user, "date": today, "metric_name": "総合", "value": achievement, "coach_comment": coach_msg, "free_text": free_comment}])
        conn.update(worksheet="History", data=pd.concat([history_df, new_history], ignore_index=True))
        
        st.cache_data.clear()
        st.balloons()
        show_feedback(coach_msg, user_info['coach_name'])
