import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# --- [Phase 1] モバイル表示対策CSS ---
st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { background-color: white !important; color: black !important; }
    h1, h2, h3, p, span, label, .stMarkdown { color: black !important; }
    button, div.stButton > button, div.stFormSubmitButton > button { 
        background-color: white !important; color: black !important; border: 2px solid black !important; border-radius: 8px !important; 
    }
    div[data-baseweb="select"] > div, ul[role="listbox"], li[role="option"] { background-color: white !important; color: black !important; }
    input, textarea { 
        background-color: white !important; color: black !important; border: 1px solid black !important; -webkit-text-fill-color: black !important; 
    }
    </style>
    """, unsafe_allow_html=True)

# --- [Phase 2] データ連携ロジック ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_all_data():
    """全シートのデータを読み込む関数"""
    try:
        p = conn.read(worksheet="Profiles", ttl=0)
        s = conn.read(worksheet="Settings", ttl=0)
        h = conn.read(worksheet="History", ttl=0)
        m = conn.read(worksheet="Metrics", ttl=0)
        return p, s, h, m
    except Exception as e:
        st.error(f"シートの読み込みに失敗しました: {e}")
        return [pd.DataFrame()] * 4

profiles_df, settings_df, history_df, metrics_df = get_all_data()

st.title("🏀 バスケットボール練習管理システム")

# 1. ユーザー選択・新規登録
user_list = profiles_df["user_id"].unique().tolist() if not profiles_df.empty else []
selected_user = st.selectbox("👤 ユーザーを選択", options=["新規登録"] + user_list)

# 選択されたユーザーの情報を抽出
is_new = selected_user == "新規登録"
u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0] if not is_new else pd.Series()

# --- 2. プロフィールとカスタマイズ項目（Profiles / Settings） ---
with st.expander("🛠️ ユーザー設定・項目カスタマイズ", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=u_prof.get("user_id", ""))
    col1, col2 = st.columns(2)
    height = col1.number_input("身長 (cm)", value=float(u_prof.get("height", 0.0)))
    weight = col2.number_input("体重 (kg)", value=float(u_prof.get("weight", 0.0)))
    
    goal = st.text_area("現在の目標 (goal)", value=u_prof.get("goal", ""))
    coach = st.text_input("担当コーチ (coach_name)", value=u_prof.get("coach_name", ""))
    
    # 記録する項目の整理（tracked_metricsはカンマ区切りで保存されている想定）
    metrics_str = st.text_input("計測項目（カンマ区切り）", value=u_prof.get("tracked_metrics", "シュート率,ハンドリング"))

# --- 3. 今日の練習記録（History / Metrics） ---
import json # JSON解析用に追加

# --- (前略：CSSとデータ読み込みロジックは継承) ---

# ユーザーが選択された後の処理
if not is_new:
    st.divider() # 区切り線
    
    # --- 1. ロードマップの表示 (roadmap列) ---
    st.subheader("🏁 成長ロードマップ")
    roadmap_text = u_prof.get("roadmap", "ロードマップが設定されていません。")
    st.info(roadmap_text) # 青いボックスで目立たせる

    # --- 2. 今日の練習メニュー (tasks_json列) ---
    st.subheader("📋 今日の練習タスク")
    tasks_raw = u_prof.get("tasks_json", "[]")
    
    try:
        # JSON文字列をリストに変換
        tasks_list = json.loads(tasks_raw)
        
        if not tasks_list:
            st.write("今日のタスクはありません。")
        else:
            # チェックボックスとして表示
            for i, task in enumerate(tasks_list):
                # 個別のタスクをチェックボックス化
                st.checkbox(task, key=f"task_{i}")
                
    except Exception as e:
        st.error("タスクの読み込みに失敗しました。形式が正しいか確認してください。")
        st.write(f"現在の値: {tasks_raw}")

    st.divider()

# --- (後略：今日の記録セクションと保存ボタン) ---
st.subheader("📝 今日の記録")
today_date = datetime.now().strftime("%Y-%m-%d")

rate = st.slider("自己評価 (rate)", 1, 5, 3)
note = st.text_area("今日頑張ったこと (note)")

# 動的に計測項目の入力欄を作成
metric_values = {}
for m_name in metrics_str.split(","):
    m_name = m_name.strip()
    if m_name:
        metric_values[m_name] = st.number_input(f"{m_name} の結果", value=0.0)

# --- 4. 保存アクション ---
if st.button("設定と記録を保存する"):
    # A. Profilesシートの更新
    new_profile = {
        "user_id": u_id, "height": height, "weight": weight, "goal": goal,
        "coach_name": coach, "tracked_metrics": metrics_str,
        "line_enabled": u_prof.get("line_enabled", False) # 既存値を保持
    }
    p_upd = profiles_df[profiles_df["user_id"] != u_id] # 既存行を削除して差し替え
    profiles_df = pd.concat([p_upd, pd.DataFrame([new_profile])], ignore_index=True)
    
    # B. Historyシートへの追加（1回分）
    new_history = pd.DataFrame([{
        "user_id": u_id, "date": today_date, "rate": rate, "note": note
    }])
    history_df = pd.concat([history_df, new_history], ignore_index=True)
    
    # C. Metricsシートへの追加（項目数分）
    new_metrics_rows = []
    for name, val in metric_values.items():
        new_metrics_rows.append({"user_id": u_id, "date": today_date, "metric_name": name, "value": val})
    metrics_df = pd.concat([metrics_df, pd.DataFrame(new_metrics_rows)], ignore_index=True)

    # 全シートを更新
    conn.update(worksheet="Profiles", data=profiles_df)
    conn.update(worksheet="History", data=history_df)
    conn.update(worksheet="Metrics", data=metrics_df)
    
    st.success("全てのデータを適切なシートに保存しました！")
    st.balloons()

