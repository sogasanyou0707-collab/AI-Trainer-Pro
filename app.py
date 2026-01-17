import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime

# ==========================================
# 1. ページ設定 & モバイル表示対策CSS
# ==========================================
st.set_page_config(page_title="バスケ練習管理", layout="wide")

st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: white !important;
        color: black !important;
    }
    h1, h2, h3, p, span, label, li, .stMarkdown {
        color: black !important;
    }
    button, div.stButton > button, div.stFormSubmitButton > button {
        background-color: white !important;
        color: black !important;
        border: 2px solid black !important;
        border-radius: 8px !important;
        font-weight: bold !important;
    }
    div[data-baseweb="select"] > div, ul[role="listbox"], li[role="option"] {
        background-color: white !important;
        color: black !important;
    }
    input, textarea, div[data-baseweb="input"] {
        background-color: white !important;
        color: black !important;
        border: 1px solid black !important;
        -webkit-text-fill-color: black !important;
    }
    .stSlider { color: black !important; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. Google Sheets 接続 & データ読み込み
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)

def load_all_sheets():
    try:
        p = conn.read(worksheet="Profiles", ttl=0)
        s = conn.read(worksheet="Settings", ttl=0)
        h = conn.read(worksheet="History", ttl=0)
        m = conn.read(worksheet="Metrics", ttl=0)
        return p, s, h, m
    except Exception as e:
        st.error(f"シートの読み込みに失敗しました: {e}")
        return [pd.DataFrame()] * 4

profiles_df, settings_df, history_df, metrics_df = load_all_sheets()

# ==========================================
# 3. メインUI：ユーザーと日付の選択
# ==========================================
st.title("🏀 バスケ練習管理システム")

col_user, col_date = st.columns(2)

with col_user:
    user_list = profiles_df["user_id"].dropna().unique().tolist() if not profiles_df.empty else []
    selected_user = st.selectbox("👤 ユーザーを選択", options=["新規登録"] + user_list)

with col_date:
    selected_date = st.date_input("📅 記録日を選択", value=datetime.now())
    target_date_str = selected_date.strftime("%Y-%m-%d")

is_new = selected_user == "新規登録"
u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0] if not is_new else pd.Series()

# --- 記録の有無を確認し、ステータスを表示 ---
existing_history = pd.Series()
existing_metrics = pd.DataFrame()
record_found = False

if not is_new:
    if not history_df.empty:
        h_match = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == target_date_str)]
        if not h_match.empty:
            existing_history = h_match.iloc[-1]
            record_found = True
    
    if not metrics_df.empty:
        existing_metrics = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == target_date_str)]

# ステータス表示（結果が入っているかどうかの視認性を向上）
if not is_new:
    if record_found:
        st.success(f"✅ {target_date_str} の記録が既に入力されています")
    else:
        st.info(f"ℹ️ {target_date_str} の記録はまだありません")

# ==========================================
# 4. ユーザー詳細設定（ロードマップの上に配置）
# ==========================================
with st.expander("⚙️ ユーザー詳細設定・項目カスタマイズ", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=str(u_prof.get("user_id", "")) if pd.notna(u_prof.get("user_id")) else "")
    c_h, c_w = st.columns(2)
    h_val = c_h.number_input("身長 (cm)", value=float(u_prof.get("height", 0.0)) if pd.notna(u_prof.get("height")) else 0.0)
    w_val = c_w.number_input("体重 (kg)", value=float(u_prof.get("weight", 0.0)) if pd.notna(u_prof.get("weight")) else 0.0)
    
    goal_val = st.text_area("現在の目標", value=str(u_prof.get("goal", "")) if pd.notna(u_prof.get("goal")) else "")
    coach_val = st.text_input("担当コーチ", value=str(u_prof.get("coach_name", "")) if pd.notna(u_prof.get("coach_name")) else "")
    
    raw_metrics = u_prof.get("tracked_metrics")
    metrics_str = st.text_input("計測項目（カンマ区切り）", 
                                value=str(raw_metrics) if pd.notna(raw_metrics) else "シュート率,ハンドリング")

