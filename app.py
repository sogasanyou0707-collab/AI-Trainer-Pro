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
# 2. 接続 & データ読み込み (ご提示のロジックを完全復元)
# ==========================================
@st.cache_data(ttl=10)
def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        p = conn.read(worksheet="Profiles", ttl=0)
        h = conn.read(worksheet="History", ttl=0)
        m = conn.read(worksheet="Metrics", ttl=0)
        
        # --- 日付の型を YYYY-MM-DD 文字列に完全統一 ---
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

# --- その日の既存記録の読み出し (ご提示の成功ロジック) ---
existing_history = pd.Series()
existing_metrics = pd.DataFrame()
if not is_new:
    if not history_df.empty:
        h_match = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == target_date_str)]
        if not h_match.empty: existing_history = h_match.iloc[-1]
    if not metrics_df.empty:
        existing_metrics = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == target_date_str)]

# ==========================================
# 4. サイドバー設定 (LINE情報の可視化)
# ==========================================
with st.sidebar:
    st.header("⚙️ システム設定")
    # シートのE列・F列から読み込んだ情報を表示
    st.info(f"LINE Token: {'設定済' if pd.notna(u_prof.get('line_token')) else '未設定'}")
    line_token_val = st.text_input("LINE Channel Token (修正用)", 
                                   value=str(u_prof.get("line_token", "")) if pd.notna(u_prof.get("line_token")) else "", type="password")
    line_user_val = st.text_input("LINE User ID (修正用)", 
                                  value=str(u_prof.get("line_user_id", "")) if pd.notna(u_prof.get("line_user_id")) else "")
    
    st.divider()
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    ms = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    st.session_state.sel_model = st.selectbox("AI Model", ms, index=0)

# ==========================================
# 5. 詳細設定 (項目管理)
# ==========================================
with st.expander("⚙️ 詳細設定（プロフィール・項目管理）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=str(u_prof.get("user_id", "")) if pd.notna(u_prof.get("user_id")) else "")
    u_goal = st.text_area("目標", value=str(u_prof.get("goal", "")) if pd.notna(u_prof.get("goal")) else "")
    coach_opts = ["安西先生", "熱血タイプ", "論理タイプ"]
    u_coach = st.selectbox("コーチ", options=coach_opts, 
                           index=coach_opts.index(u_prof.get("coach_name")) if u_prof.get("coach_name") in coach_opts else 0)
    
    metrics_str = st.text_input("計測項目（カンマ区切り）", 
                                value=str(u_prof.get("tracked_metrics", "シュート率,ハンドリング")))

# ==========================================
# 6. 振り返り入力 (ハンドリング等の反映)
# ==========================================
st.divider()
st.subheader(f"📝 {target_date_str} の振り返り")

try:
    def_rate = int(float(existing_history.get("rate", 3)))
except: def_rate = 3
rate = st.slider("自己評価", 1, 5, def_rate)
note = st.text_area("練習内容・気づき", value=str(existing_history.get("note", "")), height=150)

# --- ここが重要：以前成功していたMetrics反映ロジックを完全再現 ---
metric_inputs = {}
if metrics_str:
    for m_name in metrics_str.split(","):
        m_name = m_name.strip()
        if m_name:
            prev_val = 0.0
            if not existing_metrics.empty:
                # 項目名で一致する行を検索
                m_match = existing_metrics[existing_metrics["metric_name"] == m_name]
                if not m_match.empty:
                    try: prev_val = float(m_match.iloc[-1]["value"])
                    except: prev_val = 0.0
            metric_inputs[m_name] = st.number_input(f"{m_name} の結果", value=prev_val)

# ==========================================
# 7. 保存 & LINE報告 (データ保護ロジック)
# ==========================================
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            
            # --- Profiles更新 (特定のセルだけを更新し、E, F列を守る) ---
            p_latest = conn.read(worksheet="Profiles", ttl=0)
            new_p_data = {
                "user_id": u_id, "goal": u_goal, "coach_name": u_coach, "tracked_metrics": metrics_str,
                "line_token": line_token_val, "line_user_id": line_user_val
            }
            
            if u_id in p_latest["user_id"].astype(str).values:
                idx = p_latest[p_latest["user_id"].astype(str) == u_id].index[0]
                for key, val in new_p_data.items():
                    p_latest.at[idx, key] = val
                final_p = p_latest
            else:
                final_p = pd.concat([p_latest, pd.DataFrame([new_p_data])], ignore_index=True)

            # --- History & Metrics 更新 ---
            h_upd = pd.concat([history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == target_date_str))], 
                               pd.DataFrame([{"user_id": u_id, "date": target_date_str, "rate": rate, "note": note}])], ignore_index=True)
            
            m_rows = [{"user_id": u_id, "date": target_date_str, "metric_name": k, "value": v} for k, v in metric_inputs.items()]
            m_upd = pd.concat([metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == target_date_str))], pd.DataFrame(m_rows)], ignore_index=True)

            # スプレッドシート保存
            conn.update(worksheet="Profiles", data=final_p)
            conn.update(worksheet="History", data=h_upd)
            conn.update(worksheet="Metrics", data=m_upd)

            # --- LINE報告 ---
            if line_token_val and line_user_val:
                m_txt = "\n".join([f"・{k}: {v}" for k, v in metric_inputs.items()])
                line_msg = f"【AI報告】{target_date_str}\n評価: {int(rate)}\n内容: {str(note)}\n\n[数値]\n{m_txt}"
                payload = {"to": str(line_user_val), "messages": [{"type": "text", "text": line_msg}]}
                headers = {"Authorization": f"Bearer {line_token_val}", "Content-Type": "application/json"}
                requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
            
            st.cache_data.clear()
            st.success("全て完了しました！")
            st.rerun()
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")

if st.button("💡 コーチの助言を受ける"):
    with st.spinner("分析中..."):
        model = genai.GenerativeModel(st.session_state.sel_model)
        prompt = f"コーチ:{u_coach}, 目標:{u_goal}, 内容:{note}, 数値:{metric_inputs}から3つ助言を。"
        st.info(model.generate_content(prompt).text)
