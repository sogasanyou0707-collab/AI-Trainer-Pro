import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import requests
import google.generativeai as genai
from datetime import datetime
import os

# ==========================================
# 1. ページ設定 & デザイン (視認性改善)
# ==========================================
st.set_page_config(page_title="AI Trainer Pro", layout="centered")

st.markdown("""
    <style>
    /* 全体の白基調 */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: white !important; color: black !important;
    }
    h1, h2, h3, p, span, label, li, .stMarkdown { color: black !important; }
    
    /* ボタンデザイン */
    button, div.stButton > button { 
        background-color: white !important; color: black !important; 
        border: 2px solid black !important; border-radius: 8px !important; 
    }
    
    /* 入力エリア */
    input, textarea, div[data-baseweb="input"] { 
        background-color: white !important; color: black !important; border: 1px solid black !important; 
    }

    /* 【視認性改善】プルダウン(Selectbox)の文字と背景色を強制固定 */
    div[data-baseweb="select"] > div {
        background-color: white !important;
        color: black !important;
        border: 1px solid black !important;
    }
    div[data-testid="stSelectbox"] label { color: black !important; }
    
    /* プログレスバーの色 */
    .stProgress > div > div > div > div { background-color: #000000 !important; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 接続 & データ読み込み (現在の安定仕様を維持)
# ==========================================
@st.cache_data(ttl=5)
def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        p = conn.read(worksheet="Profiles", ttl=0)
        h = conn.read(worksheet="History", ttl=0)
        m = conn.read(worksheet="Metrics", ttl=0)
        
        for df in [h, m]:
            if not df.empty and "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        
        for df in [p, h, m]:
            if not df.empty:
                for col in df.columns:
                    if df[col].dtype == 'object':
                        df[col] = df[col].astype(str).str.strip()
        return p, h, m
    except Exception as e:
        st.error(f"データ読み込み失敗: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

profiles_df, history_df, metrics_df = load_data()

# ==========================================
# 3. メインUI：ユーザー & カレンダー
# ==========================================
st.title("🏀 AI Trainer Pro")

col_u, col_d = st.columns(2)
with col_u:
    u_list = profiles_df["user_id"].dropna().unique().tolist() if not profiles_df.empty else []
    selected_user = st.selectbox("👤 ユーザー選択", options=["新規登録"] + u_list)
with col_d:
    selected_date = st.date_input("📅 記録日", value=datetime.now())
    target_date_str = selected_date.strftime("%Y-%m-%d")

is_new = selected_user == "新規登録"
u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0] if not is_new and not profiles_df.empty else pd.Series()

# 過去データ検索
existing_history = pd.Series()
existing_metrics = pd.DataFrame()
if not is_new:
    if not history_df.empty:
        h_match = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == target_date_str)]
        if not h_match.empty: existing_history = h_match.iloc[-1]
    if not metrics_df.empty:
        existing_metrics = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == target_date_str)]

# ==========================================
# 4. 詳細設定 (項目追加と削除を分離表示)
# ==========================================
with st.expander("⚙️ 詳細設定（プロフィール・項目管理）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=str(u_prof.get("user_id", "")))
    u_goal = st.text_area("目標", value=str(u_prof.get("goal", "")))
    u_coach = st.selectbox("コーチ", options=["安西先生", "熱血タイプ", "論理タイプ"], 
                           index=["安西先生", "熱血タイプ", "論理タイプ"].index(u_prof.get("coach_name")) if u_prof.get("coach_name") in ["安西先生", "熱血タイプ", "論理タイプ"] else 0)

    # 現在の項目リスト取得
    if 'current_m' not in st.session_state or st.session_state.get('last_u') != selected_user:
        st.session_state.current_m = [m.strip() for m in str(u_prof.get("tracked_metrics", "シュート率,ハンドリング")).split(",") if m.strip()]
        st.session_state.last_u = selected_user

    st.divider()
    st.subheader("➕ 数値項目の追加")
    new_m = st.text_input("追加したい新しい項目名を入力", key="add_metric_input")
    if st.button("この項目を追加する"):
        if new_m and new_m not in st.session_state.current_m:
            st.session_state.current_m.append(new_m)
            st.success(f"「{new_m}」を追加しました。保存すると確定します。")
            st.rerun()

    st.divider()
    st.subheader("➖ 数値項目の削除")
    if st.session_state.current_m:
        del_m = st.selectbox("削除する項目を選択してください", options=["選択してください"] + st.session_state.current_m, key="del_metric_select")
        if st.button("この項目を削除する"):
            if del_m != "選択してください":
                st.session_state.current_m.remove(del_m)
                st.warning(f"「{del_m}」をリストから外しました。保存すると確定します。")
                st.rerun()

# ==========================================
# 5. 【新規】今日の練習タスク & 達成率
# ==========================================
st.divider()
st.subheader("📋 本日の練習メニュー")

# 固定タスク（将来的にスプレッドシート管理も可能）
task_list = ["シュート練習 50本", "ハンドリング 10分", "フットワーク", "対人練習"]
done_count = 0

t_col1, t_col2 = st.columns([2, 1])
with t_col1:
    for i, task in enumerate(task_list):
        if st.checkbox(task, key=f"task_{i}"):
            done_count += 1

with t_col2:
    achievement_rate = int((done_count / len(task_list)) * 100)
    st.metric("達成率", f"{achievement_rate}%")
    st.progress(achievement_rate / 100)

# ==========================================
# 6. 振り返り入力 (ハンドリング数値の反映)
# ==========================================
st.divider()
st.subheader(f"📝 {target_date_str} の振り返り")

try: def_rate = int(float(existing_history.get("rate", 3)))
except: def_rate = 3
rate = st.slider("自己評価", 1, 5, def_rate)
note = st.text_area("練習内容・気づき", value=str(existing_history.get("note", "")), height=150)

# 数値の自動反映ロジック
metric_inputs = {}
for m_name in st.session_state.current_m:
    prev_val = 0.0
    if not existing_metrics.empty:
        m_match = existing_metrics[existing_metrics["metric_name"] == m_name]
        if not m_match.empty:
            try: prev_val = float(m_match.iloc[-1]["value"])
            except: prev_val = 0.0
    metric_inputs[m_name] = st.number_input(f"{m_name} の結果", value=prev_val, key=f"val_{m_name}")

# ==========================================
# 7. 保存 & LINE報告 (データ保護維持)
# ==========================================
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        with st.spinner("処理中..."):
            conn = st.connection("gsheets", type=GSheetsConnection)
            
            # Profiles更新 (E/F列保護)
            p_latest = conn.read(worksheet="Profiles", ttl=0)
            new_p_data = {
                "user_id": u_id, "goal": u_goal, "coach_name": u_coach, 
                "tracked_metrics": ",".join(st.session_state.current_m)
            }
            if u_id in p_latest["user_id"].astype(str).values:
                idx = p_latest[p_latest["user_id"].astype(str) == u_id].index[0]
                for key, val in new_p_data.items(): p_latest.at[idx, key] = val
                final_p = p_latest
            else:
                final_p = pd.concat([p_latest, pd.DataFrame([new_p_data])], ignore_index=True)

            # History & Metrics 更新
            h_upd = pd.concat([history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == target_date_str))], 
                               pd.DataFrame([{"user_id": u_id, "date": target_date_str, "rate": rate, "note": note}])], ignore_index=True)
            m_rows = [{"user_id": u_id, "date": target_date_str, "metric_name": k, "value": v} for k, v in metric_inputs.items()]
            m_upd = pd.concat([metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == target_date_str))], pd.DataFrame(m_rows)], ignore_index=True)

            # 書き込み
            conn.update(worksheet="Profiles", data=final_p)
            conn.update(worksheet="History", data=h_upd)
            conn.update(worksheet="Metrics", data=m_upd)

            # LINE送信
            target_user = final_p[final_p["user_id"] == u_id].iloc[0]
            l_token = target_user.get("line_token")
            l_id = target_user.get("line_user_id")
            if l_token and l_id and str(l_token) != "nan":
                m_txt = "\n".join([f"・{k}: {v}" for k, v in metric_inputs.items()])
                line_msg = f"【AI報告】{target_date_str}\n達成率: {achievement_rate}%\n評価: {int(rate)}\n内容: {str(note)}\n\n[数値]\n{m_txt}"
                payload = {"to": str(l_id), "messages": [{"type": "text", "text": line_msg}]}
                headers = {"Authorization": f"Bearer {l_token}", "Content-Type": "application/json"}
                requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
            
            st.cache_data.clear()
            st.success("全てのデータを保存しました！")
            st.rerun()

# --- AIコーチ ---
if st.button("💡 コーチのアドバイスを受ける", use_container_width=True):
    with st.spinner("分析中..."):
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel(st.session_state.get("sel_model", "gemini-3-pro"))
        prompt = f"コーチ:{u_coach}, 目標:{u_goal}, 内容:{note}, 数値:{metric_inputs}, 達成率:{achievement_rate}%"
        st.info(model.generate_content(prompt).text)

with st.sidebar:
    st.header("⚙️ Setting")
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    ms = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    st.session_state.sel_model = st.selectbox("AI Model", ms, index=0)
