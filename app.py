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
# 2. データの取得と徹底クレンジング (同期不全の解消)
# ==========================================
@st.cache_data(ttl=3) # デバッグのためキャッシュを極短に設定
def fetch_master_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        p = conn.read(worksheet="Profiles", ttl=0)
        h = conn.read(worksheet="History", ttl=0)
        m = conn.read(worksheet="Metrics", ttl=0)
        
        # 検索漏れを防ぐための正規化
        for df in [h, m]:
            if not df.empty and "date" in df.columns:
                # 日付を YYYY-MM-DD 文字列に完全統一 (時刻情報やシリアル値を排除)
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            if not df.empty:
                # 文字列の空白をトリミング
                for col in df.columns:
                    if df[col].dtype == 'object':
                        df[col] = df[col].astype(str).str.strip()
        
        if not p.empty:
            p["user_id"] = p["user_id"].astype(str).str.strip()
            
        return p, h, m
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

profiles_df, history_df, metrics_df = fetch_master_data()

# ==========================================
# 3. メインUI：ユーザー & 日付
# ==========================================
st.title("🏀 AI Trainer Pro")

col_u, col_d = st.columns(2)
with col_u:
    u_list = profiles_df["user_id"].dropna().unique().tolist() if not profiles_df.empty else []
    selected_user = st.selectbox("👤 ユーザー", options=["新規登録"] + u_list)
with col_d:
    selected_date = st.date_input("📅 日付", value=datetime.now())
    date_str = selected_date.strftime("%Y-%m-%d")

is_new = selected_user == "新規登録"
u_prof_row = profiles_df[profiles_df["user_id"] == str(selected_user)]
u_prof = u_prof_row.iloc[0] if not is_new and not u_prof_row.empty else pd.Series()

# --- データの抽出 (ご提示のロジックにガードを追加) ---
existing_history = history_df[(history_df["user_id"] == str(selected_user)) & (history_df["date"] == date_str)] if not is_new else pd.DataFrame()
existing_metrics = metrics_df[(metrics_df["user_id"] == str(selected_user)) & (metrics_df["date"] == date_str)] if not is_new else pd.DataFrame()

# ==========================================
# 4. 詳細設定 (列の消失を防ぐ保護ロジック)
# ==========================================
with st.expander("⚙️ 詳細設定（項目・コーチ設定）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=str(u_prof.get("user_id", "")))
    u_goal = st.text_area("現在の目標", value=str(u_prof.get("goal", "")))
    u_coach = st.selectbox("コーチ", ["安西先生", "熱血タイプ", "論理タイプ"], 
                           index=["安西先生", "熱血タイプ", "論理タイプ"].index(u_prof.get("coach_name")) if u_prof.get("coach_name") in ["安西先生", "熱血タイプ", "論理タイプ"] else 0)
    
    # 計測項目のセッション管理
    if 'm_list' not in st.session_state or st.session_state.get('last_u') != selected_user:
        st.session_state.m_list = [m.strip() for m in str(u_prof.get("tracked_metrics", "シュート率,ハンドリング")).split(",") if m.strip()]
        st.session_state.last_u = selected_user

# ==========================================
# 5. 入力 & 数値反映 (ハンドリングデータ表示)
# ==========================================
st.divider()
st.subheader(f"📝 {date_str} の振り返り")

try:
    val_rate = int(float(existing_history.iloc[0]["rate"])) if not existing_history.empty else 3
except: val_rate = 3

rate = st.slider("自己評価", 1, 5, val_rate)
note = st.text_area("練習内容", value=str(existing_history.iloc[0]["note"]) if not existing_history.empty else "", height=150)

# --- 数値反映 (B, C, D列完全同期ロジック) ---
res_metrics = {}
for m_name in st.session_state.m_list:
    v_init = 0.0
    if not existing_metrics.empty:
        # 項目名で一致する行を特定
        target_row = existing_metrics[existing_metrics["metric_name"] == m_name]
        if not target_row.empty:
            try:
                v_init = float(target_row.iloc[-1]["value"])
            except: v_init = 0.0
    res_metrics[m_name] = st.number_input(f"{m_name}", value=v_init, key=f"inp_{m_name}")

# ==========================================
# 6. 保存 & LINE連携 (保護更新 & JSON安定化)
# ==========================================
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("IDを入力してください")
    else:
        with st.spinner("保存中..."):
            conn = st.connection("gsheets", type=GSheetsConnection)
            
            # --- Profilesの保護更新 (E/F列を絶対に消さない) ---
            p_latest = conn.read(worksheet="Profiles", ttl=0)
            if u_id in p_latest["user_id"].astype(str).values:
                idx = p_latest[p_latest["user_id"].astype(str) == u_id].index[0]
                p_latest.at[idx, "goal"] = u_goal
                p_latest.at[idx, "coach_name"] = u_coach
                p_latest.at[idx, "tracked_metrics"] = ",".join(st.session_state.m_list)
                # E, F列の情報を取り出す
                token = p_latest.at[idx, "line_token"] if "line_token" in p_latest.columns else None
                user_id = p_latest.at[idx, "line_user_id"] if "line_user_id" in p_latest.columns else None
            else:
                new_profile = pd.DataFrame([{"user_id": u_id, "goal": u_goal, "coach_name": u_coach, "tracked_metrics": ",".join(st.session_state.m_list)}])
                p_latest = pd.concat([p_latest, new_profile], ignore_index=True)
                token, user_id = None, None

            # History & Metrics の部分置換更新
            h_upd = pd.concat([history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == date_str))], 
                               pd.DataFrame([{"user_id": u_id, "date": date_str, "rate": rate, "note": note}])], ignore_index=True)
            m_new_data = [{"user_id": u_id, "date": date_str, "metric_name": k, "value": v} for k, v in res_metrics.items()]
            m_upd = pd.concat([metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == date_str))], pd.DataFrame(m_new_data)], ignore_index=True)

            # 更新実行
            conn.update(worksheet="Profiles", data=p_latest)
            conn.update(worksheet="History", data=h_upd)
            conn.update(worksheet="Metrics", data=m_upd)

            # LINE送信 (型変換の徹底)
            if token and user_id and str(token) != "nan":
                m_txt = "\n".join([f"・{k}: {v}" for k, v in res_metrics.items()])
                line_msg = f"【AI報告】{date_str}\n評価: {int(rate)}\n内容: {str(note)}\n\n[数値]\n{m_txt}"
                payload = json.dumps({"to": str(user_id), "messages": [{"type": "text", "text": line_msg}]})
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                try: requests.post("https://api.line.me/v2/bot/message/push", headers=headers, data=payload)
                except: pass
            
            st.cache_data.clear()
            st.success("全て完了しました！")
            st.rerun()

# ==========================================
# 7. AIコーチング
# ==========================================
if st.button("💡 コーチのアドバイスを受ける", use_container_width=True):
    with st.spinner("AIコーチ分析中..."):
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel(st.session_state.get("sel_model", "gemini-3-pro"))
        prompt = f"コーチ設定:{u_coach}\n目標:{u_goal}\n本日の振り返り:{note}\n数値:{res_metrics}\nの3つ助言を。"
        st.info(model.generate_content(prompt).text)

with st.sidebar:
    st.header("⚙️ システム設定")
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    ms = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    st.session_state.sel_model = st.selectbox("使用モデル", ms, index=0)

# デバッグ用ビュー (もし反映されない場合にシートの生データを確認できます)
with st.expander("🛠️ デバッグ：Metricsシートの現在のデータ"):
    st.write(metrics_df[metrics_df["user_id"] == str(selected_user)])
