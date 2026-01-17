import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection
import time

# --- 1. CSS設定（ボタンを横に強制整列させ、視認性を確保） ---
st.markdown("""
    <style>
    /* コーチ・目標カードの見栄え */
    .status-box {
        background-color: #e1e4eb !important;
        color: #000000 !important;
        padding: 12px;
        border-radius: 10px;
        border-left: 5px solid #ff4b4b;
        margin-bottom: 10px;
        min-height: 80px;
    }
    .status-box b { color: #000 !important; font-size: 1.1rem; }

    /* ★重要：ボタンをスマホでも横に並べる魔法のCSS */
    div[data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        gap: 8px !important;
    }
    div[data-testid="stHorizontalBlock"] > div {
        min-width: 65px !important;
    }
    /* ボタン自体のデザイン調整 */
    button[kind="secondary"] {
        height: 85px !important;
        border-radius: 12px !important;
        padding: 5px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. データ接続と読み込み ---
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

# --- 3. ユーザー選択とステータス ---
st.title("🏀 Basketball AI Coach")

user_list = profiles_df['user_id'].unique().tolist()
selected_user = st.selectbox("👤 ユーザーを選択", user_list)
user_info = profiles_df[profiles_df['user_id'] == selected_user].iloc[0]

# 視認性を高めたステータス表示
c1, c2 = st.columns(2)
with c1: st.markdown(f'<div class="status-box"><small>コーチ</small><br><b>{user_info.get("coach_name", "安西")}</b></div>', unsafe_allow_html=True)
with c2: st.markdown(f'<div class="status-box"><small>今の目標</small><br><b>{user_info.get("goal", "未設定")}</b></div>', unsafe_allow_html=True)

st.divider()

# --- 4. ラグなし！直感タップカレンダー ---
st.subheader("🗓️ 今週の進捗")

today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
user_metrics = metrics_df[metrics_df['user_id'] == selected_user]

if "selected_date" not in st.session_state:
    st.session_state.selected_date = today

# 横並びのカラムを作成（CSSで横スクロール化済み）
cols = st.columns(7)
for i, d in enumerate(date_range):
    # 練習データがあるかチェック
    has_p = not user_metrics[user_metrics['date'] == d].empty
    icon = "🏀" if has_p else "⚪"
    
    # ボタンのラベル（曜日 / アイコン / 日付）
    btn_label = f"{d.strftime('%a')}\n{icon}\n{d.day}"
    
    # タップ時に即座にsession_stateを更新
    if cols[i].button(btn_label, key=f"d_btn_{i}", type="primary" if st.session_state.selected_date == d else "secondary"):
        st.session_state.selected_date = d
        st.rerun()

# --- 5. 選択された日の詳細表示 ＆ 入力 ---
day_data = user_metrics[user_metrics['date'] == st.session_state.selected_date]

with st.container():
    st.markdown(f"### 📅 {st.session_state.selected_date} の記録")
    if not day_data.empty:
        for _, row in day_data.iterrows():
            st.success(f"✅ **{row['metric_name']}**: {row['value']} 秒")
    else:
        st.info("練習記録がありません。")

st.divider()

# --- 6. 今日の入力フォーム ---
st.subheader("🚀 今日の記録を保存")
input_speed = st.number_input("ハンドリングスピード (秒)", min_value=0.0, value=20.0, step=0.1)

if st.button("このタイムを保存する", use_container_width=True, type="primary"):
    new_entry = pd.DataFrame([{"user_id": selected_user, "date": today.strftime('%Y-%m-%d'), "metric_name": "ハンドリング", "value": input_speed}])
    updated = pd.concat([metrics_df, new_entry], ignore_index=True)
    conn.update(worksheet="Metrics", data=updated)
    st.cache_data.clear()
    st.balloons()
    st.rerun()
