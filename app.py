import streamlit as st
import pandas as pd
import datetime
import time
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection

# --- 0. 基本設定 & CSS (モバイル最適化) ---
st.set_page_config(page_title="AI Basketball Coach", layout="centered")

# AI設定 (Secretsから取得)
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

st.markdown("""
    <style>
    /* ステータスカード：高コントラスト設定 */
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

    /* 横スクロールカレンダーの強制 */
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

# --- 1. データ接続・集計ロジック ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=5)
def load_all_data():
    try:
        p = conn.read(worksheet="Profiles")
        m = conn.read(worksheet="Metrics")
        h = conn.read(worksheet="History") # 履歴シートも読み込み
        p.columns = [c.strip().lower() for c in p.columns]
        m.columns = [c.strip().lower() for c in m.columns]
        h.columns = [c.strip().lower() for c in h.columns]
        if 'date' in m.columns:
            m['date'] = pd.to_datetime(m['date']).dt.date
        if 'date' in h.columns:
            h['date'] = pd.to_datetime(h['date']).dt.date
        return p, m, h
    except:
        return None, None, None

def calculate_stats(m_df, user_id, metric_name):
    user_data = m_df[(m_df['user_id'] == user_id) & (m_df['metric_name'] == metric_name)]
    if user_data.empty:
        return {"is_first_time": True, "best": None, "avg": None}
    return {
        "is_first_time": False,
        "best": user_data['value'].min(),
        "avg": round(user_data['value'].tail(7).mean(), 2)
    }

def get_ai_feedback(coach, goal, val, stats):
    if stats["is_first_time"]:
        context = f"初挑戦の記録（{val}秒）です。比較対象はありません。"
    else:
        context = f"今日の記録{val}秒。自己ベスト{stats['best']}秒、直近7回平均{stats['avg']}秒です。"

    prompt = f"""
    あなたはバスケの「{coach}」です。目標は「{goal}」。
    {context}
    1. 数値を分析し、成長を褒めてください。
    2. 次に繋がる具体的な「提案」を1つ伝えてください。
    3. {coach}らしい口調で150文字以内で回答してください。
    """
    try:
        return model.generate_content(prompt).text
    except:
        return "素晴らしい努力です。明日も続けましょう！"

# --- 2. データの読み込み ---
profiles_df, metrics_df, history_df = load_all_data()
if profiles_df is None:
    st.error("データの読み込みに失敗しました。")
    st.stop()

# --- 3. ユーザー管理 ＆ ステータス表示 ---
st.title("🏀 Basketball AI Coach")

user_list = profiles_df['user_id'].unique().tolist()
selected_user = st.selectbox("👤 ユーザーを選択", user_list)

# 新規登録 expander
with st.expander("✨ 新規登録"):
    with st.form("reg_form"):
        u_id = st.text_input("新ユーザーID")
        u_goal = st.text_input("目標")
        if st.form_submit_button("登録"):
            if u_id and u_id not in user_list:
                new_p = pd.DataFrame([{"user_id": u_id, "goal": u_goal, "coach_name": "安西コーチ"}])
                conn.update(worksheet="Profiles", data=pd.concat([profiles_df, new_p], ignore_index=True))
                st.cache_data.clear()
                st.success("登録完了！"); time.sleep(1); st.rerun()

user_info = profiles_df[profiles_df['user_id'] == selected_user].iloc[0]

# ダッシュボード
c1, c2 = st.columns(2)
with c1: st.markdown(f'<div class="status-box"><small>コーチ</small><br><b>{user_info.get("coach_name", "安西")}</b></div>', unsafe_allow_html=True)
with c2: st.markdown(f'<div class="status-box"><small>目標</small><br><b>{user_info.get("goal", "未設定")}</b></div>', unsafe_allow_html=True)

with st.expander("⚙️ 設定変更"):
    with st.form("set_form"):
        n_coach = st.selectbox("コーチ変更", ["安西コーチ", "熱血コーチ", "冷静コーチ"])
        n_goal = st.text_input("目標変更", value=user_info.get("goal", ""))
        if st.form_submit_button("保存"):
            idx = profiles_df[profiles_df['user_id'] == selected_user].index[0]
            profiles_df.at[idx, 'coach_name'] = n_coach
            profiles_df.at[idx, 'goal'] = n_goal
            conn.update(worksheet="Profiles", data=profiles_df)
            st.cache_data.clear()
            st.success("更新！"); time.sleep(1); st.rerun()

st.divider()

# --- 4. カレンダー (14日間) ---
st.subheader("🗓️ 週間進捗")
today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(13, -1, -1)]

if "selected_date" not in st.session_state:
    st.session_state.selected_date = today

cols = st.columns(14)
for i, d in enumerate(date_range):
    has_p = not metrics_df[(metrics_df['user_id'] == selected_user) & (metrics_df['date'] == d)].empty
    btn_label = f"{d.strftime('%a')}\n{'🏀' if has_p else '⚪'}\n{d.day}"
    if cols[i].button(btn_label, key=f"d_{i}", type="primary" if st.session_state.selected_date == d else "secondary"):
        st.session_state.selected_date = d
        st.rerun()

# --- 5. 入力 & AI分析ポップアップ ---
st.subheader("🚀 今日の記録")
input_val = st.number_input("ハンドリング (秒)", min_value=0.0, value=20.0, step=0.1)

# フィードバック用ダイアログ
@st.dialog("コーチからのアドバイス")
def show_feedback_dialog(msg, coach):
    st.write(f"### 🔥 {coach}")
    st.info(msg)
    if st.button("明日もやる！"): st.rerun()

if st.button("タイムを保存する", use_container_width=True, type="primary"):
    with st.spinner("AIコーチが分析中..."):
        # A. 統計計算
        stats = calculate_stats(metrics_df, selected_user, "ハンドリング")
        # B. AIアドバイス生成
        coach_msg = get_ai_feedback(user_info.get("coach_name"), user_info.get("goal"), input_val, stats)
        # C. Metrics保存
        new_m = pd.DataFrame([{"user_id": selected_user, "date": today, "metric_name": "ハンドリング", "value": input_val}])
        conn.update(worksheet="Metrics", data=pd.concat([metrics_df, new_m], ignore_index=True))
        # D. History保存
        new_h = pd.DataFrame([{"user_id": selected_user, "date": today, "metric_name": "ハンドリング", "value": input_val, "coach_comment": coach_msg}])
        conn.update(worksheet="History", data=pd.concat([history_df, new_h], ignore_index=True))
        
        st.cache_data.clear()
        st.balloons()
        show_feedback_dialog(coach_msg, user_info.get("coach_name"))

# --- 6. 詳細表示 (履歴からのアドバイスも表示) ---
st.divider()
day_m = metrics_df[(metrics_df['user_id'] == selected_user) & (metrics_df['date'] == st.session_state.selected_date)]
day_h = history_df[(history_df['user_id'] == selected_user) & (history_df['date'] == st.session_state.selected_date)]

st.write(f"### 📊 {st.session_state.selected_date} の詳細")
if day_m.empty:
    st.caption("記録なし")
else:
    for _, row in day_m.iterrows():
        st.success(f"**{row['metric_name']}**: {row['value']} 秒")
    if not day_h.empty:
        st.info(f"💡 コーチの言葉:\n{day_h.iloc[0]['coach_comment']}")
