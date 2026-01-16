import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection

# --- 1. 接続設定 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    # 各シートを最新状態で読み込み
    profiles = conn.read(worksheet="Profiles", ttl=0)
    metrics = conn.read(worksheet="Metrics", ttl=0)
    
    # 列名の空白削除と小文字化（マッチングを確実にするため）
    profiles.columns = [c.strip().lower() for c in profiles.columns]
    metrics.columns = [c.strip().lower() for c in metrics.columns]
    
    # 日付型の変換
    if 'date' in metrics.columns:
        metrics['date'] = pd.to_datetime(metrics['date']).dt.date
    return profiles, metrics

# データロード実行
try:
    profiles_df, metrics_df = load_data()
except Exception as e:
    st.error("データの読み取りに失敗しました。シート名や列構成を確認してください。")
    st.stop()

# --- 2. ユーザー選択（'user_id' 列を使用） ---
st.title("🏀 AI Basketball Coach")

if 'user_id' in profiles_df.columns:
    user_list = profiles_df['user_id'].unique().tolist()
    selected_user = st.selectbox("👤 ユーザーを選択", user_list)
    user_info = profiles_df[profiles_df['user_id'] == selected_user].iloc[0]
else:
    st.error("Profilesシートに 'user_id' 列が見つかりません。")
    st.stop()

# --- 3. ステータス表示（サイドバーからトップ画へ移動） ---
col1, col2 = st.columns(2)
with col1:
    # コーチ名がシートにない場合はデフォルトを表示
    coach = user_info.get('coach_name', '安西コーチ') 
    st.markdown(f"""
        <div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4b4b;">
            <small>現在のコーチ</small><br><strong>🔥 {coach}</strong>
        </div>
    """, unsafe_allow_html=True)
with col2:
    # Profilesシートの 'goal' 列から取得
    goal = user_info.get('goal', '目標未設定')
    st.markdown(f"""
        <div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4b4b;">
            <small>現在の目標</small><br><strong>🎯 {goal}</strong>
        </div>
    """, unsafe_allow_html=True)

st.divider()

# --- 4. 横スクロール・今週の進捗（Metricsシート連動） ---
st.subheader("🗓️ 今週の進捗")

today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]

# モバイル視認性を重視した7カラムのボタン配置
cols = st.columns(7)
for i, d in enumerate(date_range):
    # Metricsから該当ユーザー・該当日のデータを抽出
    day_data = metrics_df[(metrics_df['user_id'] == selected_user) & (metrics_df['date'] == d)]
    is_done = not day_data.empty
    
    label = f"{d.strftime('%a')}\n{'🏀' if is_done else '⚪'}\n{d.day}"
    if cols[i].button(label, key=f"day_{i}"):
        st.session_state.selected_date = d

# --- 5. 選択した日の詳細表示 ---
if "selected_date" not in st.session_state:
    st.session_state.selected_date = today

selected_day_data = metrics_df[
    (metrics_df['user_id'] == selected_user) & 
    (metrics_df['date'] == st.session_state.selected_date)
]

with st.container():
    st.write(f"### 📅 {st.session_state.selected_date} の詳細")
    if not selected_day_data.empty:
        row = selected_day_data.iloc[0]
        # Metricsシートに 'handling_speed' 列があることを想定
        speed = row.get('handling_speed', '-')
        st.metric("ハンドリングスピード", f"{speed} 秒")
    else:
        st.caption("この日の練習記録はありません。")

# --- 6. 今日の入力への導線 ---
st.divider()
if st.button("🚀 今日の練習を記録する", use_container_width=True, type="primary"):
    st.session_state.input_mode = True
