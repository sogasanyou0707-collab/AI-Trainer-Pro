import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection
import time

# --- 1. CSS設定（視認性とスクロールの強制） ---
# ここで定義したスタイルを HTML 描画時に適用させます
st.markdown("""
    <style>
    /* ステータスカード：背景グレー、文字は絶対黒 */
    .status-card {
        background-color: #e1e4eb !important;
        color: #1a1a1a !important;
        padding: 12px;
        border-radius: 10px;
        border-left: 5px solid #ff4b4b;
        margin-bottom: 10px;
    }
    .status-card b { color: #000 !important; font-size: 1.1rem; }
    
    /* 横スクロールカレンダーの外枠 */
    .scroll-container {
        display: flex;
        overflow-x: auto;
        gap: 10px;
        padding: 10px 0;
        margin-bottom: 10px;
        -webkit-overflow-scrolling: touch;
    }
    /* 各日付のカード */
    .date-item {
        min-width: 65px;
        background: #f0f2f6;
        border: 1px solid #ddd;
        border-radius: 10px;
        text-align: center;
        padding: 8px 0;
        color: #333;
    }
    /* 選択中の日付の強調 */
    .active-day {
        border: 2px solid #ff4b4b !important;
        background-color: #fff0f0 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. データ接続と読み込み ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=10)
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

# --- 3. ユーザー選択とメイン表示 ---
st.title("🏀 Basketball AI Coach")

user_list = profiles_df['user_id'].unique().tolist()
selected_user = st.selectbox("👤 ユーザーを選択", user_list)
user_idx = profiles_df[profiles_df['user_id'] == selected_user].index[0]
user_info = profiles_df.loc[user_idx]

# ステータス表示（白飛び防止・高コントラスト）
col1, col2 = st.columns(2)
with col1:
    st.markdown(f'<div class="status-card"><small>コーチ</small><br><b>{user_info.get("coach_name", "未設定")}</b></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="status-card"><small>目標</small><br><b>{user_info.get("goal", "未設定")}</b></div>', unsafe_allow_html=True)

# コーチ・目標の設定変更
with st.expander("⚙️ 設定を変更（コーチ・目標）"):
    with st.form("settings_form"):
        new_coach = st.selectbox("コーチを選択", ["安西コーチ", "熱血コーチ", "冷静コーチ"], index=0)
        new_goal = st.text_input("新しい目標", value=user_info.get('goal', ''))
        if st.form_submit_button("設定を保存"):
            profiles_df.at[user_idx, 'coach_name'] = new_coach
            profiles_df.at[user_idx, 'goal'] = new_goal
            conn.update(worksheet="Profiles", data=profiles_df)
            st.cache_data.clear()
            st.success("更新完了！")
            time.sleep(1)
            st.rerun()

st.divider()

# --- 4. カレンダー表示（HTMLエラー修正版） ---
st.subheader("🗓️ 今週の進捗")

today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
user_metrics = metrics_df[metrics_df['user_id'] == selected_user]

if "selected_date" not in st.session_state:
    st.session_state.selected_date = today

# HTMLを一つの文字列として確実に組み立てる
html_elements = []
for d in date_range:
    has_p = not user_metrics[user_metrics['date'] == d].empty
    icon = "🏀" if has_p else "⚪"
    # 選択中の日付に特別なクラスを付与
    css_class = "date-item active-day" if st.session_state.selected_date == d else "date-item"
    
    html_elements.append(f"""
        <div class="{css_class}">
            <div style="font-size:0.7rem; color: #666;">{d.strftime('%a')}</div>
            <div style="font-size:1.2rem; margin:3px 0;">{icon}</div>
            <div style="font-weight:bold; color: #333;">{d.day}</div>
        </div>
    """)

# join() で結合し、一つのdivで包む
full_html = f'<div class="scroll-container">{"".join(html_elements)}</div>'

# 重要：ここが正しく描画されるための肝です
st.markdown(full_html, unsafe_allow_html=True)

# 日付選択用スライダー
selected_d = st.select_slider("詳細を見る日付を選択", options=date_range, value=st.session_state.selected_date, format_func=lambda x: x.strftime('%m/%d'))
st.session_state.selected_date = selected_d

# --- 5. 入力と詳細表示 ---
st.divider()
st.subheader("🚀 今日の記録")
input_speed = st.number_input("ハンドリングスピード (秒)", min_value=0.0, value=20.0, step=0.1)

if st.button("このタイムを保存", use_container_width=True, type="primary"):
    new_entry = pd.DataFrame([{"user_id": selected_user, "date": today.strftime('%Y-%m-%d'), "metric_name": "ハンドリング", "value": input_speed}])
    updated = pd.concat([metrics_df, new_entry], ignore_index=True)
    conn.update(worksheet="Metrics", data=updated)
    st.cache_data.clear()
    st.balloons()
    st.rerun()

# 詳細表示エリア
day_data = user_metrics[user_metrics['date'] == st.session_state.selected_date]
with st.container():
    st.write(f"📊 **{st.session_state.selected_date} の詳細**")
    if day_data.empty:
        st.caption("記録はありません")
    else:
        for _, row in day_data.iterrows():
            st.write(f"・{row['metric_name']}: **{row['value']}**")
