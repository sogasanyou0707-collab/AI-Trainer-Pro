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
    }
    input, textarea, div[data-baseweb="input"], div[data-baseweb="select"] > div {
        background-color: white !important;
        color: black !important;
        border: 1px solid black !important;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 接続 & キャッシュ管理
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)

def load_local_config():
    if os.path.exists("app_settings.json"):
        with open("app_settings.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {"selected_model": "gemini-3-pro"}

def save_local_config(cfg):
    with open("app_settings.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

# ==========================================
# 3. データ読み込み
# ==========================================
def get_data():
    p = conn.read(worksheet="Profiles", ttl=0)
    h = conn.read(worksheet="History", ttl=0)
    m = conn.read(worksheet="Metrics", ttl=0)
    return p, h, m

profiles_df, history_df, metrics_df = get_data()

# ==========================================
# 4. メインUI：ユーザー & カレンダー
# ==========================================
st.title("🏀 AI Trainer Pro")

col_u, col_d = st.columns(2)
with col_u:
    user_list = profiles_df["user_id"].dropna().unique().tolist() if not profiles_df.empty else []
    selected_user = st.selectbox("👤 ユーザー", options=["新規登録"] + user_list)
with col_d:
    selected_date = st.date_input("📅 日付選択", value=datetime.now())
    date_str = selected_date.strftime("%Y-%m-%d")

# --- 新規ユーザー または 既存ユーザーの判定 ---
is_new = selected_user == "新規登録"
if is_new:
    u_prof = pd.Series({"user_id": "", "goal": "", "coach_name": "", "tracked_metrics": "シュート率,ハンドリング", "tasks_json": "[]"})
else:
    u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0]

# ==========================================
# 5. 過去データの取得ロジック
# ==========================================
existing_history = pd.Series()
existing_metrics = pd.DataFrame()

if not is_new and not history_df.empty:
    h_match = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == date_str)]
    if not h_match.empty:
        existing_history = h_match.iloc[-1]
        st.success(f"✅ {date_str} の記録を読み込みました")

if not is_new and not metrics_df.empty:
    existing_metrics = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == date_str)]

# ==========================================
# 6. 詳細設定 (ユーザー情報・項目の編集)
# ==========================================
with st.expander("⚙️ ユーザープロフィール・項目の追加削除", expanded=is_new):
    u_id = st.text_input("ユーザーID (保存用)", value=str(u_prof["user_id"]))
    u_goal = st.text_area("現在の目標", value=str(u_prof["goal"]))
    u_coach = st.text_input("担当コーチ", value=str(u_prof["coach_name"]))
    u_metrics_str = st.text_input("計測項目 (カンマ区切りで追加/削除)", value=str(u_prof["tracked_metrics"]))

# ==========================================
# 7. 今日のタスク (Profilesから取得)
# ==========================================
st.divider()
st.subheader("📋 今日の練習タスク")
done_tasks = []
try:
    tasks_list = json.loads(u_prof.get("tasks_json", "[]"))
    if tasks_list:
        for i, t in enumerate(tasks_list):
            if st.checkbox(t, key=f"t_{i}"):
                done_tasks.append(t)
    else:
        st.caption("タスクは設定されていません")
except:
    st.error("タスク形式エラー")

# ==========================================
# 8. 記録入力 (過去データがあれば pre-fill)
# ==========================================
st.subheader(f"📝 {date_str} の振り返り")

rate = st.slider("自己評価", 1, 5, int(existing_history.get("rate", 3)))
note = st.text_area("内容・気づき", value=str(existing_history.get("note", "")))

# 動的な計測項目 (ハンドリング、シュート率など)
metric_results = {}
st.write("📊 数値計測")
for m_name in u_metrics_str.split(","):
    m_name = m_name.strip()
    if m_name:
        # 過去の数値があればそれを初期値に
        val_init = 0.0
        if not existing_metrics.empty:
            m_match = existing_metrics[existing_metrics["metric_name"] == m_name]
            if not m_match.empty:
                val_init = float(m_match.iloc[-1]["value"])
        
        metric_results[m_name] = st.number_input(f"{m_name} の結果", value=val_init)

# ==========================================
# 9. 保存 & 送信 & AIコーチング
# ==========================================
local_cfg = load_local_config()

if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        with st.spinner("保存中..."):
            # A. Profilesの更新 (新規・修正の両対応)
            new_p = {
                "user_id": u_id, "goal": u_goal, "coach_name": u_coach, 
                "tracked_metrics": u_metrics_str, "tasks_json": u_prof["tasks_json"],
                "line_token": u_prof.get("line_token", ""), "line_user_id": u_prof.get("line_user_id", "")
            }
            p_clean = profiles_df[profiles_df["user_id"] != u_id] if not profiles_df.empty else pd.DataFrame()
            updated_p = pd.concat([p_clean, pd.DataFrame([new_p])], ignore_index=True)
            conn.update(worksheet="Profiles", data=updated_p)

            # B. Historyの更新 (上書き保存)
            h_clean = history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == date_str))] if not history_df.empty else pd.DataFrame()
            new_h = {"user_id": u_id, "date": date_str, "rate": rate, "note": note}
            updated_h = pd.concat([h_clean, pd.DataFrame([new_h])], ignore_index=True)
            conn.update(worksheet="History", data=updated_h)

            # C. Metricsの更新
            m_clean = metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == date_str))] if not metrics_df.empty else pd.DataFrame()
            new_m_data = [{"user_id": u_id, "date": date_str, "metric_name": k, "value": v} for k, v in metric_results.items()]
            updated_m = pd.concat([m_clean, pd.DataFrame(new_m_data)], ignore_index=True)
            conn.update(worksheet="Metrics", data=updated_m)

            # LINE送信 (ProfilesのE, F列を使用)
            l_token = u_prof.get("line_token")
            l_id = u_prof.get("line_user_id")
            if l_token and l_id:
                msg = f"【AI Trainer】{date_str} 記録\nユーザー: {u_id}\n評価: {rate}\n内容: {note}"
                requests.post("https://api.line.me/v2/bot/message/push", headers={"Authorization": f"Bearer {l_token}", "Content-Type": "application/json"}, json={"to": l_id, "messages": [{"type": "text", "text": msg}]})
            
            st.success("スプレッドシートへの保存とLINE送信が完了しました！")
            st.balloons()

if st.button("🤖 AIコーチのアドバイスを受ける", use_container_width=True):
    if not note:
        st.warning("先に内容を入力してください")
    else:
        with st.spinner("AIコーチが思考中..."):
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel(local_cfg["selected_model"])
            prompt = f"あなたはバスケコーチです。目標「{u_goal}」を持つ選手が、本日「{note}」という練習をし、各数値は{metric_results}でした。具体的なアドバイスを3つください。"
            advice = model.generate_content(prompt).text
            st.markdown("### 💡 コーチのアドバイス")
            st.info(advice)

# ==========================================
# 10. サイドバー
# ==========================================
with st.sidebar:
    st.header("⚙️ システム設定")
    # Geminiモデル選択 (1.5系除外)
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    all_models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    
    current_m = local_cfg.get("selected_model", "gemini-3-pro")
    sel_m = st.selectbox("使用AIモデル", all_models, index=all_models.index(current_m) if current_m in all_models else 0)
    
    if sel_m != current_m:
        local_cfg["selected_model"] = sel_m
        save_local_config(local_cfg)
        st.rerun()

    if st.button("🔄 データを再読み込み"):
        st.rerun()
