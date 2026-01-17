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
# 2. データ読み込み (B列:date, C列:name, D列:value)
# ==========================================
@st.cache_data(ttl=300)
def fetch_master_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        p = conn.read(worksheet="Profiles")
        h = conn.read(worksheet="History")
        m = conn.read(worksheet="Metrics")
        
        # 日付標準化
        for df in [h, m]:
            if not df.empty and "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        
        # コーチタイプ定義
        coach_types = ["安西先生", "熱血タイプ", "論理タイプ"]
        
        return p, h, m, coach_types
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), ["安西先生", "熱血タイプ", "論理タイプ"]

profiles_df, history_df, metrics_df, coach_list = fetch_master_data()

# ==========================================
# 3. AIコーチング・ロジック (性格反映)
# ==========================================
def get_ai_coach_advice(coach_type, goal, note, metrics, model_name):
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel(model_name)
    
    # コーチ別の性格設定
    personalities = {
        "安西先生": "穏やかで、選手の可能性を信じ、短くも核心を突く励ましを与えてください。有名なフレーズ『諦めたらそこで試合終了』の精神を大切にしてください。",
        "熱血タイプ": "非常にエネルギッシュで、情熱的な言葉遣いをしてください。努力と根性を称賛し、大きな声（感嘆符多め）で鼓舞してください。",
        "論理タイプ": "冷静かつ分析的です。感情論ではなく、数値データに基づいた具体的な改善案や、効率的な練習メニューを論理的に提案してください。"
    }
    
    prompt = f"""
    あなたはバスケットボールのコーチです。性格設定：{personalities.get(coach_type, "")}
    
    【選手の目標】: {goal}
    【本日の報告】: {note}
    【本日の計測数値】: {metrics}
    
    上記を踏まえ、選手に3つのアドバイスを提供してください。
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"コーチング生成エラー: {e}"

# ==========================================
# 4. メインUI
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

# ユーザー情報の特定
is_new = selected_user == "新規登録"
u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0].to_dict() if not is_new else {
    "user_id": "", "goal": "", "coach_name": "安西先生", "tracked_metrics": "シュート率,ハンドリング"
}

# 項目のセッション管理
if 'current_metrics' not in st.session_state or st.session_state.get('last_user') != selected_user:
    st.session_state.current_metrics = [m.strip() for m in str(u_prof.get("tracked_metrics", "")).split(",") if m.strip()]
    st.session_state.last_user = selected_user

# ==========================================
# 5. 詳細設定 (プロフィール・コーチ・項目管理)
# ==========================================
with st.expander("⚙️ 詳細設定（プロフィール・項目管理）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=u_prof["user_id"])
    u_goal = st.text_area("現在の目標", value=u_prof["goal"])
    
    # コーチ選択 (安西先生、熱血タイプ、論理タイプ)
    u_coach = st.selectbox("コーチのタイプ", options=coach_list, 
                           index=coach_list.index(u_prof["coach_name"]) if u_prof["coach_name"] in coach_list else 0)
    
    st.divider()
    st.subheader("📊 数値項目のカスタマイズ")
    c_add, c_del = st.columns(2)
    new_m = c_add.text_input("項目を新規追加")
    if c_add.button("➕ 追加") and new_m:
        if new_m not in st.session_state.current_metrics:
            st.session_state.current_metrics.append(new_m)
            st.rerun()

    if st.session_state.current_metrics:
        del_m = c_del.selectbox("項目を削除", options=["選択してください"] + st.session_state.current_metrics)
        if c_del.button("➖ 削除") and del_m != "選択してください":
            st.session_state.current_metrics.remove(del_m)
            st.rerun()

# ==========================================
# 6. 過去データの取得 & 入力
# ==========================================
st.divider()
st.subheader(f"📝 {date_str} の振り返り")

# 過去データの検索 (History: B列date / Metrics: B列date)
h_match = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == date_str)] if not is_new else pd.DataFrame()
m_match = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == date_str)] if not is_new else pd.DataFrame()

if not h_match.empty:
    st.success(f"✅ {date_str} の記録を読み込みました")

user_rate = st.slider("自己評価", 1, 5, int(h_match["rate"].iloc[0]) if not h_match.empty else 3)
user_note = st.text_area("内容・気づき", value=str(h_match["note"].iloc[0]) if not h_match.empty else "", height=150)

# 数値入力 (Metricsシート C列:metric_name, D列:value を反映)
res_metrics = {}
for m_name in st.session_state.current_metrics:
    v_init = 0.0
    if not m_match.empty:
        # C列(metric_name)で合致する行のD列(value)を取得
        spec_m = m_match[m_match["metric_name"] == m_name]
        if not spec_m.empty:
            v_init = float(spec_m["value"].iloc[0])
    res_metrics[m_name] = st.number_input(f"{m_name} の結果", value=v_init)

# ==========================================
# 7. アクションボタン
# ==========================================
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        with st.spinner("スプレッドシートを更新中..."):
            conn = st.connection("gsheets", type=GSheetsConnection)
            
            # 1. Profiles更新
            new_p = {
                "user_id": u_id, "goal": u_goal, "coach_name": u_coach, 
                "tracked_metrics": ",".join(st.session_state.current_metrics)
            }
            p_upd = pd.concat([profiles_df[profiles_df["user_id"] != u_id], pd.DataFrame([new_p])], ignore_index=True)
            conn.update(worksheet="Profiles", data=p_upd)

            # 2. History更新
            h_upd = pd.concat([history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == date_str))], 
                               pd.DataFrame([{"user_id": u_id, "date": date_str, "rate": user_rate, "note": user_note}])], ignore_index=True)
            conn.update(worksheet="History", data=h_upd)

            # 3. Metrics更新 (B列:date, C列:metric_name, D列:value)
            m_new = [{"user_id": u_id, "date": date_str, "metric_name": k, "value": v} for k, v in res_metrics.items()]
            m_upd = pd.concat([metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == date_str))], pd.DataFrame(m_new)], ignore_index=True)
            conn.update(worksheet="Metrics", data=m_upd)

            st.cache_data.clear()
            st.success("全てのデータを保存しました！")
            st.rerun()

if st.button("💡 AIコーチの助言を受ける", use_container_width=True):
    with st.spinner(f"{u_coach}が思考中..."):
        advice = get_ai_coach_advice(u_coach, u_goal, user_note, res_metrics, st.session_state.cfg["selected_model"])
        st.markdown(f"### 🤖 {u_coach}からのアドバイス")
        st.info(advice)

# サイドバー (モデル選択)
with st.sidebar:
    st.header("⚙️ システム")
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    all_models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    st.session_state.cfg["selected_model"] = st.selectbox("使用AIモデル", all_models, index=0)
