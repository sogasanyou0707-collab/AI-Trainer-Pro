import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection

# --- 1. 接続とデータ読み込み ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    profiles = conn.read(worksheet="Profiles", ttl=0)
    metrics = conn.read(worksheet="Metrics", ttl=0)
    
    # 列名のクレンジング（空白除去・小文字化）
    # A=user_id, B=date, C=metric_name, D=value と想定
    profiles.columns = [c.strip().lower() for c in profiles.columns]
    metrics.columns = [c.strip().lower() for c in metrics.columns]
    
    if 'date' in metrics.columns:
        metrics['date'] = pd.to_datetime(metrics['date']).dt.date
    return profiles, metrics

profiles_df, metrics_df = load_data()

# --- 2. ユーザー選択 ---
user_list = profiles_df['user_id'].unique().tolist()
selected_user = st.selectbox("👤 ユーザーを選択", user_list)
user_info = profiles_df[profiles_df['user_id'] == selected_user].iloc[0]

# --- 3. ステータス表示 ---
col1, col2 = st.columns(2)
with col1:
    st.info(f"🔥 コーチ: {user_info.get('coach_name', '安西コーチ')}")
with col2:
    st.info(f"🎯 目標: {user_info.get('goal', '目標未設定')}")

st.divider()

# --- 4. 横スクロール・進捗（「ハンドリング」の練習があるかチェック） ---
st.subheader("🗓️ 今週の進捗")
today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]

cols = st.columns(7)
for i, d in enumerate(date_range):
    # 【検索条件】ユーザーID ＋ 日付 ＋ 項目名が「ハンドリング」
    # metric_name 列(C列)から「ハンドリング」を検索
    has_practice = not metrics_df[
        (metrics_df['user_id'] == selected_user) & 
        (metrics_df['date'] == d) & 
        (metrics_df['metric_name'].astype(str).str.contains('ハンドリング'))
    ].empty
    
    label = f"{d.strftime('%a')}\n{'🏀' if has_practice else '⚪'}\n{d.day}"
    if cols[i].button(label, key=f"day_{i}"):
        st.session_state.selected_date = d

# --- 5. 選択した日の詳細（D列のvalueを取得） ---
if "selected_date" not in st.session_state:
    st.session_state.selected_date = today

# 該当日・該当ユーザーの「ハンドリング」行を抽出
handling_data = metrics_df[
    (metrics_df['user_id'] == selected_user) & 
    (metrics_df['date'] == st.session_state.selected_date) & 
    (metrics_df['metric_name'].astype(str).str.contains('ハンドリング'))
]

with st.container():
    st.write(f"### 📅 {st.session_state.selected_date} の記録")
    if not handling_data.empty:
        # D列（value）の値を取得して表示
        val = handling_data.iloc[0]['value']
        st.metric("ハンドリングスピード", f"{val} 秒")
    else:
        st.write("この日の「ハンドリング」記録はありません。")

# --- 6. 今日の入力フォーム（書き込み仕様） ---
st.divider()
if st.button("🚀 今日の練習を記録する", use_container_width=True, type="primary"):
    st.session_state.show_form = True

if st.session_state.get("show_form"):
    with st.form("input_form"):
        st.write("### 今日の記録を入力")
        # モバイルで入力しやすいスライダー
        new_speed = st.slider("ハンドリングスピード (秒)", 10.0, 60.0, 20.0, 0.1)
        
        if st.form_submit_button("保存する"):
            # ここでスプレッドシートに「記載」するロジック
            # A=user_id, B=今日, C="ハンドリング", D=new_speed を書き込む
            new_row = [selected_user, today.strftime('%Y-%m-%d'), "ハンドリング", new_speed]
            
            # 書き込み処理 (st-gsheets-connection を使用する場合)
            # conn.create(worksheet="Metrics", data=[new_row]) 
            
            st.success(f"{today} の記録として {new_speed}秒 を保存しました！")
            st.session_state.show_form = False
