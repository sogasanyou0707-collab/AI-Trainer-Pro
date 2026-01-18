import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import requests
import google.generativeai as genai
from datetime import datetime
import os

# ==========================================
# 1. ページ構成 & デザイン
# ==========================================
st.set_page_config(page_title="AI Trainer Pro", layout="centered")

st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"] { background-color: white !important; color: black !important; }
    h1, h2, h3, p, label, span, .stMarkdown { color: black !important; }
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
# 2. データ読み込み (徹底した型変換)
# ==========================================
@st.cache_data(ttl=60)
def fetch_master_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        p = conn.read(worksheet="Profiles")
        h = conn.read(worksheet="History")
        m = conn.read(worksheet="Metrics")
        
        # 日付を "YYYY-MM-DD" の標準文字列に強制変換
        for df in [h, m]:
            if not df.empty and "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        
        # 全ての値を標準Pythonオブジェクトに変換 (NumPy型を排除)
        def clean_df(df):
            if df.empty: return df
            return df.astype(object).where(pd.notnull(df), None)

        coach_types = ["安西先生", "熱血タイプ", "論理タイプ"]
        return clean_df(p), clean_df(h), clean_df(m), coach_types
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), ["安西先生", "熱血タイプ", "論理タイプ"]

profiles_df, history_df, metrics_df, coach_list = fetch_master_data()

# ==========================================
# 3. 初期設定 & メインUI
# ==========================================
if 'cfg' not in st.session_state:
    st.session_state.cfg = {"selected_model": "gemini-3-pro"}

st.title("🏀 AI Trainer Pro")

col_u, col_d = st.columns(2)
with col_u:
    u_list = profiles_df["user_id"].dropna().unique().tolist() if not profiles_df.empty else []
    selected_user = st.selectbox("👤 ユーザー", options=["新規登録"] + u_list)
with col_d:
    selected_date = st.date_input("📅 日付", value=datetime.now())
    date_str = selected_date.strftime("%Y-%m-%d")

# ユーザー詳細の特定
is_new = selected_user == "新規登録"
u_prof = profiles_df[profiles_df["user_id"].astype(str) == str(selected_user)].iloc[0].to_dict() if not is_new else {
    "user_id": "", "goal": "", "coach_name": "安西先生", "tracked_metrics": "シュート率,ハンドリング", "line_token": "", "line_user_id": ""
}

# 項目管理のセッション (ユーザー切替時に更新)
if 'm_list' not in st.session_state or st.session_state.get('last_u') != selected_user:
    st.session_state.m_list = [m.strip() for m in str(u_prof.get("tracked_metrics", "")).split(",") if m.strip()]
    st.session_state.last_u = selected_user