# ==========================================
# 5. ロードマップ & 今日のタスク表示（達成率を追加）
# ==========================================
done_tasks = [] 
if not is_new:
    st.divider()
    st.subheader("🏁 成長ロードマップ")
    raw_roadmap = u_prof.get("roadmap")
    st.info(raw_roadmap if pd.notna(raw_roadmap) and raw_roadmap != "" else "ロードマップが設定されていません。")

    st.subheader("📋 今日の練習タスク")
    tasks_raw = u_prof.get("tasks_json")
    if pd.isna(tasks_raw) or tasks_raw == "" or tasks_raw == "[]":
        st.write("今日のタスクは設定されていません。")
    else:
        try:
            tasks_list = json.loads(tasks_raw)
            total_tasks = len(tasks_list)
            
            # タスク一覧とチェックボックス
            for i, task in enumerate(tasks_list):
                if st.checkbox(task, key=f"task_{i}"):
                    done_tasks.append(task)
            
            # --- タスク達成率の表示 ---
            if total_tasks > 0:
                completion_rate = int((len(done_tasks) / total_tasks) * 100)
                st.write(f"📊 **タスク達成率: {completion_rate}%**")
                st.progress(completion_rate / 100)
                
        except:
            st.error("⚠️ tasks_json の形式エラー")
    st.divider()

# ==========================================
# 6. 今日の記録入力
# ==========================================
st.subheader(f"📝 {target_date_str} の振り返り")

default_rate = int(existing_history.get("rate", 3)) if pd.notna(existing_history.get("rate")) else 3
default_note = str(existing_history.get("note", "")) if pd.notna(existing_history.get("note")) else ""

rate = st.slider("自己評価 (rate)", 1, 5, default_rate)
user_note = st.text_area("今日頑張ったこと (note)", value=default_note)

metric_inputs = {}
if metrics_str:
    for m_name in metrics_str.split(","):
        m_name = m_name.strip()
        if m_name:
            prev_val = 0.0
            if not existing_metrics.empty:
                m_match = existing_metrics[existing_metrics["metric_name"] == m_name]
                if not m_match.empty:
                    prev_val = float(m_match.iloc[-1]["value"])
            metric_inputs[m_name] = st.number_input(f"{m_name} の結果", value=prev_val)

# ==========================================
# 7. 保存ロジック
# ==========================================
if st.button("設定と記録を保存する"):
    if not u_id:
        st.error("ユーザーIDを入力してください。")
    else:
        try:
            # A. Profiles更新
            new_profile = {
                "user_id": u_id, "height": h_val, "weight": w_val, "goal": goal_val,
                "coach_name": coach_val, "tracked_metrics": metrics_str,
                "roadmap": u_prof.get("roadmap") if not is_new else "",
                "tasks_json": u_prof.get("tasks_json") if not is_new else "[]"
            }
            p_df_clean = profiles_df[profiles_df["user_id"] != u_id] if not profiles_df.empty else pd.DataFrame()
            updated_profiles = pd.concat([p_df_clean, pd.DataFrame([new_profile])], ignore_index=True)

            # B. History追加
            tasks_summary = "\n[完了タスク]: " + ", ".join(done_tasks) if done_tasks else ""
            full_note = user_note + tasks_summary
            h_df_clean = history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == target_date_str))]
            new_history = pd.DataFrame([{
                "user_id": u_id, "date": target_date_str, "rate": rate, "note": full_note, "coach_comment": ""
            }])
            updated_history = pd.concat([h_df_clean, new_history], ignore_index=True)

            # C. Metrics追加
            m_df_clean = metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == target_date_str))]
            new_m_list = []
            for name, val in metric_inputs.items():
                new_m_list.append({"user_id": u_id, "date": target_date_str, "metric_name": name, "value": val})
            updated_metrics = pd.concat([m_df_clean, pd.DataFrame(new_m_list)], ignore_index=True)

            conn.update(worksheet="Profiles", data=updated_profiles)
            conn.update(worksheet="History", data=updated_history)
            conn.update(worksheet="Metrics", data=updated_metrics)
            
            st.success(f"保存完了！")
            st.balloons()
            
        except Exception as e:
            st.error(f"保存エラー: {e}")
