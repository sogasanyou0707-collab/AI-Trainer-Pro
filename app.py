import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import requests
import google.generativeai as genai
from datetime import datetime
import os

# ==========================================
# 1. ページ構成 & UIデザイン
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
# 2. データの取得と強力な整形 (日付・空白対策)
# ==========================================
@st.cache_data(ttl=60) # 1分キャッシュ
def fetch_master_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        p = conn.read(worksheet="Profiles")
        h = conn.read(worksheet="History")
        m = conn.read(worksheet="Metrics")
        
        # --- 日付と文字列のクレンジング ---
        # 1. 日付列を強制的に YYYY-MM-DD 形式の文字列にする
        for df in [h, m]:
            if not df.empty and "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        
        # 2. 検索キーとなる文字列から前後の空白を削除
        if not m.empty:
            m["metric_name"] = m["metric_name"].astype(str).str.strip()
            m["user_id"] = m["user_id"].astype(str).str.strip()
        if not p.empty:
            p["user_id"] = p["user_id"].astype(str).str.strip()

        coach_types = ["安西先生", "熱血タイプ", "論理タイプ"]
        return p, h, m, coach_types
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), ["安西先生", "熱血タイプ", "論理タイプ"]

profiles_df, history_df, metrics_df, coach_list = fetch_master_data()

# ==========================================
# 3. AIコーチング定義
# ==========================================
def get_coach_advice(coach_type, goal, note, metrics, model_name):
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel(model_name)
    
    personalities = {
        "安西先生": "穏やかで、『諦めたらそこで試合終了』の精神。短い言葉で核心を突き、選手の可能性を信じる。",
        "熱血タイプ": "修造のような熱さ。根性と努力を褒め、感嘆符を多用してやる気を引き出す。",
        "論理タイプ": "分析的。具体的な数値の推移や効率的なトレーニングメニューを論理的に提案する。"
    }
    
    prompt = f"コーチ性格：{personalities.get(coach_type, '')}\n目標：{goal}\n報告：{note}\n数値：{metrics}\n上記から3点アドバイスを。"
    try:
        return model.generate_content(prompt).text
    except:
        return "コーチが休憩中です。再度お試しください。"

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

# ユーザー詳細の取得
is_new = selected_user == "新規登録"
u_prof = profiles_df[profiles_df["user_id"] == str(selected_user).strip()].iloc[0].to_dict() if not is_new else {
    "user_id": "", "goal": "", "coach_name": "安西先生", "tracked_metrics": "シュート率,ハンドリング"
}

# 項目のセッション管理 (ユーザー切替時にリセット)
if 'metrics_list' not in st.session_state or st.session_state.get('last_u') != selected_user:
    st.session_state.metrics_list = [m.strip() for m in str(u_prof.get("tracked_metrics", "")).split(",") if m.strip()]
    st.session_state.last_u = selected_user

# ==========================================
# 5. 詳細設定（プロフィール・項目管理）
# ==========================================
with st.expander("⚙️ 詳細設定（プロフィール・項目管理）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=u_prof["user_id"])
    u_goal = st.text_area("現在の目標", value=u_prof["goal"])
    u_coach = st.selectbox("コーチのタイプ", options=coach_list, 
                           index=coach_list.index(u_prof["coach_name"]) if u_prof["coach_name"] in coach_list else 0)
    
    st.write("---")
    st.subheader("📊 数値項目のカスタマイズ")
    c_add, c_del = st.columns(2)
    new_m = c_add.text_input("追加したい項目名")
    if c_add.button("➕ 追加") and new_m:
        if new_m not in st.session_state.metrics_list:
            st.session_state.metrics_list.append(new_m)
            st.rerun()

    if st.session_state.metrics_list:
        del_m = c_del.selectbox("削除したい項目を選択", options=["選択してください"] + st.session_state.metrics_list)
        if c_del.button("➖ 削除") and del_m != "選択してください":
            st.session_state.metrics_list.remove(del_m)
            st.rerun()

# ==========================================
# 6. 過去データの取得と表示 (Metrics B, C, D列完全対応)
# ==========================================
st.divider()
st.subheader(f"📝 {date_str} の振り返り")

# フィルタリング
h_match = history_df[(history_df["user_id"] == str(selected_user).strip()) & (history_df["date"] == date_str)]
m_match = metrics_df[(metrics_df["user_id"] == str(selected_user).strip()) & (metrics_df["date"] == date_str)]

if not h_match.empty:
    st.success(f"✅ {date_str} の過去記録を読み込みました")

# 自己評価・日記の安全な取得
def get_val(df, col, default=""):
    if not df.empty and pd.notna(df[col].iloc[0]):
        return df[col].iloc[0]
    return default

rate = st.slider("自己評価", 1, 5, int(float(get_val(h_match, "rate", 3))))
note = st.text_area("今日の内容・気づき", value=str(get_val(h_match, "note", "")), height=150)

# --- 数値計測 (B列:date, C列:metric_name, D列:value) ---
st.write("📊 本日の数値")
current_res_metrics = {}
for m_name in st.session_state.metrics_list:
    v_init = 0.0
    if not m_match.empty:
        # C列(metric_name)が一致する行を探す
        target_row = m_match[m_match["metric_name"] == m_name]
        if not target_row.empty:
            try:
                # D列(value)を取得
                v_init = float(target_row["value"].iloc[0])
            except:
                v_init = 0.0
    current_res_metrics[m_name] = st.number_input(f"{m_name} の結果", value=v_init, key=f"inp_{m_name}")

# ==========================================
# 7. 保存 & コーチング
# ==========================================
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        with st.spinner("スプレッドシートを更新中..."):
            conn = st.connection("gsheets", type=GSheetsConnection)
            # Profiles更新
            new_p = {"user_id": u_id, "goal": u_goal, "coach_name": u_coach, "tracked_metrics": ",".join(st.session_state.metrics_list)}
            p_upd = pd.concat([profiles_df[profiles_df["user_id"] != u_id], pd.DataFrame([new_p])], ignore_index=True)
            conn.update(worksheet="Profiles", data=p_upd)
            # History更新
            h_upd = pd.concat([history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == date_str))], 
                               pd.DataFrame([{"user_id": u_id, "date": date_str, "rate": rate, "note": note}])], ignore_index=True)
            conn.update(worksheet="History", data=h_upd)
            # Metrics更新
            m_rows = [{"user_id": u_id, "date": date_str, "metric_name": k, "value": v} for k, v in current_res_metrics.items()]
            m_upd = pd.concat([metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == date_str))], pd.DataFrame(m_rows)], ignore_index=True)
            conn.update(worksheet="Metrics", data=m_upd)

            st.cache_data.clear()
            st.success("保存完了しました！")
            st.rerun()

if st.button("💡 コーチのアドバイスを受ける", use_container_width=True):
    with st.spinner(f"{u_coach}が分析中..."):
        advice = get_coach_advice(u_coach, u_goal, note, current_res_metrics, st.session_state.cfg["selected_model"])
        st.info(advice)

with st.sidebar:
    st.header("⚙️ システム設定")
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    ms = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    st.session_state.cfg["selected_model"] = st.selectbox("使用AIモデル", ms, index=0)
