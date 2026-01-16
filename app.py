import streamlit as st
import pandas as pd
import datetime

# --- 1. スプレッドシート接続設定 ---
# 接続情報を取得（st.connection経由、または既存の認証情報を利用）
conn = st.connection("gsheets", type="gsheets")

def load_app_data():
    # 各シートを読み込み
    profiles_df = conn.read(worksheet="Profiles")
    metrics_df = conn.read(worksheet="Metrics")
    # 日付列を日付型に変換しておく
    metrics_df['date'] = pd.to_datetime(metrics_df['date']).dt.date
    return profiles_df, metrics_df

# --- 2. データの取得と整形 ---
profiles_df, metrics_df = load_app_data()

# 選択されたユーザー（selected_user）の情報を抽出
# ※selected_user は画面上のセレクトボックスから取得
user_info = profiles_df[profiles_df['name'] == selected_user].iloc[0]

# 直近1週間のデータをMetricsから抽出
today = datetime.date.today()
start_date = today - datetime.timedelta(days=6)
weekly_metrics = metrics_df[
    (metrics_df['name'] == selected_user) & 
    (metrics_df['date'] >= start_date)
].sort_values('date')

# --- 3. UIへの反映（前回のスクロールUIに流し込む） ---

# A. プロフィール・目標の表示
col1, col2 = st.columns(2)
with col1:
    st.metric("Coach", user_info['coach_name']) # シートから読み込み
with col2:
    st.info(f"🎯 **目標:** {user_info['current_goal']}") # シートから読み込み

# B. 横スクロールカレンダーの動的生成
# weekly_metricsにデータがあれば🏀、なければ⚪を表示するループ処理
