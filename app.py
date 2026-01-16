import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection

# --- 1. 接続設定（JSONキーはSecretsに設定済みと想定） ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    # 各シートを最新状態で読み込み
    profiles = conn.read(worksheet="Profiles", ttl=0)
    metrics = conn.read(worksheet="Metrics", ttl=0)
    
    # 列名のズレ（空白や大文字小文字）を自動修正してKeyErrorを防止
    profiles.columns = [c.strip().lower() for c in profiles.columns]
    metrics.columns = [c.strip().lower() for c in metrics.columns]
    
    # 日付型の変換
    if 'date' in metrics.columns:
        metrics['date'] = pd.to_datetime(metrics['date']).dt.date
        
    return profiles, metrics

# データロード
try:
    profiles_df, metrics_df = load_data()
except Exception as e:
    st.error("データの読み込みに失敗しました。シート名や列名を確認してください。")
    st.stop()

# --- 2. ユーザー選択（Profilesシートの 'name' 列を使用） ---
st.title("🏀 AI Basketball Coach")

if 'name' in profiles_df.columns:
    user_list = profiles_df['name'].unique().tolist()
    selected_user = st.selectbox("👤 ユーザーを選択", user_list)
    user_info = profiles_df[profiles_df['name'] == selected_user].iloc[0]
else:
    st.error("Profilesシートに 'name' 列が見つかりません。")
    st.stop()

# --- 3. ステータス表示（サイドバーからトップへ移動） ---
col1, col2 = st.columns(2)
with col1:
    coach = user_info.get('coach_name', '未設定')
    st.markdown(f"""
        <div style="background-color: #f0f2f6; padding: 10px; border-radius: 10px; border-left: 5px solid #ff4b4b;">
            <small>コーチ</small><br><strong>🔥 {coach}</strong>
        </div>
    """, unsafe_allow_html=True)
with col2:
    goal = user_info.get('current_goal', '目標未設定')
    st.markdown(f"""
        <div style="background-color: #f0f2f6; padding: 10px; border-radius: 10px; border-left: 5px solid #ff4b4b;">
            <small>現在の目標</small><br><strong>🎯 {goal}</strong>
        </div>
    """, unsafe_allow_html=True)

st.divider()

# --- 4. 横スクロール・進捗（Metricsシートと連動） ---
st.subheader("🗓️ 今週の進捗")

# 直近7日間の日付リスト
today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]

# モバイルでの視認性を高めた横並びボタン（スクロール対応）
# ※Streamlitのネイティブな挙動を活かしつつ、1列に並ばないよう調整
cols = st.columns(7)
for i, d in enumerate(date_range):
    # Metricsシートからその日のデータを検索
    day_data = metrics_df[(metrics_df['name'] == selected_user) & (metrics_df['date'] == d)]
    is_done = not day_data.empty
    
    # ラベル作成（曜日、アイコン、日付）
    day_label = f"{d.strftime('%a')}\n{'🏀' if is_done else '⚪'}\n{d.day}"
    
    if cols[i].button(day_label, key=f"day_{i}"):
        st.session_state.selected_date = d

# --- 5. 選択した日の詳細表示 ---
if "selected_date" not in st.session_state:
    st.session_state.selected_date = today

selected_day_data = metrics_df[
    (metrics_df['name'] == selected_user) & 
    (metrics_df['date'] == st.session_state.selected_date)
]

with st.container():
    st.write(f"### 📅 {st.session_state.selected_date} の詳細")
    if not selected_day_data.empty:
        row = selected_day_data.iloc[0]
        # 前チャットの仕様にある 'handling_speed' などの項目を表示
        speed = row.get('handling_speed', '-')
        st.metric("ハンドリングスピード", f"{speed} 秒")
        if 'comment' in row:
            st.info(f"コーチより: {row['comment']}")
    else:
        st.caption("この日の練習記録はありません。")

# --- 6. 今日の入力への導線 ---
st.divider()
if st.button("🚀 今日の練習を記録する", use_container_width=True, type="primary"):
    # ここで入力フォームのフラグを立てる、またはページ遷移
    st.session_state.input_mode = True
