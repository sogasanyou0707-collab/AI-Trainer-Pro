import streamlit as st
import pandas as pd
import datetime
import time
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection

# --- 0. 基本設定 & モバイル最適化CSS ---
st.set_page_config(page_title="AI Basketball Coach", layout="centered")

# AI設定 (Secretsから取得)
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

st.markdown("""
    <style>
    .status-box { background-color: #e1e4eb !important; color: #000 !important; padding: 12px; border-radius: 10px; border-left: 5px solid #ff4b4b; margin-bottom: 10px; min-height: 80px; }
    .status-box b { color: #000 !important; font-size: 1.1rem; }
    div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; overflow-x: auto !important; gap: 8px !important; padding-bottom: 10px; }
    div[data-testid="stHorizontalBlock"] > div { min-width: 65px !important; }
    .stCheckbox { background-color: #f0f2f6; padding: 12px; border-radius: 10px; margin-bottom: 8px; border: 1px solid #ddd; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. データ接続・堅牢な読み込み ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=5)
def load_all_data():
    try:
        p = conn.read(worksheet="Profiles")
        m = conn.read(worksheet="Metrics")
        h = conn.read(worksheet="History")
        
        # 列名を「前後の空白削除」「小文字化」して統一
        p.columns = [c.strip().lower() for c in p.columns]
        m.columns = [c.strip().lower() for c in m.columns]
        h.columns = [c.strip().lower() for c in h.columns]
        
        # 日付列を確実に datetime.date 型に変換（これが合わないと表示されません）
        if 'date' in m.columns:
            m['date'] = pd.to_datetime(m['date']).dt.date
        if 'date' in h.columns:
            h['date'] = pd.to_datetime(h['date']).dt.date
            
        return p, m, h
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return None, None, None

profiles_df, metrics_df, history_df = load_all_data()

# --- 2. ユーザー管理 ＆ 初期設定 ---
if profiles_df is None or profiles_df.empty:
    st.warning("Profilesシートが空か、読み込めません。")
    st.stop()

st.title("🏀 AI Basketball Coach")

user_list = profiles_df['user_id'].unique().tolist()
selected_user = st.selectbox("👤 ユーザーを選択", user_list)
user_idx = profiles_df[profiles_df['user_id'] == selected_user].index[0]
user_info = profiles_df.loc[user_idx]

# --- 3. 新規登録 ＆ 設定管理 ---
with st.expander("⚙️ ユーザー管理・設定"):
    t1, t2 = st.tabs(["プロフィール編集", "新規ユーザー作成"])
    with t1:
        with st.form("edit"):
            n_coach = st.selectbox("コーチ", ["安西コーチ", "熱血コーチ", "冷静コーチ"], 
                                   index=["安西コーチ", "熱血コーチ", "冷静コーチ"].index(user_info.get('coach_name', '安西コーチ')))
            n_goal = st.text_input("今の目標", value=user_info.get('goal', ''))
            cur_metrics = user_info.get('tracked_metrics', "ハンドリング")
            if pd.isna(cur_metrics): cur_metrics = "ハンドリング"
            m_list = [m.strip() for m in cur_metrics.split(",") if m.strip()]
            to_del = st.multiselect("削除する項目", m_list)
            to_add = st.text_input("追加する項目（例：シュート成功率）")
            if st.form_submit_button("保存"):
                final = [m for m in m_list if m not in to_del]
                if to_add: final.append(to_add)
                profiles_df.at[user_idx, 'coach_name'] = n_coach
                profiles_df.at[user_idx, 'goal'] = n_goal
                profiles_df.at[user_idx, 'tracked_metrics'] = ",".join(final)
                conn.update(worksheet="Profiles", data=profiles_df)
                st.cache_data.clear(); st.rerun()
    with t2:
        with st.form("new"):
            uid = st.text_input("新規ID"); goal = st.text_input("目標")
            if st.form_submit_button("登録"):
                if uid and uid not in user_list:
                    new_u = pd.DataFrame([{"user_id": uid, "goal": goal, "coach_name": "安西コーチ", "tracked_metrics": "ハンドリング"}])
                    conn.update(worksheet="Profiles", data=pd.concat([profiles_df, new_u]))
                    st.cache_data.clear(); st.rerun()

# ステータス表示
c1, c2 = st.columns(2)
with c1: st.markdown(f'<div class="status-box"><small>コーチ</small><br><b>{user_info.get("coach_name", "安西")}</b></div>', unsafe_allow_html=True)
with c2: st.markdown(f'<div class="status-box"><small>今の目標</small><br><b>{user_info.get("goal", "未設定")}</b></div>', unsafe_allow_html=True)

st.divider()

# --- 4. 過去データの表示（カレンダー連動） ---
st.subheader("🗓️ 週間進捗")
today = datetime.date.today()
date_range = [(today - datetime.timedelta(days=i)) for i in range(13, -1, -1)]

if "selected_date" not in st.session_state: st.session_state.selected_date = today

cols = st.columns(14)
for i, d in enumerate(date_range):
    # 過去データの達成度を参照
    day_metrics = metrics_df[(metrics_df['user_id'] == selected_user) & (metrics_df['date'] == d)]
    achieve = day_metrics[day_metrics['metric_name'] == '達成度']
    val = achieve.iloc[0]['value'] if not achieve.empty else 0
    icon = "🔥" if val >= 100 else ("🟡" if val > 0 else "⚪")
    
    if cols[i].button(f"{d.strftime('%a')}\n{icon}\n{d.day}", key=f"d_{i}", 
                       type="primary" if st.session_state.selected_date == d else "secondary"):
        st.session_state.selected_date = d; st.rerun()

# --- 5. 本日のAIメニュー（タスク提示） ---
# 選択日が「今日」の場合のみ、入力画面を表示
if st.session_state.selected_date == today:
    st.subheader("🗓️ 今日のメニュー")
    
    def generate_tasks(coach, goal):
        prompt = f"バスケコーチ「{coach}」として、目標「{goal}」に向けた今日のタスクを4つ厳選して。15文字以内の箇条書きだけで回答して。"
        try:
            res = model.generate_content(prompt)
            return [t.strip("- ").strip() for t in res.text.split("\n") if t][:4]
        except: return ["ハンドリング10分", "フリースロー20本", "体幹トレーニング", "NBA動画分析"]

    if "daily_tasks" not in st.session_state or st.session_state.get("task_user") != selected_user:
        st.session_state.daily_tasks = generate_tasks(user_info['coach_name'], user_info['goal'])
        st.session_state.task_user = selected_user

    checks = []
    for i, t in enumerate(st.session_state.daily_tasks):
        checks.append(st.checkbox(t, key=f"t_{i}"))
    
    achievement = int((sum(checks) / 4) * 100)
    st.progress(achievement / 100)
    st.write(f"現在の達成度: **{achievement}%**")

    st.divider()
    st.subheader("📊 今日の記録")
    m_names = [m.strip() for m in user_info.get('tracked_metrics', "ハンドリング").split(",") if m.strip()]
    input_vals = {}
    m_cols = st.columns(len(m_names) if m_names else 1)
    for i, m_name in enumerate(m_names):
        with m_cols[i % len(m_cols)]:
            input_vals[m_name] = st.number_input(m_name, min_value=0.0, step=0.1, key=f"m_in_{i}")
    free_note = st.text_area("今日頑張ったこと", placeholder="具体的に書くとコーチが喜びます")

    if st.button("今日の成果を報告する", use_container_width=True, type="primary"):
        with st.spinner("コーチが分析中..."):
            # AIフィードバック
            prompt = f"コーチ「{user_info['coach_name']}」として、今日の達成度{achievement}%、数値{input_vals}、感想「{free_note}」を分析し、目標に向けたアドバイスを100文字で。"
            try: coach_msg = model.generate_content(prompt).text
            except: coach_msg = "素晴らしい努力です！"
            
            # データ一括保存
            new_rows = [{"user_id": selected_user, "date": today, "metric_name": "達成度", "value": achievement}]
            for k, v in input_vals.items():
                new_rows.append({"user_id": selected_user, "date": today, "metric_name": k, "value": v})
            
            conn.update(worksheet="Metrics", data=pd.concat([metrics_df, pd.DataFrame(new_rows)]))
            new_h = pd.DataFrame([{"user_id": selected_user, "date": today, "metric_name": "総合", "value": achievement, "coach_comment": coach_msg, "free_text": free_note}])
            conn.update(worksheet="History", data=pd.concat([history_df, new_h]))
            
            st.cache_data.clear(); st.balloons(); st.rerun()

# --- 6. 過去の記録表示セクション ---
else:
    st.subheader(f"📊 {st.session_state.selected_date} の振り返り")
    past_m = metrics_df[(metrics_df['user_id'] == selected_user) & (metrics_df['date'] == st.session_state.selected_date)]
    past_h = history_df[(history_df['user_id'] == selected_user) & (history_df['date'] == st.session_state.selected_date)]
    
    if past_m.empty:
        st.info("この日の記録はありません。")
    else:
        for _, row in past_m.iterrows():
            st.write(f"✅ **{row['metric_name']}**: {row['value']}")
        if not past_h.empty:
            st.success(f"💡 **コーチの言葉**:\n{past_h.iloc[0]['coach_comment']}")
            if not pd.isna(past_h.iloc[0]['free_text']):
                st.info(f"📝 **自分のメモ**: {past_h.iloc[0]['free_text']}")
