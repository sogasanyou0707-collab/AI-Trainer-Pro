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
    html, body, [data-testid="stAppViewContainer"] { background-color: white !important; color: black !important; }
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
# 2. データの取得 (E列: line_token, F列: line_user_id を含む)
# ==========================================
@st.cache_data(ttl=5)
def fetch_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        p = conn.read(worksheet="Profiles", ttl=0)
        h = conn.read(worksheet="History", ttl=0)
        m = conn.read(worksheet="Metrics", ttl=0)
        
        # 型の標準化と空白削除
        for df in [p, h, m]:
            if not df.empty:
                df.columns = [c.strip() for c in df.columns] # 列名の空白削除
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                for col in df.columns:
                    if df[col].dtype == 'object':
                        df[col] = df[col].astype(str).str.strip()
        return p, h, m
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

profiles_df, history_df, metrics_df = fetch_data()

# ==========================================
# 3. メインUI：ユーザー & 日付
# ==========================================
st.title("🏀 AI Trainer Pro")

col_u, col_d = st.columns(2)
with col_u:
    u_list = profiles_df["user_id"].dropna().unique().tolist() if not profiles_df.empty else []
    selected_user = st.selectbox("👤 ユーザー", options=["新規登録"] + u_list)
with col_d:
    selected_date = st.date_input("📅 記録日", value=datetime.now())
    date_str = selected_date.strftime("%Y-%m-%d")

# ユーザー詳細の特定
is_new = selected_user == "新規登録"
u_prof_row = profiles_df[profiles_df["user_id"] == str(selected_user)]
u_prof = u_prof_row.iloc[0] if not is_new and not u_prof_row.empty else pd.Series()

# ==========================================
# 4. 詳細設定 (編集してもE/F列は壊さない仕組み)
# ==========================================
with st.expander("⚙️ 詳細設定（プロフィール・項目管理）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=str(u_prof.get("user_id", "")))
    u_goal = st.text_area("目標", value=str(u_prof.get("goal", "")))
    c_opts = ["安西先生", "熱血タイプ", "論理タイプ"]
    u_coach = st.selectbox("コーチ", options=c_opts, 
                           index=c_opts.index(u_prof.get("coach_name")) if u_prof.get("coach_name") in c_opts else 0)
    
    if 'm_list' not in st.session_state or st.session_state.get('last_u') != selected_user:
        st.session_state.m_list = [m.strip() for m in str(u_prof.get("tracked_metrics", "シュート率,ハンドリング")).split(",") if m.strip()]
        st.session_state.last_u = selected_user

# ==========================================
# 5. 振り返り入力
# ==========================================
st.divider()
h_match = history_df[(history_df["user_id"] == str(selected_user)) & (history_df["date"] == date_str)]
m_match = metrics_df[(metrics_df["user_id"] == str(selected_user)) & (metrics_df["date"] == date_str)]

if not h_match.empty:
    st.success(f"✅ {date_str} の記録を読み込みました")

rate = st.slider("自己評価", 1, 5, int(float(h_match.iloc[0]["rate"])) if not h_match.empty else 3)
note = st.text_area("内容", value=str(h_match.iloc[0]["note"]) if not h_match.empty else "", height=150)

# 数値入力
metric_results = {}
for m_name in st.session_state.m_list:
    v_init = 0.0
    if not m_match.empty:
        target_m = m_match[m_match["metric_name"] == m_name]
        if not target_m.empty:
            try: v_init = float(target_m.iloc[-1]["value"])
            except: v_init = 0.0
    metric_results[m_name] = st.number_input(f"{m_name} の結果", value=v_init, key=f"inp_{m_name}")

# ==========================================
# 6. 保存 & LINE連携 (E列/F列を保護して取得)
# ==========================================
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        with st.spinner("保存とLINE送信を実行中..."):
            conn = st.connection("gsheets", type=GSheetsConnection)
            
            # --- Profilesの保護更新ロジック ---
            p_latest = conn.read(worksheet="Profiles", ttl=0)
            if u_id in p_latest["user_id"].astype(str).values:
                # 既存ユーザー：E列・F列はそのまま、A〜D列だけ更新
                idx = p_latest[p_latest["user_id"].astype(str) == u_id].index[0]
                p_latest.at[idx, "goal"] = u_goal
                p_latest.at[idx, "coach_name"] = u_coach
                p_latest.at[idx, "tracked_metrics"] = ",".join(st.session_state.m_list)
                # E列(line_token)とF列(line_user_id)は既存の値を保持
                token = p_latest.at[idx, "line_token"]
                user_id = p_latest.at[idx, "line_user_id"]
            else:
                # 新規ユーザー
                new_row = pd.DataFrame([{"user_id": u_id, "goal": u_goal, "coach_name": u_coach, "tracked_metrics": ",".join(st.session_state.m_list)}])
                p_latest = pd.concat([p_latest, new_row], ignore_index=True)
                token = None
                user_id = None
            
            # History & Metrics のマージ
            h_upd = pd.concat([history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == date_str))], 
                               pd.DataFrame([{"user_id": u_id, "date": date_str, "rate": rate, "note": note}])], ignore_index=True)
            
            m_new_list = [{"user_id": u_id, "date": date_str, "metric_name": k, "value": v} for k, v in metric_results.items()]
            m_upd = pd.concat([metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == date_str))], pd.DataFrame(m_new_list)], ignore_index=True)

            # 保存
            conn.update(worksheet="Profiles", data=p_latest)
            conn.update(worksheet="History", data=h_upd)
            conn.update(worksheet="Metrics", data=m_upd)

            # --- LINE送信実行 ---
            if token and user_id and str(token) != "None" and str(user_id) != "None":
                m_txt = "\n".join([f"・{k}: {v}" for k, v in metric_results.items()])
                msg = f"【練習報告】{date_str}\n評価: {int(rate)}\n内容: {str(note)}\n\n[数値]\n{m_txt}"
                
                payload = json.dumps({"to": str(user_id), "messages": [{"type": "text", "text": msg}]})
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                
                try:
                    res = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, data=payload)
                    if res.status_code == 200: st.success("LINE送信成功！")
                    else: st.error(f"LINE送信失敗(Status:{res.status_code})")
                except: st.error("LINE通信エラー")
            else:
                st.warning("LINE連携情報（E列/F列）がProfilesシートにありません。")
            
            st.cache_data.clear()
            st.rerun()

# --- AIコーチ ---
if st.button("💡 コーチのアドバイスを受ける", use_container_width=True):
    with st.spinner("思考中..."):
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model_name = st.session_state.get("sel_model", "gemini-3-pro")
        model = genai.GenerativeModel(model_name)
        prompt = f"コーチ:{u_coach}\n目標:{u_goal}\n本日の内容:{note}\n数値:{metric_results}\nのアドバイスを3点。"
        st.info(model.generate_content(prompt).text)

with st.sidebar:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    ms = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    st.session_state.sel_model = st.selectbox("AI Model", ms, index=0)
