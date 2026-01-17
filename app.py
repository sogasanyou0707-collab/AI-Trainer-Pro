import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection
import time

# --- 1. CSS設定（モバイル視認性・横スクロール・高コントラスト） ---
st.markdown("""
    <style>
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

    /* 横スクロールの強制（ボタンが縦に並ぶのを防ぐ） */
    div[data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        gap: 8px !important;
        padding-bottom: 10px;
    }
    div[data-testid="stHorizontalBlock"] > div {
        min-width: 65px !important;
    }
    button[kind="secondary"], button[kind="primary"] {
        height: 85px !important;
        border-radius: 12px !important;
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

# --- 3. ユーザー管理（選択 ＆ 新規登録） ---
st.title("🏀 Basketball AI Coach")

user_list = profiles_df['user_id'].unique().tolist()
selected_user = st.selectbox("👤 ユーザーを選択", user_list)

# 【復活】新規ユーザー登録
with st.expander("✨ 新規ユーザーを登録する"):
    with st.form("new_user_form"):
        new_id = st.text_input("ユーザーID（英数字）")
        new_goal_text = st.text_input("最初の目標")
        if st.form_submit_button("新規登録"):
            if new_id and new_id not in user_list:
                new_user = pd.DataFrame([{"user_id": new_id, "goal": new_goal_text, "coach_name": "安西コーチ"}])
                updated_p = pd.concat([profiles_df, new_user], ignore_index=True)
                conn.update(worksheet="Profiles", data=updated_p)
                st.cache_data.clear()
                st.success(f"{new_id}さんを登録しました！")
                time.sleep(1)
                st.rerun()
            else:
                st.error("有効なIDを入力してください（重複は不可）")

user_idx = profiles_df[profiles_df['user_id'] == selected_user].index[0]
user_info = profiles_df.loc[user_idx]

# --- 4. ステータス表示 ＆ 設定変更 ---
c1, c2 = st.columns(2)
with c1: st.markdown(f'<div class="status-box"><small>コーチ</small><br><b>{user_info.get("coach_name", "安西")}</b></div>', unsafe_allow_html=True)
with c2: st.markdown(f'<div class="status-box"><small>目標</small><br><b>{user_info.get("goal", "未設定")}</b></div>', unsafe_allow_html=True)

# 【復活】コーチ・目標の変更
with st.expander("⚙️ コーチ・目標の設定を変更"):
    with st.form("settings_form"):
        new_coach = st.selectbox("コーチを選択", ["安西コーチ", "熱血コーチ", "冷静コーチ"], 
                                 index=0 if user_info.get("coach_name") == "安西コーチ" else 1)
        new_goal = st.text_input("目標を更新", value=user_info.get("goal", ""))
        if st.form_submit_button("設定を保存"):
            profiles_df.at[user_idx, 'coach_name'] = new_coach
            profiles_df.at[user_idx, 'goal'] = new_goal
            conn.update(worksheet="Profiles", data=profiles_df)
            st.cache_data.clear()
            st.success("設定を更新しました！")
            time.sleep(1)
            st.rerun()

st.divider()

# --- 5. カレンダー機能（期間延長 ＆ 過去データ対応） ---
st.subheader("🗓️ 進捗（過去14日間）")

# 【解決案】表示期間を14日間に延長
today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(13, -1, -1)]
user_metrics = metrics_df[metrics_df['user_id'] == selected_user]

if "selected_date" not in st.session_state:
    st.session_state.selected_date = today

# 14日分のカラムを作成
cols = st.columns(14)
for i, d in enumerate(date_range):
    has_p = not user_metrics[user_metrics['date'] == d].empty
    icon = "🏀" if has_p else "⚪"
    btn_label = f"{d.strftime('%a')}\n{icon}\n{d.day}"
    
    # 選択中の日付を強調
    is_active = st.session_state.selected_date == d
    if cols[i].button(btn_label, key=f"d_btn_{i}", type="primary" if is_active else "secondary"):
        st.session_state.selected_date = d
        st.rerun()

# さらに古いデータを見たい場合のカレンダー入力
with st.expander("📅 もっと前のデータを探す"):
    past_date = st.date_input("日付を選択", value=st.session_state.selected_date)
    if past_date != st.session_state.selected_date:
        st.session_state.selected_date = past_date
        st.rerun()

# --- 6. 詳細表示 ＆ データ保存 ---
day_data = user_metrics[user_metrics['date'] == st.session_state.selected_date]

with st.container():
    st.markdown(f"### 📊 {st.session_state.selected_date} の記録")
    if not day_data.empty:
        for _, row in day_data.iterrows():
            st.success(f"✅ **{row['metric_name']}**: {row['value']} 秒")
    else:
        st.info("この日の記録はありません。")

st.divider()

# 自由な数値入力
st.subheader("🚀 今日の記録を保存")
input_speed = st.number_input("ハンドリングスピード (秒)", min_value=0.0, value=20.0, step=0.1)

if st.button("このタイムを保存する", use_container_width=True, type="primary"):
def get_analysis_data(metrics_df, user_id, metric_name, current_val):
    # 1. 該当ユーザーかつ、指定した項目（ハンドリング）の全データを抽出
    user_history = metrics_df[
        (metrics_df['user_id'] == user_id) & 
        (metrics_df['metric_name'] == metric_name)
    ]
    
    # 2. 初めての入力かどうかを判定
    if user_history.empty:
        return {
            "is_first_time": True,
            "best": None,
            "avg": None,
            "diff_best": None
        }
    
    # 3. データがある場合は統計を計算
    # ハンドリングは「数値が小さいほど良い」ので min() を使用
    personal_best = user_history['value'].min()
    avg_lately = user_history.tail(7)['value'].mean() # 直近7回の平均
    
    return {
        "is_first_time": False,
        "best": personal_best,
        "avg": round(avg_lately, 2),
        "diff_best": round(current_val - personal_best, 2) # ベストとの差
    }
