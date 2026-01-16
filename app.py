import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection

# --- 1. 接続とデータ読み込み ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_all_data():
    # 各シートを読み込み（TTL=0で最新の状態を取得）
    profiles = conn.read(worksheet="Profiles", ttl=0)
    metrics = conn.read(worksheet="Metrics", ttl=0)
    # 日付列の変換
    metrics['date'] = pd.to_datetime(metrics['date']).dt.date
    return profiles, metrics

profiles_df, metrics_df = load_all_data()

# --- 2. ユーザー選択セクション ---
st.title("🏀 AI Basketball Coach")

user_list = profiles_df['name'].tolist()
selected_user = st.selectbox("👤 ユーザーを選択", user_list)

# 選択されたユーザーの詳細情報を取得
user_info = profiles_df[profiles_df['name'] == selected_user].iloc[0]

# --- 3. ステータス表示（Profilesシートと連動） ---
col1, col2 = st.columns(2)
with col1:
    st.markdown(f"""
        <div style="background-color: #f0f2f6; padding: 10px; border-radius: 10px; border-left: 5px solid #ff4b4b;">
            <small>コーチ</small><br><strong>🔥 {user_info['coach_name']}</strong>
        </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"""
        <div style="background-color: #f0f2f6; padding: 10px; border-radius: 10px; border-left: 5px solid #ff4b4b;">
            <small>現在の目標</small><br><strong>🎯 {user_info['current_goal']}</strong>
        </div>
    """, unsafe_allow_html=True)

st.divider()

# --- 4. 横スクロール・進捗（Metricsシートと連動） ---
st.subheader("🗓️ 今週の進捗")

# 直近7日間の枠を作成
today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]

# ユーザーの今週のデータを抽出
user_metrics = metrics_df[metrics_df['name'] == selected_user]

# スクロールエリアの描画（以前のCSSを流用）
cols = st.columns(7)
for i, d in enumerate(date_range):
    # その日のデータがあるか判定
    day_data = user_metrics[user_metrics['date'] == d]
    is_done = not day_data.empty
    
    label = f"{d.strftime('%a')}\n{'🏀' if is_done else '⚪'}\n{d.day}"
    if cols[i].button(label, key=f"day_{i}"):
        st.session_state.selected_date = d

# --- 5. 選択した日の詳細表示 ---
if "selected_date" not in st.session_state:
    st.session_state.selected_date = today

selected_day_data = user_metrics[user_metrics['date'] == st.session_state.selected_date]

if not selected_day_data.empty:
    row = selected_day_data.iloc[0]
    st.info(f"📅 {st.session_state.selected_date} の記録：ハンドリング {row['handling_speed']} 秒")
else:
    st.write(f"📅 {st.session_state.selected_date} の記録はありません。")

# --- 6. クイック入力への導線 ---
st.divider()
if st.button("🚀 今日の練習を記録する", use_container_width=True, type="primary"):
    st.switch_page("pages/input_form.py") # 入力画面（別ページ想定）へ
