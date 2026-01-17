import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime
import google.generativeai as genai

# ==========================================
# 1. ページ設定 & モバイル表示対策CSS
# ==========================================
st.set_page_config(page_title="バスケ練習管理 AI", layout="wide")

st.markdown("""
    <style>
    /* 全体の基本設定（白背景・黒文字） */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: white !important;
        color: black !important;
    }
    h1, h2, h3, p, span, label, li, .stMarkdown {
        color: black !important;
    }
    /* ボタンのスタイル */
    button, div.stButton > button, div.stFormSubmitButton > button {
        background-color: white !important;
        color: black !important;
        border: 2px solid black !important;
        border-radius: 8px !important;
        font-weight: bold !important;
    }
    /* セレクトボックス、入力欄、スライダーの視認性対策 */
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
# 2. 接続設定（GSheets & Gemini）
# ==========================================
# Google Sheets 接続 (secrets内の [connections.gsheets] を使用)
conn = st.connection("gsheets", type=GSheetsConnection)

# Gemini API の設定 (Secretsの GEMINI_API_KEY を使用)
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.warning("⚠️ Gemini APIキーの設定を確認してください。AIアドバイスは現在利用できません。")

def load_all_sheets():
    try:
        p = conn.read(worksheet="Profiles", ttl=0)
        h = conn.read(worksheet="History", ttl=0)
        m = conn.read(worksheet="Metrics", ttl=0)
        return p, h, m
    except Exception as e:
        st.error(f"シートの読み込みに失敗しました: {e}")
        return [pd.DataFrame()] * 3

profiles_df, history_df, metrics_df = load_all_sheets()

# ==========================================
# 3. メインUI：ユーザーと日付の選択
# ==========================================
st.title("🏀 AIコーチ・練習管理システム")

col_u, col_d = st.columns(2)
with col_u:
    user_list = profiles_df["user_id"].dropna().unique().tolist() if not profiles_df.empty else []
    selected_user = st.selectbox("👤 ユーザーを選択", options=["新規登録"] + user_list)

with col_d:
    selected_date = st.date_input("📅 記録日を選択", value=datetime.now())
    target_date_str = selected_date.strftime("%Y-%m-%d")

is_new = selected_user == "新規登録"
u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0] if not is_new else pd.Series()

# 既存記録の引き継ぎ確認
existing_history = pd.Series()
existing_metrics = pd.DataFrame()
if not is_new:
    if not history_df.empty:
        h_match = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == target_date_str)]
        if not h_match.empty:
            existing_history = h_match.iloc[-1]
    if not metrics_df.empty:
        existing_metrics = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == target_date_str)]

# 記録状況の視認化
if not is_new:
    if not existing_history.empty:
        st.success(f"✅ {target_date_str} の記録が既に入力されています")
    else:
        st.info(f"ℹ️ {target_date_str} の記録はまだありません")

# ==========================================
# 4. ユーザー詳細設定
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
# 5. ロードマップ & 今日のタスク（達成率表示）
# ==========================================
done_tasks = []
total_tasks = 0
if not is_new:
    st.divider()
    st.subheader("🏁 成長ロードマップ")
    st.info(u_prof.get("roadmap", "ロードマップが設定されていません。"))

    st.subheader("📋 今日の練習タスク")
    tasks_raw = u_prof.get("tasks_json", "[]")
    try:
        tasks_list = json.loads(tasks_raw)
        total_tasks = len(tasks_list)
        if total_tasks > 0:
            for i, task in enumerate(tasks_list):
                if st.checkbox(task, key=f"t_{i}"):
                    done_tasks.append(task)
            
            # タスク達成率の視覚化
            completion_rate = int((len(done_tasks) / total_tasks) * 100)
            st.write(f"📊 **タスク達成率: {completion_rate}%**")
            st.progress(completion_rate / 100)
        else:
            st.write("タスクが設定されていません。")
    except:
        st.error("⚠️ tasks_json の形式エラー")

# ==========================================
# 6. 今日の記録 & AIコーチのフィードバック表示
# ==========================================
st.divider()
st.subheader(f"📝 {target_date_str} の振り返り")

# 過去のAIアドバイスがあれば表示
if not existing_history.empty and pd.notna(existing_history.get("coach_comment")):
    with st.chat_message("assistant"):
        st.write("**コーチからのアドバイス:**")
        st.write(existing_history.get("coach_comment"))

rate = st.slider("自己評価 (rate)", 1, 5, int(existing_history.get("rate", 3)) if pd.notna(existing_history.get("rate")) else 3)
user_note = st.text_area("今日頑張ったこと (note)", value=str(existing_history.get("note", "")) if pd.notna(existing_history.get("note")) else "")

metric_inputs = {}
if metrics_str:
    m_names = metrics_str.split(",")
    cols = st.columns(len(m_names))
    for idx, m_name in enumerate(m_names):
        m_name = m_name.strip()
        if m_name:
            prev_val = 0.0
            if not existing_metrics.empty:
                m_match = existing_metrics[existing_metrics["metric_name"] == m_name]
                if not m_match.empty: prev_val = float(m_match.iloc[-1]["value"])
            
            with cols[idx]:
                metric_inputs[m_name] = st.number_input(f"{m_name}", value=prev_val)

# ==========================================
# 7. 保存 & AIアドバイス生成ロジック
# ==========================================
if st.button("設定と記録を保存してAIコーチを呼ぶ"):
    if not u_id:
        st.error("ユーザーIDを入力してください。")
    else:
        with st.spinner("AIコーチが今日の練習内容を確認しています..."):
            # A. AIアドバイスの生成
            prompt = f"""
            あなたはプロのバスケットボールコーチです。小学6年生の選手に対して、今日の練習記録をもとに、
            成長を促し、やる気を引き出す具体的なアドバイスを150文字程度で作成してください。
            
            【選手の目標】: {goal_val}
            【自己評価】: {rate}/5
            【今日頑張ったこと】: {user_note}
            【完了したタスク】: {', '.join(done_tasks)}
            【練習の数値】: {metric_inputs}
            """
            try:
                response = model.generate_content(prompt)
                ai_comment = response.text
            except:
                ai_comment = "今日はナイスチャレンジ！自分の決めたメニューをやり遂げたことが素晴らしい。明日も一歩ずつ進もう！"

            # B. 各シートの更新
            # Profiles更新
            new_p = {"user_id": u_id, "height": h_val, "weight": w_val, "goal": goal_val, "coach_name": coach_val, "tracked_metrics": metrics_str, "roadmap": u_prof.get("roadmap", ""), "tasks_json": tasks_raw}
            p_upd = pd.concat([profiles_df[profiles_df["user_id"] != u_id], pd.DataFrame([new_p])], ignore_index=True)

            # History更新 (AIコメント含む)
            tasks_sum = "\n[完了]: " + ", ".join(done_tasks) if done_tasks else ""
            new_h = {"user_id": u_id, "date": target_date_str, "rate": rate, "note": user_note + tasks_sum, "coach_comment": ai_comment}
            h_upd = pd.concat([history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == target_date_str))], pd.DataFrame([new_h])], ignore_index=True)

            # Metrics更新
            new_m_list = [{"user_id": u_id, "date": target_date_str, "metric_name": k, "value": v} for k, v in metric_inputs.items()]
            m_upd = pd.concat([metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == target_date_str))], pd.DataFrame(new_m_list)], ignore_index=True)

            # 書き込み実行
            conn.update(worksheet="Profiles", data=p_upd)
            conn.update(worksheet="History", data=h_upd)
            conn.update(worksheet="Metrics", data=m_upd)
            
            st.success(f"{target_date_str} のデータを保存しました。AIコーチからメッセージが届いています！")
            with st.chat_message("assistant"):
                st.write(ai_comment)
            st.balloons()
