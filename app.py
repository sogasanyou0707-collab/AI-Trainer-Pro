import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import requests
import google.generativeai as genai
from datetime import datetime
import os

# ==========================================
# 1. ページ設定 & デザイン (白基調・モバイル対応)
# ==========================================
st.set_page_config(page_title="AI Trainer Pro", layout="centered")

st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: white !important; color: black !important;
    }
    h1, h2, h3, p, span, label, li, .stMarkdown { color: black !important; }
    button, div.stButton > button { 
        background-color: white !important; color: black !important; 
        border: 2px solid black !important; border-radius: 8px !important; 
    }
    input, textarea, div[data-baseweb="input"] { 
        background-color: white !important; color: black !important; border: 1px solid black !important; 
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. データ読み込み (ご提示のロジックをベースに強化)
# ==========================================
@st.cache_data(ttl=5)
def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        p = conn.read(worksheet="Profiles", ttl=0)
        h = conn.read(worksheet="History", ttl=0)
        m = conn.read(worksheet="Metrics", ttl=0)
        
        # 日付の型を YYYY-MM-DD 文字列に完全統一
        for df in [h, m]:
            if not df.empty and "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        
        # 文字列の空白をトリミング
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

# --- 過去データの検索 (ご提示のロジックを100%継承) ---
existing_history = pd.Series()
existing_metrics = pd.DataFrame()
if not is_new:
    if not history_df.empty:
        h_match = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == target_date_str)]
        if not h_match.empty: existing_history = h_match.iloc[-1]
    if not metrics_df.empty:
        existing_metrics = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == target_date_str)]

# ==========================================
# 4. 詳細設定 (Profilesの全列を保護する仕組み)
# ==========================================
with st.expander("⚙️ 詳細設定（プロフィール・項目管理）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=str(u_prof.get("user_id", "")))
    u_goal = st.text_area("目標", value=str(u_prof.get("goal", "")))
    
    coach_opts = ["安西先生", "熱血タイプ", "論理タイプ"]
    u_coach = st.selectbox("コーチ", options=coach_opts, 
                           index=coach_opts.index(u_prof.get("coach_name")) if u_prof.get("coach_name") in coach_opts else 0)

    # 数値項目の管理 (追加：フリー入力、削除：プルダウン)
    if 'current_m' not in st.session_state or st.session_state.get('last_u') != selected_user:
        st.session_state.current_m = [m.strip() for m in str(u_prof.get("tracked_metrics", "シュート率,ハンドリング")).split(",") if m.strip()]
        st.session_state.last_u = selected_user

    c_add, c_del = st.columns(2)
    new_m = c_add.text_input("追加項目名")
    if c_add.button("➕ 追加"):
        if new_m and new_m not in st.session_state.current_m:
            st.session_state.current_m.append(new_m)
            st.rerun()

    if st.session_state.current_m:
        del_m = c_del.selectbox("削除項目を選択", options=["選択"] + st.session_state.current_m)
        if c_del.button("➖ 削除") and del_m != "選択":
            st.session_state.current_m.remove(del_m)
            st.rerun()

# ==========================================
# 5. 振り返り入力 (ハンドリング数値の反映)
# ==========================================
st.divider()
st.subheader(f"📝 {target_date_str} の振り返り")

try:
    def_rate = int(float(existing_history.get("rate", 3)))
except: def_rate = 3
rate = st.slider("自己評価", 1, 5, def_rate)
note = st.text_area("練習内容・気づき", value=str(existing_history.get("note", "")), height=150)

# --- ハンドリング等数値の自動反映ロジック ---
metric_inputs = {}
for m_name in st.session_state.current_m:
    prev_val = 0.0
    if not existing_metrics.empty:
        # ご提示いただいた成功時の検索ロジックを適用
        m_match = existing_metrics[existing_metrics["metric_name"] == m_name]
        if not m_match.empty:
            try: prev_val = float(m_match.iloc[-1]["value"])
            except: prev_val = 0.0
    metric_inputs[m_name] = st.number_input(f"{m_name} の結果", value=prev_val, key=f"val_{m_name}")

# ==========================================
# 6. 保存 & LINE送信 (データの完全保護)
# ==========================================
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        with st.spinner("処理中..."):
            conn = st.connection("gsheets", type=GSheetsConnection)
            
            # --- A. Profiles更新 (既存の列を絶対に消さないロジック) ---
            p_latest = conn.read(worksheet="Profiles", ttl=0)
            if u_id in p_latest["user_id"].astype(str).values:
                # 既存ユーザーの行を特定し、UIで編集した箇所だけ書き換える
                idx = p_latest[p_latest["user_id"].astype(str) == u_id].index[0]
                p_latest.at[idx, "goal"] = u_goal
                p_latest.at[idx, "coach_name"] = u_coach
                p_latest.at[idx, "tracked_metrics"] = ",".join(st.session_state.current_m)
                final_p = p_latest
            else:
                # 新規ユーザーの追加
                new_p = pd.DataFrame([{"user_id": u_id, "goal": u_goal, "coach_name": u_coach, "tracked_metrics": ",".join(st.session_state.current_m)}])
                final_p = pd.concat([p_latest, new_p], ignore_index=True)

            # B. History & Metrics
            h_clean = history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == target_date_str))]
            h_upd = pd.concat([h_clean, pd.DataFrame([{"user_id": u_id, "date": target_date_str, "rate": rate, "note": note}])], ignore_index=True)
            
            m_clean = metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == target_date_str))]
            m_rows = [{"user_id": u_id, "date": target_date_str, "metric_name": k, "value": v} for k, v in metric_inputs.items()]
            m_upd = pd.concat([m_clean, pd.DataFrame(m_rows)], ignore_index=True)

            # 保存実行
            conn.update(worksheet="Profiles", data=final_p)
            conn.update(worksheet="History", data=h_upd)
            conn.update(worksheet="Metrics", data=m_upd)

            # --- C. LINE送信 (ProfilesのE, F列から安全に取得) ---
            target_user = final_p[final_p["user_id"] == u_id].iloc[0]
            l_token = target_user.get("line_token")
            l_id = target_user.get("line_user_id")

            if l_token and l_id and str(l_token) != "nan":
                m_txt = "\n".join([f"・{k}: {v}" for k, v in metric_inputs.items()])
                line_msg = f"【AI報告】{target_date_str}\n評価: {int(rate)}\n内容: {str(note)}\n\n[数値]\n{m_txt}"
                
                payload = {"to": str(l_id), "messages": [{"type": "text", "text": line_msg}]}
                headers = {"Authorization": f"Bearer {l_token}", "Content-Type": "application/json"}
                requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
            
            st.cache_data.clear()
            st.success("全て完了しました！")
            st.rerun()

# --- AIコーチ ---
if st.button("💡 コーチのアドバイスを受ける", use_container_width=True):
    with st.spinner("AIコーチ分析中..."):
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model_name = st.session_state.get("sel_model", "gemini-3-pro")
        model = genai.GenerativeModel(model_name)
        personalities = {"安西先生": "穏やか", "熱血タイプ": "情熱的", "論理タイプ": "分析的"}
        prompt = f"コーチ設定:{personalities.get(u_coach)}\n目標:{u_goal}\n内容:{note}\n数値:{metric_inputs}"
        st.info(model.generate_content(prompt).text)

with st.sidebar:
    st.header("⚙️ Setting")
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    ms = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    st.session_state.sel_model = st.selectbox("AI Model", ms, index=0)
