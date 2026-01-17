import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection
import time

# --- 1. 接続設定とキャッシュ管理 ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_data():
    try:
        profiles = conn.read(worksheet="Profiles")
        metrics = conn.read(worksheet="Metrics")
        # 列名のクレンジング
        profiles.columns = [c.strip().lower() for c in profiles.columns]
        metrics.columns = [c.strip().lower() for c in metrics.columns]
        if 'date' in metrics.columns:
            metrics['date'] = pd.to_datetime(metrics['date']).dt.date
        return profiles, metrics
    except Exception:
        return None, None

profiles_df, metrics_df = load_data()

if profiles_df is None:
    st.error("データの読み込みに失敗しました。時間をおいて再度お試しください。")
    st.stop()

# --- 2. ユーザー選択・現在のステータス ---
st.title("🏀 Basketball AI Coach")

user_list = profiles_df['user_id'].unique().tolist()
selected_user = st.selectbox("👤 ユーザーを選択", user_list)
user_idx = profiles_df[profiles_df['user_id'] == selected_user].index[0]
user_info = profiles_df.loc[user_idx]

# トップ画面でのコーチ・目標表示
col1, col2 = st.columns(2)
with col1:
    st.markdown(f"""<div style="background-color:#f0f2f6;padding:10px;border-radius:10px;border-left:5px solid #ff4b4b;">
    <small>コーチ</small><br><strong>{user_info.get('coach_name', '未設定')}</strong></div>""", unsafe_allow_html=True)
with col2:
    st.markdown(f"""<div style="background-color:#f0f2f6;padding:10px;border-radius:10px;border-left:5px solid #ff4b4b;">
    <small>現在の目標</small><br><strong>{user_info.get('goal', '未設定')}</strong></div>""", unsafe_allow_html=True)

# 設定変更（エクスパンダーで隠す）
with st.expander("⚙️ コーチ・目標の変更"):
    with st.form("settings"):
        new_coach = st.selectbox("コーチを選択", ["安西コーチ", "熱血コーチ", "冷静コーチ"], 
                                 index=0 if user_info.get('coach_name') == '安西コーチ' else 1)
        new_goal = st.text_input("目標を更新", value=user_info.get('goal', ''))
        if st.form_submit_button("設定を保存"):
            profiles_df.at[user_idx, 'coach_name'] = new_coach
            profiles_df.at[user_idx, 'goal'] = new_goal
            conn.update(worksheet="Profiles", data=profiles_df)
            st.cache_data.clear()
            st.success("設定を更新しました！")
            time.sleep(1)
            st.rerun()

st.divider()

# --- 3. 今日のデータ入力 (フリー入力版) ---
st.subheader("🚀 今日の記録を入れる")

# スライダーから数値入力（自由入力）に変更
# 範囲を 0.0〜500.0 など広く設定
input_speed = st.number_input("ハンドリングスピード (秒)", min_value=0.0, max_value=500.0, value=20.0, step=0.1)

if st.button("今日の練習を保存する", use_container_width=True, type="primary"):
    today_val = datetime.date.today()
    new_entry = pd.DataFrame([{
        "user_id": selected_user,
        "date": today_val.strftime('%Y-%m-%d'),
        "metric_name": "ハンドリング",
        "value": input_speed
    }])
    
    try:
        updated_metrics = pd.concat([metrics_df, new_entry], ignore_index=True)
        conn.update(worksheet="Metrics", data=updated_metrics)
        st.cache_data.clear()
        st.balloons()
        st.success(f"{input_speed}秒で保存しました！")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error("保存に失敗しました。")

st.divider()

# --- 4. 復活！横スクロール風カレンダー ---
st.subheader("🗓️ 今週の進捗")

# 直近7日間の日付
today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]

# このユーザーの今週のデータを抽出
user_all_metrics = metrics_df[metrics_df['user_id'] == selected_user]

# スマホで見やすくするために7つのボタンを並列配置
cols = st.columns(7)
for i, d in enumerate(date_range):
    # その日に何らかの練習データ（metric_name問わず）があるか
    has_practice = not user_all_metrics[user_all_metrics['date'] == d].empty
    
    # 選択中の日付かどうかで色を変える
    is_selected = "selected_date" in st.session_state and st.session_state.selected_date == d
    icon = "🏀" if has_practice else "⚪"
    btn_label = f"{d.strftime('%a')}\n{icon}\n{d.day}"
    
    if cols[i].button(btn_label, key=f"d_btn_{i}"):
        st.session_state.selected_date = d

# 選択した日の詳細表示
if "selected_date" not in st.session_state:
    st.session_state.selected_date = today

selected_day_data = user_all_metrics[user_all_metrics['date'] == st.session_state.selected_date]

with st.container():
    st.write(f"### 📅 {st.session_state.selected_date} の詳細")
    if not selected_day_all_data := selected_day_data:
        st.caption("記録なし")
    else:
        for _, row in selected_day_all_data.iterrows():
            st.write(f"・{row['metric_name']}: **{row['value']}**")
