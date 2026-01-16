import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection

# --- 1. 接続とデータ読み込み ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    profiles = conn.read(worksheet="Profiles", ttl=0)
    metrics = conn.read(worksheet="Metrics", ttl=0)
    # クレンジング
    profiles.columns = [c.strip().lower() for c in profiles.columns]
    metrics.columns = [c.strip().lower() for c in metrics.columns]
    if 'date' in metrics.columns:
        metrics['date'] = pd.to_datetime(metrics['date']).dt.date
    return profiles, metrics

profiles_df, metrics_df = load_data()

# --- 2. ユーザー選択 ---
user_list = profiles_df['user_id'].unique().tolist()
selected_user = st.selectbox("👤 ユーザーを選択", user_list)
# 選択中のユーザー行を取得
user_idx = profiles_df[profiles_df['user_id'] == selected_user].index[0]
user_info = profiles_df.loc[user_idx]

# --- 3. コーチ選択 ＆ 目標設定 (Profilesシート更新) ---
with st.expander("⚙️ コーチ・目標の設定を変更する"):
    with st.form("settings_form"):
        # コーチ選択
        current_coach = user_info.get('coach_name', '安西コーチ')
        new_coach = st.selectbox("コーチを選択", ["安西コーチ", "熱血コーチ", "冷静コーチ"], index=0)
        
        # 目標設定
        current_goal = user_info.get('goal', '')
        new_goal = st.text_input("今の目標を入力", value=current_goal)
        
        if st.form_submit_button("設定を保存"):
            # Profilesの該当行を更新
            profiles_df.at[user_idx, 'coach_name'] = new_coach
            profiles_df.at[user_idx, 'goal'] = new_goal
            # スプレッドシートへ上書き保存
            conn.update(worksheet="Profiles", data=profiles_df)
            st.success("設定を更新しました！")
            st.rerun()

# --- 4. 現在のステータス表示 (トップ画) ---
col1, col2 = st.columns(2)
with col1:
    st.markdown(f"""<div style="background-color:#f0f2f6;padding:10px;border-radius:10px;border-left:5px solid #ff4b4b;">
    <small>コーチ</small><br><strong>{user_info.get('coach_name', '未設定')}</strong></div>""", unsafe_allow_html=True)
with col2:
    st.markdown(f"""<div style="background-color:#f0f2f6;padding:10px;border-radius:10px;border-left:5px solid #ff4b4b;">
    <small>目標</small><br><strong>{user_info.get('goal', '未設定')}</strong></div>""", unsafe_allow_html=True)

st.divider()

# --- 5. 今日のデータ入力 (Metricsシート記載) ---
st.subheader("🚀 今日の練習を記録")

# 入力項目（今回はハンドリングスピード）
with st.container():
    # キーボードを使わず親指で調整できるスライダー
    input_speed = st.slider("ハンドリングスピード (秒)", 10.0, 40.0, 20.0, 0.1)
    
    if st.button("この内容で保存する", use_container_width=True, type="primary"):
        # Metricsシート用の新しい行を作成
        # A:user_id, B:date, C:metric_name, D:value
        today_str = datetime.date.today()
        new_entry = pd.DataFrame([{
            "user_id": selected_user,
            "date": today_str,
            "metric_name": "ハンドリング",
            "value": input_speed
        }])
        
        # 既存のデータに結合して上書き、または追加（ライブラリの仕様に合わせる）
        updated_metrics = pd.concat([metrics_df, new_entry], ignore_index=True)
        conn.update(worksheet="Metrics", data=updated_metrics)
        
        st.balloons()
        st.success(f"{today_str} の記録を保存しました！")
        st.rerun()

# --- 6. カレンダー表示 (前回の横スクロールをここに配置) ---
# ... (以前作成したスクロールカレンダーのコード) ...
