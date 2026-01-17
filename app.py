import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import requests
import google.generativeai as genai
from datetime import datetime
import os

# ==========================================
# 1. ページ設定 & デザイン (白基調)
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
@st.cache_data(ttl=300) # 5分キャッシュ
def fetch_all_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        p = conn.read(worksheet="Profiles")
        h = conn.read(worksheet="History")
        m = conn.read(worksheet="Metrics")
        try:
            s = conn.read(worksheet="Settings")
            c_list = s["coach_names"].dropna().tolist() if "coach_names" in s.columns else []
        except:
            c_list = p["coach_name"].dropna().unique().tolist() if not p.empty else []
        return p, h, m, c_list
    except Exception:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), []

profiles_df, history_df, metrics_df, coach_list = fetch_all_data()

# ==========================================
# 3. 初期化 & サイドバー
# ==========================================
if 'cfg' not in st.session_state:
    if os.path.exists("app_settings.json"):
        with open("app_settings.json", "r", encoding="utf-8") as f:
            st.session_state.cfg = json.load(f)
    else:
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
    
    if sel_model != st.session_state.cfg["selected_model"]:
        st.session_state.cfg["selected_model"] = sel_model
        with open("app_settings.json", "w", encoding="utf-8") as f:
            json.dump(st.session_state.cfg, f, indent=4)
        st.rerun()

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
    user_list = profiles_df["user_id"].dropna().unique().tolist()
    selected_user = st.selectbox("👤 ユーザー選択", options=["新規登録"] + user_list)
with col_d:
    selected_date = st.date_input("📅 日付選択", value=datetime.now())
    date_str = selected_date.strftime("%Y-%m-%d")

# ユーザー情報
is_new = selected_user == "新規登録"
if is_new:
    u_prof = {"user_id": "", "goal": "", "coach_name": "", "tracked_metrics": "シュート率,ハンドリング", "tasks_json": "[]"}
else:
    u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0].to_dict()

# --- 計測項目のセッション管理 ---
if 'current_metrics' not in st.session_state or st.session_state.get('last_user') != selected_user:
    st.session_state.current_metrics = [m.strip() for m in str(u_prof.get("tracked_metrics", "")).split(",") if m.strip()]
    st.session_state.last_user = selected_user

# ==========================================
# 5. 詳細設定 (コーチ・項目の追加/削除)
# ==========================================
with st.expander("⚙️ 詳細設定（プロフィール・項目管理）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=u_prof["user_id"])
    u_goal = st.text_area("現在の目標", value=u_prof["goal"])
    
    # コーチ選択の復元
    final_coach_opts = sorted(list(set(coach_list + ([u_prof["coach_name"]] if u_prof["coach_name"] else []))))
    u_coach = st.selectbox("担当コーチ", options=final_coach_opts, 
                           index=final_coach_opts.index(u_prof["coach_name"]) if u_prof["coach_name"] in final_coach_opts else 0)
    
    st.write("---")
    st.subheader("📊 数値項目のカスタマイズ")
    c_add, c_del = st.columns(2)
    new_m = c_add.text_input("項目を追加")
    if c_add.button("➕ 追加") and new_m:
        if new_m not in st.session_state.current_metrics:
            st.session_state.current_metrics.append(new_m)
            st.rerun()

    if st.session_state.current_metrics:
        del_m = c_del.selectbox("項目を削除", options=["選択"] + st.session_state.current_metrics)
        if c_del.button("➖ 削除") and del_m != "選択":
            st.session_state.current_metrics.remove(del_m)
            st.rerun()
    st.caption(f"現在の項目: {', '.join(st.session_state.current_metrics)}")

# ==========================================
# 6. 過去データの取得 & 入力
# ==========================================
st.divider()
st.subheader(f"📝 {date_str} の振り返り")

# 過去の日記・評価の検索
h_match = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == date_str)] if not is_new else pd.DataFrame()
# 過去の数値(Metrics)の検索
m_match = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == date_str)] if not is_new else pd.DataFrame()

if not h_match.empty:
    st.success(f"✅ {date_str} の過去記録を表示しています")

rate = st.slider("自己評価", 1, 5, int(h_match["rate"].values[0]) if not h_match.empty else 3)
note = st.text_area("今日の内容・気づき", value=str(h_match["note"].values[0]) if not h_match.empty else "", height=150)

# 数値入力 (過去データがあれば自動セット)
metric_results = {}
for m_name in st.session_state.current_metrics:
    v_init = 0.0
    if not m_match.empty:
        specific_val = m_match[m_match["metric_name"] == m_name]
        if not specific_val.empty:
            v_init = float(specific_val["value"].values[0])
    metric_results[m_name] = st.number_input(f"{m_name} の結果", value=v_init)

# ==========================================
# 7. 保存 & LINE報告
# ==========================================
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        with st.spinner("保存中..."):
            conn = st.connection("gsheets", type=GSheetsConnection)
            
            # Profiles更新
            new_p = {
                "user_id": u_id, "goal": u_goal, "coach_name": u_coach, 
                "tracked_metrics": ",".join(st.session_state.current_metrics), 
                "tasks_json": u_prof.get("tasks_json", "[]"),
                "line_token": u_prof.get("line_token", ""), "line_user_id": u_prof.get("line_user_id", "")
            }
            p_upd = pd.concat([profiles_df[profiles_df["user_id"] != u_id], pd.DataFrame([new_p])], ignore_index=True)
            conn.update(worksheet="Profiles", data=p_upd)

            # History更新
            h_upd = pd.concat([history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == date_str))], 
                               pd.DataFrame([{"user_id": u_id, "date": date_str, "rate": rate, "note": note}])], ignore_index=True)
            conn.update(worksheet="History", data=h_upd)

            # Metrics更新
            m_rows = [{"user_id": u_id, "date": date_str, "metric_name": k, "value": v} for k, v in metric_results.items()]
            m_upd = pd.concat([metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == date_str))], pd.DataFrame(m_rows)], ignore_index=True)
            conn.update(worksheet="Metrics", data=m_upd)

            st.cache_data.clear()
            st.success("保存完了しました！")
            st.rerun()

if st.button("💡 AIコーチの助言", use_container_width=True):
    with st.spinner("AIが思考中..."):
        model = genai.GenerativeModel(st.session_state.cfg["selected_model"])
        advice = model.generate_content(f"バスケコーチとして、目標「{u_goal}」を持つ選手へ助言を下さい。本日:{note}, 数値:{metric_results}").text
        st.info(advice)
