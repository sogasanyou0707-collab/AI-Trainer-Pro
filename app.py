import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import requests
import google.generativeai as genai
from datetime import datetime
import os

# ==========================================
# 1. ページ設定 & 視認性改善CSS
# ==========================================
st.set_page_config(page_title="AI Trainer Pro", layout="centered")

st.markdown("""
    <style>
    /* 全体を白背景・黒文字に固定 */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: white !important; color: black !important;
    }
    h1, h2, h3, p, span, label, li, .stMarkdown { color: black !important; }
    
    /* ボタンデザイン */
    button, div.stButton > button { 
        background-color: white !important; color: black !important; 
        border: 2px solid black !important; border-radius: 8px !important; 
        font-weight: bold !important;
    }
    
    /* 【視認性改善】プルダウン(Selectbox)の背景を白、文字を黒に強制 */
    div[data-baseweb="select"] > div, div[role="listbox"], li[role="option"] {
        background-color: white !important; color: black !important;
    }
    
    /* 入力エリア */
    input, textarea, div[data-baseweb="input"] { 
        background-color: white !important; color: black !important; border: 1px solid black !important; 
    }
    .stProgress > div > div > div > div { background-color: black !important; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 接続 & データ読み込み (成功事例と同じ ttl=0)
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)

def load_all_sheets():
    try:
        # 成功事例と同様、ttl=0で常に最新を読み込む
        p = conn.read(worksheet="Profiles", ttl=0)
        h = conn.read(worksheet="History", ttl=0)
        m = conn.read(worksheet="Metrics", ttl=0)
        return p, h, m
    except Exception as e:
        st.error(f"シートの読み込みに失敗しました: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

profiles_df, history_df, metrics_df = load_all_sheets()

# ==========================================
# 3. メインUI：ユーザー & 日付選択
# ==========================================
st.title("🏀 AI Trainer Pro")

col_u, col_d = st.columns(2)
with col_u:
    user_list = profiles_df["user_id"].dropna().unique().tolist() if not profiles_df.empty else []
    selected_user = st.selectbox("👤 ユーザー選択", options=["新規登録"] + user_list)
with col_d:
    selected_date = st.date_input("📅 記録日", value=datetime.now())
    target_date_str = selected_date.strftime("%Y-%m-%d")

is_new = selected_user == "新規登録"
u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0] if not is_new and not profiles_df.empty else pd.Series()

# --- 過去データの検索 (成功事例のロジックを完全再現) ---
existing_history = pd.Series()
existing_metrics = pd.DataFrame()
if not is_new:
    if not history_df.empty:
        # 日付形式の一致をより確実にするため、一旦文字列で比較
        history_df["date"] = history_df["date"].astype(str)
        h_match = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == target_date_str)]
        if not h_match.empty: existing_history = h_match.iloc[-1]
    if not metrics_df.empty:
        metrics_df["date"] = metrics_df["date"].astype(str)
        existing_metrics = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == target_date_str)]

# ==========================================
# 4. サイドバー設定 (LINE情報の反映)
# ==========================================
with st.sidebar:
    st.header("⚙️ システム設定")
    
    # ProfilesシートのE, F列から読み込んだ情報を表示・編集枠に反映
    st.subheader("LINE連携情報")
    l_token = st.text_input("LINE Token", value=str(u_prof.get("line_token", "")), type="password")
    l_user_id = st.text_input("LINE User ID", value=str(u_prof.get("line_user_id", "")))
    
    st.divider()
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    ms = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    st.session_state.sel_model = st.selectbox("AI Model", ms, index=0)

# ==========================================
# 5. 詳細設定 (項目追加・削除を分離)
# ==========================================
with st.expander("⚙️ 詳細設定（プロフィール・項目管理）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=str(u_prof.get("user_id", "")))
    u_goal = st.text_area("現在の目標", value=str(u_prof.get("goal", "")))
    
    coach_opts = ["安西先生", "熱血タイプ", "論理タイプ"]
    u_coach = st.selectbox("担当コーチ", options=coach_opts, 
                           index=coach_opts.index(u_prof.get("coach_name")) if u_prof.get("coach_name") in coach_opts else 0)

    # 現在の計測項目
    m_str = st.text_input("現在の計測項目（カンマ区切り）", value=str(u_prof.get("tracked_metrics", "シュート率,ハンドリング")))
    m_list = [m.strip() for m in m_str.split(",") if m.strip()]

    st.write("---")
    col_add, col_del = st.columns(2)
    with col_add:
        st.subheader("➕ 項目の追加")
        add_name = st.text_input("追加したい項目名")
        if st.button("追加を実行"):
            if add_name and add_name not in m_list:
                m_list.append(add_name)
                m_str = ",".join(m_list)
                st.rerun()

    with col_del:
        st.subheader("➖ 項目の削除")
        del_target = st.selectbox("削除する項目", options=["選択してください"] + m_list)
        if st.button("削除を実行"):
            if del_target != "選択してください":
                m_list.remove(del_target)
                m_str = ",".join(m_list)
                st.rerun()

# ==========================================
# 6. 本日のメニュー (タスク達成率)
# ==========================================
st.divider()
st.subheader("📋 本日の練習メニュー")
tasks = ["シュート 50本", "ハンドリング 10分", "フットワーク", "対人練習"]
done_count = 0
for t in tasks:
    if st.checkbox(t):
        done_count += 1

achieve_rate = int((done_count / len(tasks)) * 100)
st.progress(achieve_rate / 100)
st.write(f"達成率: **{achieve_rate}%**")

# ==========================================
# 7. 振り返り入力 (成功事例のロジック完全再現)
# ==========================================
st.divider()
st.subheader(f"📝 {target_date_str} の振り返り")

try: def_rate = int(float(existing_history.get("rate", 3)))
except: def_rate = 3
rate = st.slider("自己評価", 1, 5, def_rate)
note = st.text_area("練習内容・気づき", value=str(existing_history.get("note", "")), height=150)

# --- 成功事例の数値反映ロジック ---

metric_inputs = {}
if m_str:
    for m_name in m_str.split(","):
        m_name = m_name.strip()
        if m_name:
            prev_val = 0.0
            if not existing_metrics.empty:
                # 成功事例と全く同じ検索コード
                m_match = existing_metrics[existing_metrics["metric_name"] == m_name]
                if not m_match.empty:
                    try: prev_val = float(m_match.iloc[-1]["value"])
                    except: prev_val = 0.0
            metric_inputs[m_name] = st.number_input(f"{m_name} の結果", value=prev_val, key=f"inp_{m_name}")

# ==========================================
# 8. 保存 & LINE送信 (データ保護維持)
# ==========================================
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        with st.spinner("処理中..."):
            # Profiles更新 (E/F列のトークン情報を守るための部分更新)
            p_latest = conn.read(worksheet="Profiles", ttl=0)
            new_p_data = {
                "user_id": u_id, "goal": u_goal, "coach_name": u_coach, 
                "tracked_metrics": m_str, "line_token": l_token, "line_user_id": l_user_id
            }
            if u_id in p_latest["user_id"].astype(str).values:
                idx = p_latest[p_latest["user_id"].astype(str) == u_id].index[0]
                for k, v in new_p_data.items(): p_latest.at[idx, k] = v
                final_p = p_latest
            else:
                final_p = pd.concat([p_latest, pd.DataFrame([new_p_data])], ignore_index=True)

            # 更新実行
            conn.update(worksheet="Profiles", data=final_p)
            conn.update(worksheet="History", data=pd.concat([history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == target_date_str))], pd.DataFrame([{"user_id": u_id, "date": target_date_str, "rate": rate, "note": note}])], ignore_index=True))
            conn.update(worksheet="Metrics", data=pd.concat([metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == target_date_str))], pd.DataFrame([{"user_id": u_id, "date": target_date_str, "metric_name": k, "value": v} for k, v in metric_inputs.items()])], ignore_index=True))

            # LINE送信 (サイドバーの最新値を使用)
            if l_token and l_user_id:
                m_txt = "\n".join([f"・{k}: {v}" for k, v in metric_inputs.items()])
                line_msg = f"【練習報告】{target_date_str}\n達成率: {achieve_rate}%\n評価: {int(rate)}\n内容: {str(note)}\n\n[数値]\n{m_txt}"
                requests.post("https://api.line.me/v2/bot/message/push", headers={"Authorization": f"Bearer {l_token}", "Content-Type": "application/json"}, json={"to": str(l_user_id), "messages": [{"type": "text", "text": line_msg}]})
            
            st.success("全て完了しました！")
            st.rerun()
