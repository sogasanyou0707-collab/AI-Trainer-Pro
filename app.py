import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import requests
import google.generativeai as genai
from datetime import datetime
import os

# ==========================================
# 1. デザイン設定
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
# 2. 接続 & データ読み込み (安定版)
# ==========================================
@st.cache_data(ttl=5)
def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        p = conn.read(worksheet="Profiles", ttl=0)
        h = conn.read(worksheet="History", ttl=0)
        m = conn.read(worksheet="Metrics", ttl=0)
        
        # 日付標準化 (YYYY-MM-DD)
        for df in [h, m]:
            if not df.empty and "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        
        # 空白トリミング
        for df in [p, h, m]:
            if not df.empty:
                for col in df.columns:
                    if df[col].dtype == 'object':
                        df[col] = df[col].astype(str).str.strip()
        return p, h, m
    except Exception as e:
        st.error(f"読み込み失敗: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

profiles_df, history_df, metrics_df = load_data()

# ==========================================
# 3. メインUI
# ==========================================
st.title("🏀 AI Trainer Pro")

col_u, col_d = st.columns(2)
with col_u:
    u_list = profiles_df["user_id"].dropna().unique().tolist() if not profiles_df.empty else []
    selected_user = st.selectbox("👤 ユーザー", options=["新規登録"] + u_list)
with col_d:
    selected_date = st.date_input("📅 記録日", value=datetime.now())
    target_date_str = selected_date.strftime("%Y-%m-%d")

# ユーザー詳細
is_new = selected_user == "新規登録"
u_prof_row = profiles_df[profiles_df["user_id"] == selected_user]
u_prof = u_prof_row.iloc[0] if not is_new and not u_prof_row.empty else pd.Series()

# 過去データ検索
existing_history = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == target_date_str)] if not is_new else pd.DataFrame()
existing_metrics = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == target_date_str)] if not is_new else pd.DataFrame()

# ==========================================
# 4. プロフィール設定 (詳細設定)
# ==========================================
with st.expander("⚙️ 詳細設定（項目・コーチ設定）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=str(u_prof.get("user_id", "")))
    u_goal = st.text_area("目標", value=str(u_prof.get("goal", "")))
    coach_opts = ["安西先生", "熱血タイプ", "論理タイプ"]
    u_coach = st.selectbox("コーチ", options=coach_opts, 
                           index=coach_opts.index(u_prof.get("coach_name")) if u_prof.get("coach_name") in coach_opts else 0)
    
    # 計測項目の同期
    if 'm_list' not in st.session_state or st.session_state.get('last_u') != selected_user:
        st.session_state.m_list = [m.strip() for m in str(u_prof.get("tracked_metrics", "シュート率,ハンドリング")).split(",") if m.strip()]
        st.session_state.last_u = selected_user

    c_add, c_del = st.columns(2)
    new_m = c_add.text_input("項目追加")
    if c_add.button("追加"):
        if new_m and new_m not in st.session_state.m_list:
            st.session_state.m_list.append(new_m)
            st.rerun()
    if st.session_state.m_list:
        del_m = c_del.selectbox("項目削除", options=["選択"] + st.session_state.m_list)
        if c_del.button("削除") and del_m != "選択":
            st.session_state.m_list.remove(del_m)
            st.rerun()

# ==========================================
# 5. 入力フォーム
# ==========================================
st.divider()
st.subheader(f"📝 {target_date_str} の振り返り")

rate = st.slider("自己評価", 1, 5, int(existing_history.iloc[0]["rate"]) if not existing_history.empty else 3)
note = st.text_area("内容", value=str(existing_history.iloc[0]["note"]) if not existing_history.empty else "", height=150)

metric_inputs = {}
for m_name in st.session_state.m_list:
    v_init = 0.0
    if not existing_metrics.empty:
        m_match = existing_metrics[existing_metrics["metric_name"] == m_name]
        if not m_match.empty:
            try: v_init = float(m_match.iloc[-1]["value"])
            except: v_init = 0.0
    metric_inputs[m_name] = st.number_input(f"{m_name} の結果", value=v_init)

# ==========================================
# 6. 【重要】保存 & LINE送信 (データ保護ロジック)
# ==========================================


if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("IDを入力してください")
    else:
        with st.spinner("処理中..."):
            conn = st.connection("gsheets", type=GSheetsConnection)
            
            # --- A. Profilesの安全な更新 ---
            # 最新のシートを読み直し、全ての列を保持する
            p_latest = conn.read(worksheet="Profiles", ttl=0)
            if u_id in p_latest["user_id"].astype(str).values:
                # 既存ユーザーなら、その行の特定の列だけ書き換える
                idx = p_latest[p_latest["user_id"].astype(str) == u_id].index[0]
                p_latest.at[idx, "goal"] = u_goal
                p_latest.at[idx, "coach_name"] = u_coach
                p_latest.at[idx, "tracked_metrics"] = ",".join(st.session_state.m_list)
                updated_p = p_latest
            else:
                # 新規ユーザーなら追加
                new_row = pd.DataFrame([{"user_id": u_id, "goal": u_goal, "coach_name": u_coach, "tracked_metrics": ",".join(st.session_state.m_list)}])
                updated_p = pd.concat([p_latest, new_row], ignore_index=True)
            
            # --- B. History & Metrics の更新 ---
            h_clean = history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == target_date_str))]
            h_new = pd.DataFrame([{"user_id": u_id, "date": target_date_str, "rate": rate, "note": note}])
            
            m_clean = metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == target_date_str))]
            m_new = pd.DataFrame([{"user_id": u_id, "date": target_date_str, "metric_name": k, "value": v} for k, v in metric_inputs.items()])

            # スプレッドシートへ書き込み
            conn.update(worksheet="Profiles", data=updated_p)
            conn.update(worksheet="History", data=pd.concat([h_clean, h_new], ignore_index=True))
            conn.update(worksheet="Metrics", data=pd.concat([m_clean, m_new], ignore_index=True))

            # --- C. LINE送信 (保存した直後の情報を使用) ---
            target_user_info = updated_p[updated_p["user_id"] == u_id].iloc[0]
            l_token = target_user_info.get("line_token")
            l_id = target_user_info.get("line_user_id")

            if l_token and l_id:
                m_txt = "\n".join([f"・{k}: {v}" for k, v in metric_inputs.items()])
                line_text = f"【練習報告】{target_date_str}\n評価: {int(rate)}\n内容: {str(note)}\n\n[数値]\n{m_txt}"
                
                payload = json.dumps({
                    "to": str(l_id),
                    "messages": [{"type": "text", "text": line_text}]
                })
                headers = {"Authorization": f"Bearer {l_token}", "Content-Type": "application/json"}
                res = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, data=payload)
            
            st.cache_data.clear()
            st.success("全てのデータを保存し、LINEへ報告しました！")
            st.rerun()

# --- AIコーチ ---
if st.button("💡 コーチのアドバイスを受ける", use_container_width=True):
    with st.spinner("分析中..."):
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel(st.session_state.get("sel_model", "gemini-3-pro"))
        personalities = {"安西先生": "穏やか", "熱血タイプ": "情熱的", "論理タイプ": "分析的"}
        prompt = f"性格:{personalities.get(u_coach)}\n目標:{u_goal}\n報告:{note}\n数値:{metric_inputs}\nのアドバイスを。"
        st.info(model.generate_content(prompt).text)

with st.sidebar:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    ms = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    st.session_state.sel_model = st.selectbox("AI Model", ms, index=0)
