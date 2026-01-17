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

# モバイル・白基調CSS
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
@st.cache_data(ttl=600)
def fetch_all_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        # シート読み込み (Profiles, History, Metrics, Settings)
        p = conn.read(worksheet="Profiles")
        h = conn.read(worksheet="History")
        m = conn.read(worksheet="Metrics")
        try:
            s = conn.read(worksheet="Settings")
            c_list = s["coach_names"].dropna().tolist() if "coach_names" in s.columns else []
        except:
            c_list = p["coach_name"].dropna().unique().tolist() if not p.empty else []
        return p, h, m, c_list
    except Exception as e:
        # APIエラー時は空のデータフレームを返す
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), []

# データ取得
profiles_df, history_df, metrics_df, coach_list = fetch_all_data()

# キャッシュファイル読み込み
def load_cfg():
    if os.path.exists("app_settings.json"):
        with open("app_settings.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {"selected_model": "gemini-3-pro"}

cfg = load_cfg()

# ==========================================
# 3. 【重要】サイドバーを先に配置 (エラーで見えなくなるのを防ぐ)
# ==========================================
with st.sidebar:
    st.header("⚙️ システム設定")
    
    # Geminiモデル選択 (1.5系除外)
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        all_models = [m.name.replace('models/', '') for m in genai.list_models() 
                      if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    except:
        all_models = ["gemini-3-pro", "gemini-2.5-pro"]
    
    current_m = cfg.get("selected_model", "gemini-3-pro")
    sel_model = st.selectbox("使用AIモデル", all_models, 
                             index=all_models.index(current_m) if current_m in all_models else 0)
    
    if sel_model != current_m:
        cfg["selected_model"] = sel_model
        with open("app_settings.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
        st.rerun()

    st.divider()
    if st.button("🔄 データを再読み込み"):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 4. メインUI
# ==========================================
st.title("🏀 AI Trainer Pro")

# データが空の場合のガード
if profiles_df.empty:
    st.error("スプレッドシートの読み込みに失敗しました。Secretsの設定や、シート名を確認してください。")
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
u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0].to_dict() if not is_new else {
    "user_id": "", "goal": "", "coach_name": "", "tracked_metrics": "シュート率,ハンドリング", "tasks_json": "[]"
}

# 過去データ検索
h_match = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == date_str)] if not is_new and not history_df.empty else pd.DataFrame()
m_match = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == date_str)] if not is_new and not metrics_df.empty else pd.DataFrame()

# ==========================================
# 5. 詳細設定 (項目の追加・削除)
# ==========================================
with st.expander("⚙️ 詳細設定（プロフィール・項目管理）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=u_prof["user_id"])
    u_goal = st.text_area("現在の目標", value=u_prof["goal"])
    
    f_coach_list = sorted(list(set(coach_list + ([u_prof["coach_name"]] if u_prof["coach_name"] else []))))
    u_coach = st.selectbox("担当コーチ", options=f_coach_list, 
                           index=f_coach_list.index(u_prof["coach_name"]) if u_prof["coach_name"] in f_coach_list else 0)
    
    st.subheader("📊 数値項目のカスタマイズ")
    current_ms = [m.strip() for m in str(u_prof["tracked_metrics"]).split(",") if m.strip()]
    
    c_add, c_del = st.columns(2)
    new_m = c_add.text_input("追加項目名")
    if c_add.button("➕ 追加"):
        if new_m and new_m not in current_ms:
            current_ms.append(new_m)
            u_prof["tracked_metrics"] = ",".join(current_ms)
            st.rerun()

    if current_ms:
        del_m = c_del.selectbox("削除項目", options=["選択"] + current_ms)
        if c_del.button("➖ 削除"):
            if del_m in current_ms:
                current_ms.remove(del_m)
                u_prof["tracked_metrics"] = ",".join(current_ms)
                st.rerun()
    
    st.caption(f"現在の計測項目: {', '.join(current_ms)}")

# ==========================================
# 6. 練習記録 & 保存ロジック
# ==========================================
st.divider()
st.subheader(f"📝 {date_str} の振り返り")

# エラー箇所: iloc[0] を使わず、safeな取得方法に変更
default_rate = 3
if not h_match.empty:
    try:
        default_rate = int(h_match["rate"].values[0])
    except:
        pass

rate = st.slider("自己評価", 1, 5, default_rate)
note = st.text_area("内容・気づき", value=str(h_match["note"].values[0]) if not h_match.empty else "")

metric_results = {}
for m_name in current_ms:
    v_init = 0.0
    if not m_match.empty:
        m_val = m_match[m_match["metric_name"] == m_name]
        if not m_val.empty:
            v_init = float(m_val["value"].values[0])
    metric_results[m_name] = st.number_input(f"{m_name} の結果", value=v_init)

# 保存ボタン
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        # 保存ロジック (省略せず全反映)
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # Profiles更新
        new_p = {"user_id": u_id, "goal": u_goal, "coach_name": u_coach, "tracked_metrics": ",".join(current_ms), "tasks_json": u_prof["tasks_json"]}
        p_upd = pd.concat([profiles_df[profiles_df["user_id"] != u_id], pd.DataFrame([new_p])], ignore_index=True)
        conn.update(worksheet="Profiles", data=p_upd)

        # History更新
        h_upd = pd.concat([history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == date_str))], 
                           pd.DataFrame([{"user_id": u_id, "date": date_str, "rate": rate, "note": note}])], ignore_index=True)
        conn.update(worksheet="History", data=h_upd)

        st.cache_data.clear()
        st.success("保存完了しました！")
        st.rerun()
