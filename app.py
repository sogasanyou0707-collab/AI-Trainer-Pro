import streamlit as st
import pandas as pd
import datetime
import time
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection

# --- 0. 基本設定 & モバイル最適化CSS ---
st.set_page_config(page_title="AI Basketball Coach", layout="centered")

# AI設定 (Secretsから取得)
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

st.markdown("""
    <style>
    /* ステータスカード */
    .status-box { background-color: #e1e4eb !important; color: #000 !important; padding: 12px; border-radius: 10px; border-left: 5px solid #ff4b4b; margin-bottom: 10px; min-height: 80px; }
    .status-box b { color: #000 !important; font-size: 1.1rem; }
    
    /* 横スクロールカレンダー */
    div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; overflow-x: auto !important; gap: 8px !important; padding-bottom: 10px; }
    div[data-testid="stHorizontalBlock"] > div { min-width: 65px !important; }
    
    /* タスク・入力エリア */
    .stCheckbox { background-color: #f0f2f6; padding: 12px; border-radius: 10px; margin-bottom: 8px; border: 1px solid #ddd; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. データ接続・読み込み ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=5)
def load_all_data():
    try:
        p = conn.read(worksheet="Profiles")
        m = conn.read(worksheet="Metrics")
        h = conn.read(worksheet="History")
        # 列名クレンジング
        p.columns = [c.strip().lower() for c in p.columns]
        m.columns = [c.strip().lower() for c in m.columns]
        h.columns = [c.strip().lower() for c in h.columns]
        if 'date' in m.columns: m['date'] = pd.to_datetime(m['date']).dt.date
        if 'date' in h.columns: h['date'] = pd.to_datetime(h['date']).dt.date
        return p, m, h
    except: return None, None, None

profiles_df, metrics_df, history_df = load_all_data()
if profiles_df is None: st.error("データ読み込み失敗"); st.stop()

# --- 2. ユーザー管理 ＆ 設定 ---
st.title("🏀 AI Basketball Coach")

# A. ユーザー切り替え
user_list = profiles_df['user_id'].unique().tolist()
selected_user = st.selectbox("👤 ユーザーを選択", user_list)
user_idx = profiles_df[profiles_df['user_id'] == selected_user].index[0]
user_info = profiles_df.loc[user_idx]

# B. 新規登録 ＆ プロフィール変更
with st.expander("⚙️ ユーザー管理・設定変更"):
    tab1, tab2 = st.tabs(["プロフィールの変更", "新規ユーザー登録"])
    
    with tab1:
        with st.form("edit_profile"):
            new_coach = st.selectbox("コーチ", ["安西コーチ", "熱血コーチ", "冷静コーチ"], 
                                     index=["安西コーチ", "熱血コーチ", "冷静コーチ"].index(user_info.get('coach_name', '安西コーチ')))
            new_goal = st.text_input("目標", value=user_info.get('goal', ''))
            
            # 数値項目の管理 (Profilesシートの tracked_metrics 列にカンマ区切りで保存)
            current_metrics = user_info.get('tracked_metrics', "ハンドリング")
            if pd.isna(current_metrics): current_metrics = "ハンドリング"
            
            st.write("---")
            st.write("📊 記録する数値項目")
            metric_list = [m.strip() for m in current_metrics.split(",") if m.strip()]
            
            # 削除機能
            to_remove = st.multiselect("削除する項目", metric_list)
            # 追加機能
            to_add = st.text_input("追加する項目（例：シュート成功率）")
            
            if st.form_submit_button("設定を更新"):
                final_metrics = [m for m in metric_list if m not in to_remove]
                if to_add: final_metrics.append(to_add)
                
                profiles_df.at[user_idx, 'coach_name'] = new_coach
                profiles_df.at[user_idx, 'goal'] = new_goal
                profiles_df.at[user_idx, 'tracked_metrics'] = ",".join(final_metrics)
                
                conn.update(worksheet="Profiles", data=profiles_df)
                st.cache_data.clear()
                st.success("設定を更新しました！"); time.sleep(1); st.rerun()

    with tab2:
        with st.form("add_user"):
            add_id = st.text_input("新規ユーザーID")
            add_goal = st.text_input("最初の目標")
            if st.form_submit_button("新規ユーザーを作成"):
                if add_id and add_id not in user_list:
                    new_u = pd.DataFrame([{"user_id": add_id, "goal": add_goal, "coach_name": "安西コーチ", "tracked_metrics": "ハンドリング"}])
                    conn.update(worksheet="Profiles", data=pd.concat([profiles_df, new_u], ignore_index=True))
                    st.cache_data.clear()
                    st.success(f"{add_id}さんを登録しました"); time.sleep(1); st.rerun()

# --- 3. ステータス表示 ---
c1, c2 = st.columns(2)
with c1: st.markdown(f'<div class="status-box"><small>コーチ</small><br><b>{user_info.get("coach_name", "安西")}</b></div>', unsafe_allow_html=True)
with c2: st.markdown(f'<div class="status-box"><small>今の目標</small><br><b>{user_info.get("goal", "未設定")}</b></div>', unsafe_allow_html=True)

st.divider()

# --- 4. 達成度連動カレンダー ---
today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(13, -1, -1)]
if "selected_date" not in st.session_state: st.session_state.selected_date = today

cols = st.columns(14)
for i, d in enumerate(date_range):
    day_m = metrics_df[(metrics_df['user_id'] == selected_user) & (metrics_df['date'] == d)]
    achieve_row = day_m[day_m['metric_name'] == '達成度']
    val = achieve_row.iloc[0]['value'] if not achieve_row.empty else 0
    icon = "🔥" if val >= 100 else ("🟡" if val > 0 else "⚪")
    
    if cols[i].button(f"{d.strftime('%a')}\n{icon}\n{d.day}", key=f"d_{i}", 
                       type="primary" if st.session_state.selected_date == d else "secondary"):
        st.session_state.selected_date = d; st.rerun()

# --- 5. 本日のAIメニュー ---
st.subheader("🗓️ 今日のメニュー")

def generate_tasks(coach, goal):
    prompt = f"バスケのコーチ「{coach}」として、目標「{goal}」に向けた今日のタスクを4つ厳選して。各15文字以内、箇条書きのみ。"
    try:
        res = model.generate_content(prompt)
        return [t.strip("- ").strip() for t in res.text.split("\n") if t][:4]
    except: return ["ハンドリング練習", "ステップワーク", "体幹", "動画分析"]

if "daily_tasks" not in st.session_state or st.session_state.get("task_user") != selected_user:
    st.session_state.daily_tasks = generate_tasks(user_info['coach_name'], user_info['goal'])
    st.session_state.task_user = selected_user

checks = []
for i, t in enumerate(st.session_state.daily_tasks):
    checks.append(st.checkbox(t, key=f"t_{i}"))

achievement = int((sum(checks) / 4) * 100)
st.progress(achievement / 100)
st.write(f"達成度: **{achievement}%**")

# --- 6. 数値記録 ＆ フリー入力 ---
st.divider()
st.subheader("📊 記録と振り返り")

# 登録されている数値項目を動的に表示
current_metrics_str = user_info.get('tracked_metrics', "ハンドリング")
if pd.isna(current_metrics_str): current_metrics_str = "ハンドリング"
metric_names = [m.strip() for m in current_metrics_str.split(",") if m.strip()]

input_data = {}
cols_m = st.columns(len(metric_names) if len(metric_names) > 0 else 1)
for i, m_name in enumerate(metric_names):
    with cols_m[i % len(cols_m)]:
        input_data[m_name] = st.number_input(f"{m_name}", min_value=0.0, value=0.0, step=0.1, key=f"m_{i}")

free_text = st.text_area("今日頑張ったこと", placeholder="例：左手のキレが良くなった！")

# --- 7. 保存 ＆ AIフィードバック ---
@st.dialog("コーチの分析レポート")
def show_feedback(msg, coach):
    st.write(f"### 🔥 {coach}")
    st.info(msg)
    if st.button("明日も頑張る"): st.rerun()

if st.button("今日の練習を報告する", use_container_width=True, type="primary"):
    with st.spinner("コーチが分析中..."):
        # AIフィードバック生成
        stats_text = f"達成度{achievement}%、記録:{input_data}"
        prompt = f"コーチ「{user_info['coach_name']}」として、今日の成果({stats_text})と感想({free_text})を分析し、目標({user_info['goal']})に向けた具体的なアドバイスを100文字程度で伝えて。"
        try: coach_msg = model.generate_content(prompt).text
        except: coach_msg = "素晴らしい！明日も続けよう。"

        # 保存用データ作成
        new_rows = [{"user_id": selected_user, "date": today, "metric_name": "達成度", "value": achievement}]
        for k, v in input_data.items():
            new_rows.append({"user_id": selected_user, "date": today, "metric_name": k, "value": v})
        
        # 保存
        conn.update(worksheet="Metrics", data=pd.concat([metrics_df, pd.DataFrame(new_rows)], ignore_index=True))
        new_h = pd.DataFrame([{"user_id": selected_user, "date": today, "metric_name": "総合", "value": achievement, "coach_comment": coach_msg, "free_text": free_text}])
        conn.update(worksheet="History", data=pd.concat([history_df, new_h], ignore_index=True))
        
        st.cache_data.clear()
        st.balloons()
        show_feedback(coach_msg, user_info['coach_name'])
