import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection
import time

# --- 1. CSSによる外観の強制固定（視認性向上） ---
st.markdown("""
    <style>
    /* ステータスカード：背景を少し濃くし、文字色を黒に固定 */
    .status-card {
        background-color: #e1e4eb !important;
        color: #1a1a1a !important;
        padding: 12px;
        border-radius: 10px;
        border-left: 5px solid #ff4b4b;
        margin-bottom: 10px;
    }
    .status-card small { color: #555 !important; }

    /* 横スクロールカレンダーのコンテナ */
    .scroll-container {
        display: flex;
        overflow-x: auto;
        gap: 10px;
        padding: 10px 5px;
        white-space: nowrap;
        -webkit-overflow-scrolling: touch;
    }
    /* 日付カードのスタイル */
    .date-item {
        min-width: 60px;
        background: #f8f9fb;
        border: 1px solid #ddd;
        border-radius: 10px;
        text-align: center;
        padding: 8px 5px;
        color: #333;
    }
    .date-item.active {
        border-color: #ff4b4b;
        background-color: #fff0f0;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 接続とデータ読み込み ---
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

# --- 3. ユーザー選択とステータス表示 ---
st.title("🏀 AI Coach")
user_list = profiles_df['user_id'].unique().tolist()
selected_user = st.selectbox("👤 ユーザー選択", user_list)
user_idx = profiles_df[profiles_df['user_id'] == selected_user].index[0]
user_info = profiles_df.loc[user_idx]

# 文字が見えるように修正したステータス表示
col1, col2 = st.columns(2)
with col1:
    st.markdown(f'<div class="status-card"><small>コーチ</small><br><b>{user_info.get("coach_name", "安西")}</b></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="status-card"><small>目標</small><br><b>{user_info.get("goal", "未設定")}</b></div>', unsafe_allow_html=True)

st.divider()

# --- 4. 横スクロールカレンダーの実装 ---
st.subheader("🗓️ 今週の進捗")

today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
user_metrics = metrics_df[metrics_df['user_id'] == selected_user]

# HTMLで横スクロールを実現
html_scroll = '<div class="scroll-container">'
for d in date_range:
    has_p = not user_metrics[user_metrics['date'] == d].empty
    icon = "🏀" if has_p else "⚪"
    active_class = "active" if "selected_date" in st.session_state and st.session_state.selected_date == d else ""
    
    html_scroll += f"""
        <div class="date-item {active_class}">
            <div style="font-size:0.7rem;">{d.strftime('%a')}</div>
            <div style="font-size:1.2rem; margin:3px 0;">{icon}</div>
            <div style="font-weight:bold;">{d.day}</div>
        </div>
    """
html_scroll += '</div>'
st.markdown(html_scroll, unsafe_allow_html=True)

# 日付選択用のボタン（スクロールの邪魔をしないように下に配置）
selected_d = st.select_slider("詳細を見る日付を選択", options=date_range, value=today, format_func=lambda x: x.strftime('%m/%d'))
st.session_state.selected_date = selected_d

# --- 5. 入力フォーム ---
st.divider()
st.subheader("🚀 今日の記録")
input_speed = st.number_input("ハンドリングスピード (秒)", min_value=0.0, value=20.0, step=0.1)

if st.button("保存する", use_container_width=True, type="primary"):
    new_entry = pd.DataFrame([{"user_id": selected_user, "date": today.strftime('%Y-%m-%d'), "metric_name": "ハンドリング", "value": input_speed}])
    updated = pd.concat([metrics_df, new_entry], ignore_index=True)
    conn.update(worksheet="Metrics", data=updated)
    st.cache_data.clear()
    st.balloons()
    st.rerun()

# --- 6. 選択した日の詳細 ---
day_data = user_metrics[user_metrics['date'] == st.session_state.selected_date]
with st.expander(f"📅 {st.session_state.selected_date} の詳細"):
    if day_data.empty: st.write("記録なし")
    else:
        for _, row in day_data.iterrows():
            st.write(f"・{row['metric_name']}: **{row['value']}**")