# ==========================================
# 4. 詳細設定 (コーチ・項目管理)
# ==========================================
with st.expander("⚙️ 詳細設定（プロフィール・項目管理）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=u_prof["user_id"])
    u_goal = st.text_area("現在の目標", value=u_prof["goal"])
    u_coach = st.selectbox("コーチのタイプ", options=coach_list, 
                           index=coach_list.index(u_prof["coach_name"]) if u_prof["coach_name"] in coach_list else 0)
    
    st.divider()
    c_add, c_del = st.columns(2)
    new_m = c_add.text_input("追加項目")
    if c_add.button("➕追加"):
        if new_m and new_m not in st.session_state.m_list:
            st.session_state.m_list.append(new_m)
            st.rerun()
    if st.session_state.m_list:
        del_m = c_del.selectbox("削除項目", options=["選択"] + st.session_state.m_list)
        if c_del.button("➖削除") and del_m != "選択":
            st.session_state.m_list.remove(del_m)
            st.rerun()

# ==========================================
# 5. データの反映 (History & Metrics)
# ==========================================
st.divider()
st.subheader(f"📝 {date_str} の振り返り")

# フィルタリング
h_match = history_df[(history_df["user_id"].astype(str) == str(selected_user)) & (history_df["date"] == date_str)]
m_match = metrics_df[(metrics_df["user_id"].astype(str) == str(selected_user)) & (metrics_df["date"] == date_str)]

if not h_match.empty:
    st.success("過去の記録を読み込みました")

# 型エラーを防ぐ安全な取得
rate_val = 3
if not h_match.empty:
    try: rate_val = int(float(h_match["rate"].iloc[0]))
    except: rate_val = 3
rate = st.slider("自己評価", 1, 5, rate_val)
note = st.text_area("内容・気づき", value=str(h_match["note"].iloc[0]) if not h_match.empty else "", height=150)

# --- 重要: 数値反映 (ハンドリングデータ等) ---

st.write("📊 本日の数値入力")
current_res_metrics = {}
for m_name in st.session_state.m_list:
    v_init = 0.0
    if not m_match.empty:
        # C列(metric_name)から完全に一致する行を探す
        target = m_match[m_match["metric_name"].astype(str).str.strip() == m_name]
        if not target.empty:
            try:
                v_init = float(target["value"].iloc[-1])
            except:
                v_init = 0.0
    current_res_metrics[m_name] = st.number_input(f"{m_name}", value=v_init, key=f"v_{m_name}")

# ==========================================
# 6. 保存 & LINE送信 (InvalidJSONError 対策済み)
# ==========================================
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        with st.spinner("保存中..."):
            conn = st.connection("gsheets", type=GSheetsConnection)
            
            # Profiles更新
            new_p = {"user_id": str(u_id), "goal": str(u_goal), "coach_name": str(u_coach), "tracked_metrics": ",".join(st.session_state.m_list)}
            p_upd = pd.concat([profiles_df[profiles_df["user_id"].astype(str) != str(u_id)], pd.DataFrame([new_p])], ignore_index=True)
            conn.update(worksheet="Profiles", data=p_upd)

            # History更新
            h_upd = pd.concat([history_df[~((history_df["user_id"].astype(str) == str(u_id)) & (history_df["date"] == date_str))], 
                               pd.DataFrame([{"user_id": str(u_id), "date": str(date_str), "rate": int(rate), "note": str(note)}])], ignore_index=True)
            conn.update(worksheet="History", data=h_upd)

            # Metrics更新
            m_new_data = []
            for k, v in current_res_metrics.items():
                m_new_data.append({"user_id": str(u_id), "date": str(date_str), "metric_name": str(k), "value": float(v)})
            m_upd = pd.concat([metrics_df[~((metrics_df["user_id"].astype(str) == str(u_id)) & (metrics_df["date"] == date_str))], pd.DataFrame(m_new_data)], ignore_index=True)
            conn.update(worksheet="Metrics", data=m_upd)

            # --- LINE送信 (JSONエラー回避のため全項目をPython標準型に変換) ---
            
            l_token = u_prof.get("line_token")
            l_id = u_prof.get("line_user_id")
            if l_token and l_id:
                # 数値を文字列化した見やすいメッセージ作成
                metrics_summary = "\n".join([f"・{k}: {v}" for k, v in current_res_metrics.items()])
                line_text = f"【AI報告】{date_str}\n評価: {'★' * int(rate)}\n内容: {str(note)}\n\n[数値データ]\n{metrics_summary}"
                
                payload = {
                    "to": str(l_id),
                    "messages": [{"type": "text", "text": line_text}]
                }
                headers = {"Authorization": f"Bearer {l_token}", "Content-Type": "application/json"}
                
                try:
                    res = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
                    if res.status_code != 200:
                        st.error(f"LINE送信失敗: {res.text}")
                except Exception as e:
                    st.error(f"LINE通信エラー: {e}")
            
            st.cache_data.clear()
            st.success("全て完了しました！")
            st.rerun()

# --- AIコーチ ---
if st.button("💡 AIコーチの分析", use_container_width=True):
    with st.spinner(f"{u_coach}が思考中..."):
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel(st.session_state.cfg["selected_model"])
        personalities = {
            "安西先生": "穏やかで、『諦めたらそこで試合終了』という言葉を大切にする。",
            "熱血タイプ": "修造のように熱く、努力を全力で褒める。",
            "論理タイプ": "数値を分析し、論理的な改善策を提示する。"
        }
        prompt = f"コーチ設定:{personalities.get(u_coach, '')}\n目標:{u_goal}\n報告:{note}\n数値:{current_res_metrics}\n3点助言を。"
        st.info(model.generate_content(prompt).text)

with st.sidebar:
    st.header("⚙️ Setting")
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    ms = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    st.session_state.cfg["selected_model"] = st.selectbox("Model", ms, index=0)
