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
# 2. データの取得と徹底した型クレンジング
# ==========================================
@st.cache_data(ttl=10) # 開発中は短めに設定
def fetch_master_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        p = conn.read(worksheet="Profiles")
        h = conn.read(worksheet="History")
        m = conn.read(worksheet="Metrics")
        
        # --- 日付の照合ミスをなくすための正規化 ---
        def normalize_df(df):
            if df.empty: return df
            # 全ての列を標準的なPythonオブジェクトに変換し、NaNを排除
            df = df.astype(object).where(pd.notnull(df), None)
            if "date" in df.columns:
                # 日付列を確実に 'YYYY-MM-DD' の文字列に統一
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str).str.strip()
            return df

        coach_types = ["安西先生", "熱血タイプ", "論理タイプ"]
        return normalize_df(p), normalize_df(h), normalize_df(m), coach_types
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), ["安西先生", "熱血タイプ", "論理タイプ"]

profiles_df, history_df, metrics_df, coach_list = fetch_master_data()

# ==========================================
# 3. 初期設定
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

# ユーザー詳細の取得
is_new = selected_user == "新規登録"
u_prof = profiles_df[profiles_df["user_id"] == str(selected_user)].iloc[0].to_dict() if not is_new else {
    "user_id": "", "goal": "", "coach_name": "安西先生", "tracked_metrics": "シュート率,ハンドリング", "line_token": "", "line_user_id": ""
}

# 項目のセッション管理
if 'm_list' not in st.session_state or st.session_state.get('last_u') != selected_user:
    st.session_state.m_list = [m.strip() for m in str(u_prof.get("tracked_metrics", "")).split(",") if m.strip()]
    st.session_state.last_u = selected_user

# ==========================================
# 4. 詳細設定 (プロフィール・コーチ設定)
# ==========================================
with st.expander("⚙️ 詳細設定（項目・コーチ設定）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=u_prof["user_id"])
    u_goal = st.text_area("現在の目標", value=u_prof["goal"])
    u_coach = st.selectbox("コーチの性格", options=coach_list, 
                           index=coach_list.index(u_prof["coach_name"]) if u_prof["coach_name"] in coach_list else 0)
    
    st.divider()
    c_add, c_del = st.columns(2)
    new_m = c_add.text_input("項目追加")
    if c_add.button("追加") and new_m:
        if new_m not in st.session_state.m_list:
            st.session_state.m_list.append(new_m)
            st.rerun()
    if st.session_state.m_list:
        del_m = c_del.selectbox("項目削除", options=["選択"] + st.session_state.m_list)
        if c_del.button("削除") and del_m != "選択":
            st.session_state.m_list.remove(del_m)
            st.rerun()

# ==========================================
# 5. データの反映と入力 (過去データの厳密な紐付け)
# ==========================================
st.divider()
st.subheader(f"📝 {date_str} の振り返り")

# 日付とユーザーIDによるフィルタリング
h_match = history_df[(history_df["user_id"] == str(selected_user)) & (history_df["date"] == date_str)]
m_match = metrics_df[(metrics_df["user_id"] == str(selected_user)) & (metrics_df["date"] == date_str)]

if not h_match.empty:
    st.success(f"✅ {date_str} の過去データを表示しています")

# 評価・日記の読み込み
try: rate_val = int(float(h_match["rate"].iloc[0]))
except: rate_val = 3
rate = st.slider("自己評価", 1, 5, rate_val)
note = st.text_area("練習内容", value=str(h_match["note"].iloc[0]) if not h_match.empty else "", height=150)

# --- 重要: 数値項目 (ハンドリング等) の反映 ---
current_res_metrics = {}
for m_name in st.session_state.m_list:
    v_init = 0.0
    if not m_match.empty:
        # C列(metric_name)が完全一致するものを取得
        target = m_match[m_match["metric_name"] == m_name]
        if not target.empty:
            try:
                v_init = float(target["value"].iloc[-1])
            except: v_init = 0.0
    current_res_metrics[m_name] = st.number_input(f"{m_name}", value=v_init, key=f"inp_{m_name}")

# ==========================================
# 6. 保存・LINE送信 (JSONエラーと上書きの同時解決)
# ==========================================
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        with st.spinner("保存と送信を実行中..."):
            conn = st.connection("gsheets", type=GSheetsConnection)
            
            # --- データの保存処理 ---
            # 1. Profiles
            new_p = u_prof.copy()
            new_p.update({"user_id": u_id, "goal": u_goal, "coach_name": u_coach, "tracked_metrics": ",".join(st.session_state.m_list)})
            p_upd = pd.concat([profiles_df[profiles_df["user_id"] != u_id], pd.DataFrame([new_p])], ignore_index=True)
            conn.update(worksheet="Profiles", data=p_upd)

            # 2. History (上書き防止のため現在の日付のみを置換)
            h_upd = pd.concat([history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == date_str))], 
                               pd.DataFrame([{"user_id": u_id, "date": date_str, "rate": int(rate), "note": note}])], ignore_index=True)
            conn.update(worksheet="History", data=h_upd)

            # 3. Metrics (上書き防止のため現在の日付のみを置換)
            m_new_rows = [{"user_id": u_id, "date": date_str, "metric_name": k, "value": float(v)} for k, v in current_res_metrics.items()]
            m_upd = pd.concat([metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == date_str))], pd.DataFrame(m_new_rows)], ignore_index=True)
            conn.update(worksheet="Metrics", data=m_upd)

            # --- LINE送信 (標準型へのキャスト徹底) ---
            l_token = u_prof.get("line_token")
            l_id = u_prof.get("line_user_id")
            if l_token and l_id:
                metrics_txt = "\n".join([f"・{k}: {v}" for k, v in current_res_metrics.items()])
                line_msg = f"【練習報告】{date_str}\n評価: {int(rate)}\n内容: {str(note)}\n\n[数値]\n{metrics_txt}"
                
                payload = {
                    "to": str(l_id),
                    "messages": [{"type": "text", "text": line_text}] # 安全な文字列型
                }
                # payloadの中身を確実にJSON化可能な形式にする
                payload_json = json.dumps({
                    "to": str(l_id),
                    "messages": [{"type": "text", "text": line_msg}]
                })
                
                headers = {"Authorization": f"Bearer {l_token}", "Content-Type": "application/json"}
                try:
                    # json= ではなく data= を使い、自前でdumpsすることでエラーを回避
                    requests.post("https://api.line.me/v2/bot/message/push", headers=headers, data=payload_json)
                except: st.error("LINE送信に失敗しました")
            
            st.cache_data.clear()
            st.success("全てのデータを正常に保存・送信しました。")
            st.rerun()

# --- AIコーチ機能 ---
if st.button("💡 AIコーチの分析を受ける", use_container_width=True):
    with st.spinner(f"{u_coach}が思考中..."):
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel(st.session_state.cfg["selected_model"])
        advice = model.generate_content(f"コーチ:{u_coach}\n目標:{u_goal}\n報告:{note}\n数値:{current_res_metrics}\nのアドバイスを3つ。").text
        st.info(advice)

with st.sidebar:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    ms = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    st.session_state.cfg["selected_model"] = st.selectbox("AI Model", ms, index=0)        
