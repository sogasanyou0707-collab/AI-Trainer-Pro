import streamlit as st

# 強制的に文字色と背景色を指定するCSS
st.markdown("""
    <style>
    /* 全体の背景色と文字色 */
    .stApp {
        background-color: #FFFFFF;
        color: #262730;
    }
    /* 入力ラベル（シュート率やハンドリングなど）の文字色 */
    .stWidgetLabel p {
        color: #262730 !important;
    }
    /* ボタンの文字が見えない場合の対策 */
    div.stButton > button {
        background-color: #4CAF50; /* ボタンの背景色（例：緑） */
        color: white !important;    /* ボタンの文字色 */
    }
    </style>
    """, unsafe_allow_html=True)
import pandas as pd
import datetime
import time
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection

# --- 0. モバイル視認性・完全固定CSS ---
st.set_page_config(page_title="Coach App", layout="centered")

# AI設定
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

st.markdown("""
    <style>
    /* 全体の背景をあえて少し明るいグレーに固定し、文字を黒にする */
    .stApp { background-color: #f0f2f6; color: #111111; }
    
    /* ステータスカード：白背景に黒文字で固定 */
    .status-box { 
        background-color: #ffffff !important; 
        color: #111111 !important; 
        padding: 12px; 
        border-radius: 10px; 
        border-left: 5px solid #ff4b4b; 
        margin-bottom: 10px;
        box-shadow: 0px 2px 4px rgba(0,0,0,0.1);
    }
    .status-box b, .status-box small { color: #111111 !important; }
    
    /* チェックボックス：白背景に黒文字 */
    div[data-testid="stCheckbox"] {
        background-color: #ffffff !important;
        border: 1px solid #dddddd !important;
        padding: 8px 12px !important;
        border-radius: 8px !important;
        margin-bottom: 8px !important;
    }
    div[data-testid="stCheckbox"] label p {
        color: #111111 !important;
        font-weight: bold !important;
    }

    /* カレンダーボタン：背景を白、文字を黒に固定 */
    div[data-testid="stHorizontalBlock"] button {
        background-color: #ffffff !important;
        color: #111111 !important;
        border: 1px solid #cccccc !important;
    }
    /* 選択中のボタンだけ赤枠にする */
    div[data-testid="stHorizontalBlock"] button[kind="primary"] {
        border: 2px solid #ff4b4b !important;
        background-color: #fff0f0 !important;
    }

    /* 横スクロール設定 */
    div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; overflow-x: auto !important; gap: 8px !important; padding: 10px 0; }
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
        p.columns = [c.strip().lower() for c in p.columns]
        m.columns = [c.strip().lower() for c in m.columns]
        h.columns = [c.strip().lower() for c in h.columns]
        if 'date' in m.columns: m['date'] = pd.to_datetime(m['date']).dt.date
        if 'date' in h.columns: h['date'] = pd.to_datetime(h['date']).dt.date
        return p, m, h
    except: return None, None, None

profiles_df, metrics_df, history_df = load_all_data()
if profiles_df is None: st.stop()

# --- 2. ユーザー管理 ＆ 設定（機能復活） ---
st.title("🏀 AI Basketball Coach")

user_list = profiles_df['user_id'].unique().tolist()
selected_user = st.selectbox("👤 ユーザーを選択", user_list)
user_idx = profiles_df[profiles_df['user_id'] == selected_user].index[0]
user_info = profiles_df.loc[user_idx]

with st.expander("⚙️ 設定・新規登録・項目カスタマイズ"):
    tab1, tab2 = st.tabs(["プロフィールと項目設定", "新規ユーザー登録"])
    
    with tab1:
        with st.form("edit_profile"):
            new_coach = st.selectbox("コーチを選択", ["安西コーチ", "熱血コーチ", "冷静コーチ"], 
                                     index=["安西コーチ", "熱血コーチ", "冷静コーチ"].index(user_info.get('coach_name', '安西コーチ')))
            new_goal = st.text_input("目標を更新", value=user_info.get('goal', ''))
            
            # 数値項目の管理
            cur_metrics = user_info.get('tracked_metrics', "ハンドリング")
            if pd.isna(cur_metrics): cur_metrics = "ハンドリング"
            metric_list = [m.strip() for m in cur_metrics.split(",") if m.strip()]
            
            st.write("---")
            st.write("📊 **記録する項目の整理**")
            to_remove = st.multiselect("削除したい項目を選択", metric_list)
            to_add = st.text_input("新しく追加したい項目（例：シュート率）")
            
            if st.form_submit_button("設定を反映して保存"):
                final_metrics = [m for m in metric_list if m not in to_remove]
                if to_add: final_metrics.append(to_add)
                profiles_df.at[user_idx, 'coach_name'] = new_coach
                profiles_df.at[user_idx, 'goal'] = new_goal
                profiles_df.at[user_idx, 'tracked_metrics'] = ",".join(final_metrics)
                conn.update(worksheet="Profiles", data=profiles_df)
                st.cache_data.clear(); st.success("設定を更新しました！"); time.sleep(1); st.rerun()

    with tab2:
        with st.form("new_user"):
            new_id = st.text_input("新規ユーザーID（英数字）")
            new_g = st.text_input("目標")
            if st.form_submit_button("新規ユーザーを作成"):
                if new_id and new_id not in user_list:
                    new_u = pd.DataFrame([{"user_id": new_id, "goal": new_g, "coach_name": "安西コーチ", "tracked_metrics": "ハンドリング"}])
                    conn.update(worksheet="Profiles", data=pd.concat([profiles_df, new_u]))
                    st.cache_data.clear(); st.success("作成しました"); time.sleep(1); st.rerun()

# ステータス表示
c1, c2 = st.columns(2)
with c1: st.markdown(f'<div class="status-box"><small>コーチ</small><br><b>{user_info.get("coach_name", "安西")}</b></div>', unsafe_allow_html=True)
with c2: st.markdown(f'<div class="status-box"><small>目標</small><br><b>{user_info.get("goal", "未設定")}</b></div>', unsafe_allow_html=True)

# --- 3. カレンダー ---
st.divider()
today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(13, -1, -1)]
if "selected_date" not in st.session_state: st.session_state.selected_date = today

cols = st.columns(14)
for i, d in enumerate(date_range):
    day_m = metrics_df[(metrics_df['user_id'] == selected_user) & (metrics_df['date'] == d)]
    achieve = day_m[day_m['metric_name'] == '達成度']
    val = achieve.iloc[0]['value'] if not achieve.empty else 0
    icon = "🔥" if val >= 100 else ("🟡" if val > 0 else "⚪")
    if cols[i].button(f"{d.strftime('%a')}\n{icon}\n{d.day}", key=f"d_{i}", type="primary" if st.session_state.selected_date == d else "secondary"):
        st.session_state.selected_date = d; st.rerun()

# --- 4. 本日のメニュー ＆ 記録 ---
if st.session_state.selected_date == today:
    st.subheader("🗓️ 今日のタスク (AI提案)")
    if "daily_tasks" not in st.session_state or st.session_state.get("task_user") != selected_user:
        with st.spinner("AIがメニューを作成中..."):
            prompt = f"バスケコーチとして目標「{user_info['goal']}」に向けた今日のタスクを4つ厳選。各15文字以内の箇条書き(- 項目名)のみ。"
            try:
                res = model.generate_content(prompt)
                st.session_state.daily_tasks = [t.strip("- ").strip() for t in res.text.split("\n") if t][:4]
            except: st.session_state.daily_tasks = ["ハンドリング", "フリースロー", "体幹", "動画確認"]
            st.session_state.task_user = selected_user

    checks = []
    for i, t in enumerate(st.session_state.daily_tasks):
        checks.append(st.checkbox(t, key=f"t_{i}"))
    
    achievement = int((sum(checks) / 4) * 100)
    st.progress(achievement / 100)

    st.divider()
    st.subheader("📊 数値の記録")
    m_names = [m.strip() for m in user_info.get('tracked_metrics', "ハンドリング").split(",") if m.strip()]
    input_vals = {}
    m_cols = st.columns(len(m_names) if m_names else 1)
    for i, m_name in enumerate(m_names):
        with m_cols[i % len(m_cols)]:
            input_vals[m_name] = st.number_input(m_name, min_value=0.0, step=0.1, key=f"m_in_{i}")
    
    free_note = st.text_area("感想・頑張ったこと")

    if st.button("今日の成果を報告する", use_container_width=True, type="primary"):
        with st.spinner("コーチが分析中..."):
            prompt = f"コーチ「{user_info['coach_name']}」として、達成度{achievement}%、数値{input_vals}、感想「{free_note}」を分析。100文字でアドバイスを。"
            try: coach_msg = model.generate_content(prompt).text
            except: coach_msg = "素晴らしい努力です！"
            
            # Metrics保存（数値）
            m_rows = [{"user_id": selected_user, "date": today, "metric_name": "達成度", "value": achievement}]
            for k, v in input_vals.items():
                m_rows.append({"user_id": selected_user, "date": today, "metric_name": k, "value": v})
            conn.update(worksheet="Metrics", data=pd.concat([metrics_df, pd.DataFrame(m_rows)]))
            
            # History保存（テキスト）
            h_rows = [{"user_id": selected_user, "date": today, "coach_comment": coach_msg, "free_text": free_note}]
            conn.update(worksheet="History", data=pd.concat([history_df, pd.DataFrame(h_rows)]))
            
            st.cache_data.clear(); st.balloons(); st.rerun()

# --- 5. 過去の記録表示 ---
else:
    st.subheader(f"📊 {st.session_state.selected_date} の詳細")
    past_m = metrics_df[(metrics_df['user_id'] == selected_user) & (metrics_df['date'] == st.session_state.selected_date)]
    past_h = history_df[(history_df['user_id'] == selected_user) & (history_df['date'] == st.session_state.selected_date)]
    
    if past_m.empty: st.info("この日の記録はありません。")
    else:
        for _, row in past_m.iterrows():
            st.write(f"✅ **{row['metric_name']}**: {row['value']}")
        if not past_h.empty:
            st.success(f"💡 **コーチ**: {past_h.iloc[0].get('coach_comment', 'なし')}")
            st.info(f"📝 **メモ**: {past_h.iloc[0].get('free_text', 'なし')}")

