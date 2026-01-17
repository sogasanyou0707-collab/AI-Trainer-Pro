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
        font-weight: bold !important;
    }
    input, textarea, div[data-baseweb="input"], div[data-baseweb="select"] > div {
        background-color: white !important;
        color: black !important;
        border: 1px solid black !important;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 接続 & データ読み込み
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)

def get_data():
    try:
        p = conn.read(worksheet="Profiles", ttl=0)
        h = conn.read(worksheet="History", ttl=0)
        m = conn.read(worksheet="Metrics", ttl=0)
        # コーチリスト取得用。Settingsシートがない場合は空のリスト
        try:
            s = conn.read(worksheet="Settings", ttl=0)
            coach_list = s["coach_names"].dropna().tolist() if "coach_names" in s.columns else []
        except:
            coach_list = p["coach_name"].dropna().unique().tolist() if not p.empty else []
        return p, h, m, coach_list
    except Exception as e:
        st.error(f"データ読み込み失敗: {e}")
        return [pd.DataFrame()] * 3, []

profiles_df, history_df, metrics_df, coach_list = get_data()

# ==========================================
# 3. メインUI：ユーザー & カレンダー
# ==========================================
st.title("🏀 AI Trainer Pro")

col_u, col_d = st.columns(2)
with col_u:
    existing_users = profiles_df["user_id"].dropna().unique().tolist() if not profiles_df.empty else []
    selected_user = st.selectbox("👤 ユーザー選択", options=["新規登録"] + existing_users)
with col_d:
    selected_date = st.date_input("📅 日付選択", value=datetime.now())
    date_str = selected_date.strftime("%Y-%m-%d")

# ユーザー情報の特定
is_new = selected_user == "新規登録"
if is_new:
    u_prof = {"user_id": "", "goal": "", "coach_name": "", "tracked_metrics": "シュート率,ハンドリング", "tasks_json": "[]"}
else:
    u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0].to_dict()

# 過去データの自動読み込み
existing_history = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == date_str)] if not is_new and not history_df.empty else pd.DataFrame()
existing_metrics = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == date_str)] if not is_new and not metrics_df.empty else pd.DataFrame()

if not existing_history.empty:
    st.success(f"✅ {date_str} の記録を読み込みました")

# ==========================================
# 4. 詳細設定 (ユーザープロフィール・項目管理)
# ==========================================
with st.expander("⚙️ 詳細設定（プロフィール・項目管理）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=u_prof["user_id"])
    u_goal = st.text_area("現在の目標", value=u_prof["goal"])
    
    # コーチ選択 (セレクトボックス)
    final_coach_list = sorted(list(set(coach_list + [u_prof["coach_name"]]))) if u_prof["coach_name"] else coach_list
    u_coach = st.selectbox("担当コーチ", options=final_coach_list, 
                           index=final_coach_list.index(u_prof["coach_name"]) if u_prof["coach_name"] in final_coach_list else 0)
    
    st.write("---")
    st.subheader("📊 数値項目のカスタマイズ")
    current_metrics = [m.strip() for m in str(u_prof["tracked_metrics"]).split(",") if m.strip()]
    
    # 項目の追加 (フリー入力)
    new_metric = st.text_input("追加したい項目名 (例: 体力)")
    if st.button("項目を追加"):
        if new_metric and new_metric not in current_metrics:
            current_metrics.append(new_metric)
            u_prof["tracked_metrics"] = ",".join(current_metrics)
            st.success(f"{new_metric} を追加しました。保存ボタンを押すと確定します。")
    
    # 項目の削除 (プルダウン)
    if current_metrics:
        del_metric = st.selectbox("削除したい項目を選択", options=["選択してください"] + current_metrics)
        if st.button("項目を削除"):
            if del_metric in current_metrics:
                current_metrics.remove(del_metric)
                u_prof["tracked_metrics"] = ",".join(current_metrics)
                st.warning(f"{del_metric} を削除しました。保存ボタンを押すと確定します。")
    
    st.info(f"現在の項目: {', '.join(current_metrics)}")

# ==========================================
# 5. 練習タスク & 記録入力
# ==========================================
st.divider()
st.subheader("📋 今日の練習タスク")
done_tasks = []
try:
    tasks_list = json.loads(u_prof.get("tasks_json", "[]"))
    for i, t in enumerate(tasks_list):
        if st.checkbox(t, key=f"task_{i}"):
            done_tasks.append(t)
except: st.write("タスク未設定")

st.subheader(f"📝 {date_str} の振り返り")
rate = st.slider("自己評価", 1, 5, int(existing_history["rate"].iloc[0]) if not existing_history.empty else 3)
note = st.text_area("内容・気づき", value=existing_history["note"].iloc[0] if not existing_history.empty else "", height=150)

# 数値計測入力
metric_results = {}
for m_name in current_metrics:
    val_init = 0.0
    if not existing_metrics.empty:
        m_match = existing_metrics[existing_metrics["metric_name"] == m_name]
        if not m_match.empty: val_init = float(m_match["value"].iloc[0])
    metric_results[m_name] = st.number_input(f"{m_name} の結果", value=val_init)

# ==========================================
# 6. 保存・送信・AIコーチング
# ==========================================
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        with st.spinner("保存中..."):
            # Profiles更新 (tracked_metrics含む)
            new_p_data = {
                "user_id": u_id, "goal": u_goal, "coach_name": u_coach, 
                "tracked_metrics": ",".join(current_metrics), "tasks_json": u_prof["tasks_json"],
                "line_token": u_prof.get("line_token", ""), "line_user_id": u_prof.get("line_user_id", "")
            }
            p_df_clean = profiles_df[profiles_df["user_id"] != u_id] if not profiles_df.empty else pd.DataFrame()
            updated_profiles = pd.concat([p_df_clean, pd.DataFrame([new_p_data])], ignore_index=True)
            conn.update(worksheet="Profiles", data=updated_profiles)

            # History更新 (上書き)
            h_df_clean = history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == date_str))] if not history_df.empty else pd.DataFrame()
            new_h_data = {"user_id": u_id, "date": date_str, "rate": rate, "note": note}
            updated_history = pd.concat([h_df_clean, pd.DataFrame([new_h_data])], ignore_index=True)
            conn.update(worksheet="History", data=updated_history)

            # Metrics更新
            m_df_clean = metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == date_str))] if not metrics_df.empty else pd.DataFrame()
            m_rows = [{"user_id": u_id, "date": date_str, "metric_name": k, "value": v} for k, v in metric_results.items()]
            updated_metrics = pd.concat([m_df_clean, pd.DataFrame(m_rows)], ignore_index=True)
            conn.update(worksheet="Metrics", data=updated_metrics)

            # LINE送信 (SecretsのE, F列情報があれば実行)
            st.success("保存完了しました！")
            st.rerun()

# AIモデル選択 (1.5系除外)
with st.sidebar:
    st.header("⚙️ システム設定")
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    sel_model = st.selectbox("使用AIモデル", models, index=0)
    
    if st.button("💡 AIコーチのアドバイス"):
        model = genai.GenerativeModel(sel_model)
        prompt = f"バスケコーチとして、目標「{u_goal}」を持つ選手へのアドバイスを3つください。本日の内容: {note}"
        st.info(model.generate_content(prompt).text)
