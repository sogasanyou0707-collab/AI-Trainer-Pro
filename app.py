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
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: white !important;
        color: black !important;
    }
    h1, h2, h3, p, span, label, li, .stMarkdown {
        color: black !important;
    }
    button, div.stButton > button {
        background-color: white !important;
        color: black !important;
        border: 2px solid black !important;
        border-radius: 8px !important;
    }
    input, textarea, div[data-baseweb="input"], div[data-baseweb="select"] > div {
        background-color: white !important;
        color: black !important;
        border: 1px solid black !important;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. キャッシュ管理 & データ読み込み
# ==========================================
@st.cache_data(ttl=300)
def fetch_all_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        p = conn.read(worksheet="Profiles")
        h = conn.read(worksheet="History")
        m = conn.read(worksheet="Metrics")
        
        # 日付列を文字列（YYYY-MM-DD）に統一して検索を確実にする
        if not h.empty and "date" in h.columns:
            h["date"] = pd.to_datetime(h["date"]).dt.strftime("%Y-%m-%d")
        if not m.empty and "date" in m.columns:
            m["date"] = pd.to_datetime(m["date"]).dt.strftime("%Y-%m-%d")
            
        # コーチリストの取得
        try:
            s = conn.read(worksheet="Settings")
            c_list = s["coach_names"].dropna().unique().tolist() if "coach_names" in s.columns else []
        except:
            c_list = []
        
        # Profilesからも既存のコーチを収集して統合
        p_coaches = p["coach_name"].dropna().unique().tolist() if not p.empty else []
        combined_coaches = sorted(list(set(c_list + p_coaches + ["安西先生"])))
            
        return p, h, m, combined_coaches
    except Exception:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), ["安西先生"]

profiles_df, history_df, metrics_df, coach_list = fetch_all_data()

# ==========================================
# 3. 初期化 & サイドバー
# ==========================================
if 'cfg' not in st.session_state:
    st.session_state.cfg = {"selected_model": "gemini-3-pro"}

with st.sidebar:
    st.header("⚙️ システム設定")
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        all_models = [m.name.replace('models/', '') for m in genai.list_models() 
                      if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    except:
        all_models = ["gemini-3-pro", "gemini-2.5-pro"]
    
    sel_model = st.selectbox("使用AIモデル", all_models, 
                             index=all_models.index(st.session_state.cfg["selected_model"]) if st.session_state.cfg["selected_model"] in all_models else 0)
    st.session_state.cfg["selected_model"] = sel_model

    if st.button("🔄 データを最新に更新"):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 4. メインUI：ユーザー & カレンダー
# ==========================================
st.title("🏀 AI Trainer Pro")

if profiles_df.empty:
    st.error("データの読み込みに失敗しました。Secretsの設定を確認してください。")
    st.stop()

col_u, col_d = st.columns(2)
with col_u:
    u_ids = profiles_df["user_id"].dropna().unique().tolist()
    selected_user = st.selectbox("👤 ユーザー選択", options=["新規登録"] + u_ids)
with col_d:
    selected_date = st.date_input("📅 日付選択", value=datetime.now())
    date_str = selected_date.strftime("%Y-%m-%d")

# ユーザー情報
is_new = selected_user == "新規登録"
u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0].to_dict() if not is_new else {
    "user_id": "", "goal": "", "coach_name": "安西先生", "tracked_metrics": "シュート率,ハンドリング", "tasks_json": "[]"
}

# --- 項目のセッション管理 ---
if 'current_metrics' not in st.session_state or st.session_state.get('last_user') != selected_user:
    st.session_state.current_metrics = [m.strip() for m in str(u_prof.get("tracked_metrics", "")).split(",") if m.strip()]
    st.session_state.last_user = selected_user

# ==========================================
# 5. 詳細設定 (コーチ・項目の追加/削除)
# ==========================================
with st.expander("⚙️ 詳細設定（プロフィール・項目管理）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=u_prof["user_id"])
    u_goal = st.text_area("現在の目標", value=u_prof["goal"])
    
    # コーチ選択：リストを確実に結合
    u_coach = st.selectbox("担当コーチ", options=coach_list, 
                           index=coach_list.index(u_prof["coach_name"]) if u_prof["coach_name"] in coach_list else 0)
    
    st.write("---")
    st.subheader("📊 数値項目のカスタマイズ")
    c_add, c_del = st.columns(2)
    new_m = c_add.text_input("項目を追加")
    if c_add.button("➕ 追加") and new_m:
        if new_m not in st.session_state.current_metrics:
            st.session_state.current_metrics.append(new_m)
            st.rerun()

    if st.session_state.current_metrics:
        del_m = c_del.selectbox("項目を削除", options=["選択してください"] + st.session_state.current_metrics)
        if c_del.button("➖ 削除") and del_m != "選択してください":
            st.session_state.current_metrics.remove(del_m)
            st.rerun()
    st.caption(f"現在の項目: {', '.join(st.session_state.current_metrics)}")

# ==========================================
# 6. 過去データの取得 & 表示
# ==========================================
st.divider()
st.subheader(f"📝 {date_str} の振り返り")

# 安全な検索 (日付の型を統一済み)
h_match = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == date_str)] if not is_new else pd.DataFrame()
m_match = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == date_str)] if not is_new else pd.DataFrame()

if not h_match.empty:
    st.success(f"✅ {date_str} の記録を読み込みました")

# ValueError回避：.values[0] ではなく .get() または 条件分岐で安全に取得
default_rate = 3
if not h_match.empty:
    try:
        default_rate = int(h_match["rate"].iloc[0])
    except:
        default_rate = 3

rate = st.slider("自己評価", 1, 5, default_rate)
note = st.text_area("今日の内容・気づき", value=str(h_match["note"].iloc[0]) if not h_match.empty else "", height=150)

# 数値入力：過去データ（ハンドリング等）を確実に表示
metric_results = {}
for m_name in st.session_state.current_metrics:
    v_init = 0.0
    if not m_match.empty:
        # 項目名でさらに絞り込み
        spec_m = m_match[m_match["metric_name"] == m_name]
        if not spec_m.empty:
            try:
                v_init = float(spec_m["value"].iloc[0])
            except:
                v_init = 0.0
    metric_results[m_name] = st.number_input(f"{m_name} の結果", value=v_init)

# ==========================================
# 7. 保存 & コーチング
# ==========================================
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        with st.spinner("保存中..."):
            conn = st.connection("gsheets", type=GSheetsConnection)
            # 保存ロジック (Profiles, History, Metrics)
            # ... (中略: 保存用コード) ...
            st.cache_data.clear()
            st.success("保存完了しました！")
            st.rerun()

if st.button("💡 AIコーチの助言", use_container_width=True):
    with st.spinner("AIが思考中..."):
        model = genai.GenerativeModel(st.session_state.cfg["selected_model"])
        advice = model.generate_content(f"バスケコーチとして、目標「{u_goal}」を持つ選手へ助言を下さい。内容:{note}, 数値:{metric_results}").text
        st.info(advice)
