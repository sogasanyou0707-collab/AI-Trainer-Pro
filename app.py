import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection
import streamlit.components.v1 as components  # 追加：HTML専用コンポーネント
import time

# --- 1. データ接続と読み込み ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=5)
def load_data():
    try:
        p = conn.read(worksheet="Profiles")
        m = conn.read(worksheet="Metrics")
        p.columns = [c.strip().lower() for c in p.columns]
        m.columns = [c.strip().lower() for c in m.columns]
        if 'date' in m.columns:
            m['date'] = pd.to_datetime(m['date']).dt.date
        return p, m
    except: return None, None

profiles_df, metrics_df = load_data()
if profiles_df is None: st.stop()

# --- 2. ユーザー選択とステータス表示 ---
st.title("🏀 Basketball AI Coach")

user_list = profiles_df['user_id'].unique().tolist()
selected_user = st.selectbox("👤 ユーザーを選択", user_list)
user_idx = profiles_df[profiles_df['user_id'] == selected_user].index[0]
user_info = profiles_df.loc[user_idx]

# ステータス表示（視認性を極限まで高めた黒文字固定）
col1, col2 = st.columns(2)
st.markdown(f"""
    <style>
    .status-box {{
        background-color: #e1e4eb !important;
        color: #000000 !important;
        padding: 10px;
        border-radius: 8px;
        border-left: 5px solid #ff4b4b;
        margin-bottom: 10px;
        min-height: 70px;
    }}
    </style>
    <div style="display: flex; gap: 10px;">
        <div class="status-box" style="flex: 1;"><small style="color:#555;">コーチ</small><br><b>{user_info.get('coach_name', '未設定')}</b></div>
        <div class="status-box" style="flex: 1;"><small style="color:#555;">今の目標</small><br><b>{user_info.get('goal', '未設定')}</b></div>
    </div>
""", unsafe_allow_html=True)

# 設定変更
with st.expander("⚙️ 設定を変更"):
    with st.form("settings"):
        new_coach = st.selectbox("コーチを選択", ["安西コーチ", "熱血コーチ", "冷静コーチ"])
        new_goal = st.text_input("目標を更新", value=user_info.get('goal', ''))
        if st.form_submit_button("保存"):
            profiles_df.at[user_idx, 'coach_name'] = new_coach
            profiles_df.at[user_idx, 'goal'] = new_goal
            conn.update(worksheet="Profiles", data=profiles_df)
            st.cache_data.clear()
            st.rerun()

st.divider()

# --- 3. 横スクロールカレンダー（コンポーネント方式） ---
st.subheader("🗓️ 今週の進捗")

today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
user_metrics = metrics_df[metrics_df['user_id'] == selected_user]

if "selected_date" not in st.session_state:
    st.session_state.selected_date = today

# HTML/CSSを一つの文字列として定義
html_elements = ""
for d in date_range:
    has_p = not user_metrics[user_metrics['date'] == d].empty
    icon = "🏀" if has_p else "⚪"
    is_active = "border: 2.5px solid #ff4b4b; background-color: #fff0f0;" if st.session_state.selected_date == d else "border: 1px solid #ddd; background-color: #f0f2f6;"
    
    html_elements += f"""
    <div style="min-width: 65px; {is_active} border-radius: 12px; text-align: center; padding: 10px 0; color: #333;">
        <div style="font-size: 0.8rem; color: #666;">{d.strftime('%a')}</div>
        <div style="font-size: 1.5rem; margin: 5px 0;">{icon}</div>
        <div style="font-weight: bold; font-size: 1rem;">{d.day}</div>
    </div>
    """

calendar_html = f"""
<div style="display: flex; overflow-x: auto; gap: 12px; padding: 10px 5px; font-family: sans-serif; -webkit-overflow-scrolling: touch;">
    {html_elements}
</div>
"""

# HTMLコンポーネントとして描画（これが最も確実な方法です）
components.html(calendar_html, height=120)

# 日付選択用スライダー
selected_d = st.select_slider("詳細を見る日付を選択", options=date_range, value=st.session_state.selected_date, format_func=lambda x: x.strftime('%m/%d'))
st.session_state.selected_date = selected_d

# --- 4. 記録入力 ---
st.divider()
input_speed = st.number_input("🚀 今日のハンドリング (秒)", min_value=0.0, value=20.0, step=0.1)

if st.button("このタイムを保存する", use_container_width=True, type="primary"):
    new_entry = pd.DataFrame([{"user_id": selected_user, "date": today.strftime('%Y-%m-%d'), "metric_name": "ハンドリング", "value": input_speed}])
    updated = pd.concat([metrics_df, new_entry], ignore_index=True)
    conn.update(worksheet="Metrics", data=updated)
    st.cache_data.clear()
    st.balloons()
    st.rerun()

# 詳細表示
day_data = user_metrics[user_metrics['date'] == st.session_state.selected_date]
with st.container():
    if not day_data.empty:
        for _, row in day_data.iterrows():
            st.write(f"✅ **{row['metric_name']}**: {row['value']} 秒")
    else:
        st.caption("この日の記録はありません")
