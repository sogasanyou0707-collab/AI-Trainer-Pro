import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import requests
import google.generativeai as genai
from datetime import datetime
import os

# ==========================================
# 1. ページ設定 & デザイン
# ==========================================
st.set_page_config(page_title="AI Trainer Pro", layout="centered")

st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"] { background-color: white !important; color: black !important; }
    h1, h2, h3, p, label, .stMarkdown { color: black !important; }
    button, div.stButton > button { background-color: white !important; color: black !important; border: 2px solid black !important; border-radius: 8px !important; }
    input, textarea, div[data-baseweb="input"] { background-color: white !important; color: black !important; border: 1px solid black !important; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. データの取得と整形
# ==========================================
@st.cache_data(ttl=300)
def fetch_master_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        p = conn.read(worksheet="Profiles")
        h = conn.read(worksheet="History")
        m = conn.read(worksheet="Metrics")
        
        # 日付を "YYYY-MM-DD" の文字列に統一して検索漏れを防ぐ
        for df in [h, m]:
            if not df.empty and "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        
        coach_types = ["安西先生", "熱血タイプ", "論理タイプ"]
        return p, h, m, coach_types
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), ["安西先生", "熱血タイプ", "論理タイプ"]

profiles_df, history_df, metrics_df, coach_list = fetch_master_data()

# ==========================================
# 3. AIコーチングの指示（プロンプト）
# ==========================================
def get_ai_coach_advice(coach_type, goal, note, metrics, model_name):
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel(model_name)
    
    personalities = {
        "安西先生": "穏やかで、『諦めたらそこで試合終了』の精神。短い言葉で核心を突き、選手の可能性を信じる。武里戦、陵南戦の時のような包容力を。",
        "熱血タイプ": "修造のような熱さ。根性と努力を最大限に褒め、感嘆符を多用してやる気を引き出す。",
        "論理タイプ": "NBAのアナリストのように分析的。具体的な成功率の推移や効率的なトレーニングメニューを淡々と論じる。"
    }
    
    prompt = f"コーチ性格：{personalities.get(coach_type, '')}\n目標：{goal}\n報告：{note}\n数値：{metrics}\n上記を踏まえ、3点アドバイスして。"
    try:
        return model.generate_content(prompt).text
    except:
        return "コーチが少し考え込んでいます。もう一度送信してください。"

# ==========================================
# 4. メインUI：ユーザーとカレンダー
# ==========================================
if 'cfg' not in st.session_state:
    st.session_state.cfg = {"selected_model": "gemini-3-pro"}

st.title("🏀 AI Trainer Pro")

col_u, col_d = st.columns(2)
with col_u:
    u_ids = profiles_df["user_id"].dropna().unique().tolist() if not profiles_df.empty else []
    selected_user = st.selectbox("👤 ユーザー", options=["新規登録"] + u_ids)
with col_d:
    selected_date = st.date_input("📅 日付", value=datetime.now())
    date_str = selected_date.strftime("%Y-%m-%d")

is_new = selected_user == "新規登録"
u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0].to_dict() if not is_new else {
    "user_id": "", "goal": "", "coach_name": "安西先生", "tracked_metrics": "シュート率,ハンドリング"
}

# 項目管理
if 'current_metrics' not in st.session_state or st.session_state.get('last_user') != selected_user:
    st.session_state.current_metrics = [m.strip() for m in str(u_prof.get("tracked_metrics", "")).split(",") if m.strip()]
    st.session_state.last_user = selected_user

# ==========================================
# 5. 詳細設定（プロフィール）
# ==========================================
with st.expander("⚙️ 詳細設定（項目・コーチ設定）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=u_prof["user_id"])
    u_goal = st.text_area("目標", value=u_prof["goal"])
    u_coach = st.selectbox("コーチタイプ", options=coach_list, 
                           index=coach_list.index(u_prof["coach_name"]) if u_prof["coach_name"] in coach_list else 0)
    
    st.divider()
    c_add, c_del = st.columns(2)
    new_m = c_add.text_input("項目追加")
    if c_add.button("追加") and new_m:
        if new_m not in st.session_state.current_metrics:
            st.session_state.current_metrics.append(new_m)
            st.rerun()
    if st.session_state.current_metrics:
        del_m = c_del.selectbox("項目削除", options=["選択"] + st.session_state.current_metrics)
        if c_del.button("削除") and del_m != "選択":
            st.session_state.current_metrics.remove(del_m)
            st.rerun()

# ==========================================
# 6. 過去データの取得と表示（エラー防止策）
# ==========================================
st.divider()
st.subheader(f"📝 {date_str} の振り返り")

h_match = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == date_str)] if not is_new else pd.DataFrame()
m_match = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == date_str)] if not is_new else pd.DataFrame()

# 過去の自己評価を安全に取得
def get_safe_rate(df):
    if not df.empty and pd.notna(df["rate"].iloc[0]):
        try:
            return int(float(df["rate"].iloc[0]))
        except:
            return 3
    return 3

rate = st.slider("自己評価", 1, 5, get_safe_rate(h_match))
note = st.text_area("内容", value=str(h_match["note"].iloc[0]) if not h_match.empty else "")

# --- Metrics反映ロジック ---
res_metrics = {}
for m_name in st.session_state.current_metrics:
    v_init = 0.0
    if not m_match.empty:
        # C列(metric_name)で一致する行を探す
        spec_m = m_match[m_match["metric_name"] == m_name]
        if not spec_m.empty and pd.notna(spec_m["value"].iloc[0]):
            try:
                v_init = float(spec_m["value"].iloc[0])
            except:
                v_init = 0.0
    res_metrics[m_name] = st.number_input(f"{m_name} の結果", value=v_init)

# ==========================================
# 7. 保存・AIコーチ
# ==========================================
if st.button("💾 記録を保存", use_container_width=True):
    if not u_id:
        st.error("IDを入力してください")
    else:
        conn = st.connection("gsheets", type=GSheetsConnection)
        p_upd = pd.concat([profiles_df[profiles_df["user_id"] != u_id], 
                          pd.DataFrame([{"user_id": u_id, "goal": u_goal, "coach_name": u_coach, "tracked_metrics": ",".join(st.session_state.current_metrics)}])], ignore_index=True)
        h_upd = pd.concat([history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == date_str))], 
                          pd.DataFrame([{"user_id": u_id, "date": date_str, "rate": rate, "note": note}])], ignore_index=True)
        m_new_list = [{"user_id": u_id, "date": date_str, "metric_name": k, "value": v} for k, v in res_metrics.items()]
        m_upd = pd.concat([metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == date_str))], pd.DataFrame(m_new_list)], ignore_index=True)
        
        conn.update(worksheet="Profiles", data=p_upd)
        conn.update(worksheet="History", data=h_upd)
        conn.update(worksheet="Metrics", data=m_upd)
        st.cache_data.clear()
        st.success("保存完了")
        st.rerun()

if st.button("💡 コーチに相談する", use_container_width=True):
    with st.spinner(f"{u_coach}が考え中..."):
        advice = get_ai_coach_advice(u_coach, u_goal, note, res_metrics, st.session_state.cfg["selected_model"])
        st.info(advice)

with st.sidebar:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    st.session_state.cfg["selected_model"] = st.selectbox("AIモデル", models, index=0)
