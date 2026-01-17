import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime

# ==========================================
# 1. ページ設定 & [Phase 1] モバイル表示対策CSS
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
# 3. メインUI：ユーザー選択
# ==========================================
st.title("🏀 バスケ練習管理システム")

user_list = []
if not profiles_df.empty and "user_id" in profiles_df.columns:
    user_list = profiles_df["user_id"].dropna().unique().tolist()

selected_user = st.selectbox("👤 ユーザーを選択", options=["新規登録"] + user_list)

is_new = selected_user == "新規登録"
u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0] if not is_new else pd.Series()

# ==========================================
# 4. [Phase 2] ロードマップ & 今日のタスク表示
# ==========================================
done_tasks = [] 

if not is_new:
    st.divider()
    st.subheader("🏁 成長ロードマップ")
    raw_roadmap = u_prof.get("roadmap")
    roadmap_text = raw_roadmap if pd.notna(raw_roadmap) and raw_roadmap != "" else "ロードマップが設定されていません。"
    st.info(roadmap_text)

    st.subheader("📋 今日の練習タスク")
    tasks_raw = u_prof.get("tasks_json")
    
    if pd.isna(tasks_raw) or tasks_raw == "" or tasks_raw == "[]":
        st.write("今日のタスクは設定されていません。")
    else:
        try:
            tasks_list = json.loads(tasks_raw)
            for i, task in enumerate(tasks_list):
                if st.checkbox(task, key=f"task_{i}"):
                    done_tasks.append(task)
        except:
            st.error("⚠️ tasks_json の形式エラー")
    st.divider()

# ==========================================
# 5. 設定・プロフィール編集
# ==========================================
with st.expander("⚙️ ユーザー詳細設定・項目カスタマイズ", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=str(u_prof.get("user_id", "")) if pd.notna(u_prof.get("user_id")) else "")
    col1, col2 = st.columns(2)
    height = col1.number_input("身長 (cm)", value=float(u_prof.get("height", 0.0)) if pd.notna(u_prof.get("height")) else 0.0)
    weight = col2.number_input("体重 (kg)", value=float(u_prof.get("weight", 0.0)) if pd.notna(u_prof.get("weight")) else 0.0)
    
    goal = st.text_area("現在の目標", value=str(u_prof.get("goal", "")) if pd.notna(u_prof.get("goal")) else "")
    coach = st.text_input("担当コーチ", value=str(u_prof.get("coach_name", "")) if pd.notna(u_prof.get("coach_name")) else "")
    
    raw_metrics = u_prof.get("tracked_metrics")
    metrics_str = st.text_input("計測項目（カンマ区切り）", 
                                value=str(raw_metrics) if pd.notna(raw_metrics) else "シュート率,ハンドリング")

# ==========================================
# 6. 今日の記録入力
# ==========================================
st.subheader("📝 今日の振り返り")
today_date = datetime.now().strftime("%Y-%m-%d")

rate = st.slider("自己評価 (rate)", 1, 5, 3)
user_note = st.text_area("今日頑張ったこと (note)")

metric_inputs = {}
if metrics_str:
    for m_name in metrics_str.split(","):
        m_name = m_name.strip()
        if m_name:
            metric_inputs[m_name] = st.number_input(f"{m_name} の結果", value=0.0)

# ==========================================
# 7. 保存ロジック（ここが line 150 付近です）
# ==========================================
if st.button("設定と記録を保存する"):
    if not u_id:
        st.error("ユーザーIDを入力してください。")
    else:
        try:
            # A. Profilesの更新
            new_profile_data = {
                "user_id": u_id, 
                "height": height, 
                "weight": weight, 
                "goal": goal,
                "coach_name": coach, 
                "tracked_metrics": metrics_str,
                "roadmap": u_prof.get("roadmap") if not is_new else "",
                "tasks_json": u_prof.get("tasks_json") if not is_new else "[]"
            }
            p_df_clean = profiles_df[profiles_df["user_id"] != u_id] if not profiles_df.empty else pd.DataFrame()
            updated_profiles = pd.concat([p_df_clean, pd.DataFrame([new_profile_data])], ignore_index=True)

            # B. Historyへの追加
            tasks_summary = "\n[完了タスク]: " + ", ".join(done_tasks) if done_tasks else ""
            full_note = user_note + tasks_summary
            
            new_history = pd.DataFrame([{
                "user_id": u_id, 
                "date": today_date, 
                "rate": rate, 
                "note": full_note,
                "coach_comment": ""
            }])
            updated_history = pd.concat([history_df, new_history], ignore_index=True)

            # C. Metricsへの追加
            new_metrics_list = []
            for name, val in metric_inputs.items():
                new_metrics_list.append({
                    "user_id": u_id, 
                    "date": today_date, 
                    "metric_name": name, 
                    "value": val
                })
            updated_metrics = pd.concat([metrics_df, pd.DataFrame(new_metrics_list)], ignore_index=True)

            # --- 保存実行 ---
            conn.update(worksheet="Profiles", data=updated_profiles)
            conn.update(worksheet="History", data=updated_history)
            conn.update(worksheet="Metrics", data=updated_metrics)
            
            st.success("全てのデータを保存しました！")
            st.balloons()
            
        except Exception as e:
            st.error(f"保存エラー: {e}")
