import streamlit as st
import pandas as pd
import datetime
import time
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection

# --- 0. モバイル視認性・完全強化CSS ---
st.set_page_config(page_title="Coach App", layout="centered")

genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

st.markdown("""
    <style>
    /* 全体の文字色を黒に、背景を白に近く固定 */
    .stApp { color: #000000; }
    
    /* ステータスカード */
    .status-box { background-color: #e1e4eb !important; color: #000000 !important; padding: 12px; border-radius: 10px; border-left: 5px solid #ff4b4b; margin-bottom: 10px; }
    .status-box b { color: #000000 !important; }
    
    /* 【最重要】チェックボックスの視認性向上 */
    div[data-testid="stCheckbox"] label p {
        color: #000000 !important;
        font-weight: bold !important;
        font-size: 1.1rem !important;
    }
    div[data-testid="stCheckbox"] {
        background-color: #ffffff !important;
        border: 1px solid #cccccc !important;
        padding: 5px 10px !important;
        border-radius: 8px !important;
        margin-bottom: 10px !important;
    }

    /* 横スクロールカレンダー */
    div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; overflow-x: auto !important; gap: 8px !important; padding-bottom: 10px; }
    div[data-testid="stHorizontalBlock"] > div { min-width: 65px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. データ読み込み ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=5)
def load_all_data():
    try:
        p = conn.read(worksheet="Profiles")
        m = conn.read(worksheet="Metrics")
        h = conn.read(worksheet="History")
        p.columns = [c.strip().lower() for c in p.columns]; m.columns = [c.strip().lower() for c in m.columns]; h.columns = [c.strip().lower() for c in h.columns]
        if 'date' in m.columns: m['date'] = pd.to_datetime(m['date']).dt.date
        if 'date' in h.columns: h['date'] = pd.to_datetime(h['date']).dt.date
        return p, m, h
    except: return None, None, None

profiles_df, metrics_df, history_df = load_all_data()
if profiles_df is None: st.stop()

# --- 2. ユーザー選択 ---
user_list = profiles_df['user_id'].unique().tolist()
selected_user = st.selectbox("👤 ユーザーを選択", user_list)
user_idx = profiles_df[profiles_df['user_id'] == selected_user].index[0]
user_info = profiles_df.loc[user_idx]

# ステータス表示
c1, c2 = st.columns(2)
with c1: st.markdown(f'<div class="status-box"><small>コーチ</small><br><b>{user_info.get("coach_name", "安西")}</b></div>', unsafe_allow_html=True)
with c2: st.markdown(f'<div class="status-box"><small>目標</small><br><b>{user_info.get("goal", "未設定")}</b></div>', unsafe_allow_html=True)

# --- 3. カレンダー ---
today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(13, -1, -1)]
if "selected_date" not in st.session_state: st.session_state.selected_date = today

cols = st.columns(14)
for i, d in enumerate(date_range):
    # カレンダーは数値データのMetricsから達成度を読み取る
    day_m = metrics_df[(metrics_df['user_id'] == selected_user) & (metrics_df['date'] == d)]
    achieve = day_m[day_m['metric_name'] == '達成度']
    val = achieve.iloc[0]['value'] if not achieve.empty else 0
    icon = "🔥" if val >= 100 else ("🟡" if val > 0 else "⚪")
    if cols[i].button(f"{d.strftime('%a')}\n{icon}\n{d.day}", key=f"d_{i}", type="primary" if st.session_state.selected_date == d else "secondary"):
        st.session_state.selected_date = d; st.rerun()

# --- 4. 本日のメニュー（今日の日付の時のみ表示） ---
if st.session_state.selected_date == today:
    st.subheader("🗓️ 今日のメニュー")
    if "daily_tasks" not in st.session_state or st.session_state.get("task_user") != selected_user:
        prompt = f"コーチ「{user_info['coach_name']}」として、目標「{user_info['goal']}」に向けた今日のタスクを4つ厳選して。15文字以内の箇条書き（- 項目）のみで回答して。"
        try:
            res = model.generate_content(prompt)
            st.session_state.daily_tasks = [t.strip("- ").strip() for t in res.text.split("\n") if t][:4]
        except: st.session_state.daily_tasks = ["ハンドリング", "体幹", "シュート", "動画確認"]
        st.session_state.task_user = selected_user

    checks = []
    for i, t in enumerate(st.session_state.daily_tasks):
        checks.append(st.checkbox(t, key=f"t_{i}"))
    
    achievement = int((sum(checks) / 4) * 100)
    st.progress(achievement / 100)

    # 記録エリア
    st.divider()
    m_names = [m.strip() for m in user_info.get('tracked_metrics', "ハンドリング").split(",") if m.strip()]
    input_vals = {}
    m_cols = st.columns(len(m_names) if m_names else 1)
    for i, m_name in enumerate(m_names):
        with m_cols[i % len(m_cols)]:
            input_vals[m_name] = st.number_input(m_name, min_value=0.0, step=0.1, key=f"m_in_{i}")
    free_note = st.text_area("今日頑張ったこと")

    if st.button("今日の成果を報告する", use_container_width=True, type="primary"):
        with st.spinner("分析中..."):
            prompt = f"コーチ「{user_info['coach_name']}」として、達成度{achievement}%、数値{input_vals}、感想「{free_note}」を分析し、100文字でアドバイスを。"
            try: coach_msg = model.generate_content(prompt).text
            except: coach_msg = "素晴らしい努力です！"
            
            # --- 保存先の修正 ---
            # 1. Metricsシート（数値のみ）
            m_rows = [{"user_id": selected_user, "date": today, "metric_name": "達成度", "value": achievement}]
            for k, v in input_vals.items():
                m_rows.append({"user_id": selected_user, "date": today, "metric_name": k, "value": v})
            conn.update(worksheet="Metrics", data=pd.concat([metrics_df, pd.DataFrame(m_rows)]))
            
            # 2. Historyシート（テキスト中心）
            h_rows = [{"user_id": selected_user, "date": today, "coach_comment": coach_msg, "free_text": free_note}]
            conn.update(worksheet="History", data=pd.concat([history_df, pd.DataFrame(h_rows)]))
            
            st.cache_data.clear(); st.balloons(); st.rerun()

# --- 5. 過去の記録表示 ---
else:
    st.subheader(f"📊 {st.session_state.selected_date} の詳細")
    past_m = metrics_df[(metrics_df['user_id'] == selected_user) & (metrics_df['date'] == st.session_state.selected_date)]
    past_h = history_df[(history_df['user_id'] == selected_user) & (history_df['date'] == st.session_state.selected_date)]
    
    if past_m.empty: st.info("記録なし")
    else:
        for _, row in past_m.iterrows():
            st.write(f"✅ **{row['metric_name']}**: {row['value']}")
        if not past_h.empty:
            st.success(f"💡 **コーチ**: {past_h.iloc[0].get('coach_comment', 'なし')}")
            st.info(f"📝 **メモ**: {past_h.iloc[0].get('free_text', 'なし')}")
