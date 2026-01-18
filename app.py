import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import requests
import google.generativeai as genai
from datetime import datetime
import os

# ==========================================
# 1. ページ設定 & 視認性改善CSS (白基調・黒文字)
# ==========================================
st.set_page_config(page_title="AI Trainer Pro", layout="centered")

st.markdown("""
    <style>
    /* 全体の白基調設定 */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: white !important; color: black !important;
    }
    h1, h2, h3, p, span, label, li, .stMarkdown { color: black !important; }
    
    /* ボタンデザイン */
    button, div.stButton > button { 
        background-color: white !important; color: black !important; 
        border: 2px solid black !important; border-radius: 8px !important; 
    }
    
    /* 【視認性改善】プルダウン(Selectbox)の文字と背景色を強制固定 */
    div[data-baseweb="select"] > div {
        background-color: white !important;
        color: black !important;
        border: 1px solid black !important;
    }
    /* プルダウン内の選択肢リスト */
    ul[role="listbox"] {
        background-color: white !important;
    }
    li[role="option"] {
        color: black !important;
        background-color: white !important;
    }
    
    input, textarea, div[data-baseweb="input"] { 
        background-color: white !important; color: black !important; border: 1px solid black !important; 
    }
    .stProgress > div > div > div > div { background-color: black !important; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 接続 & データ読み込み (以前の成功ロジック: ttl=0)
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)

def load_all_sheets():
    try:
        # キャッシュを使わず、常に最新を読み込む(ttl=0)
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

# --- 過去データの検索 (成功時のロジック) ---
existing_history = pd.Series()
existing_metrics = pd.DataFrame()
if not is_new:
    if not history_df.empty:
        # シート側の日付形式に合わせるため型を文字列化
        history_df["date"] = history_df["date"].astype(str)
        h_match = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == target_date_str)]
        if not h_match.empty: existing_history = h_match.iloc[-1]
    if not metrics_df.empty:
        metrics_df["date"] = metrics_df["date"].astype(str)
        existing_metrics = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == target_date_str)]

# ==========================================
# 4. サイドバー設定 (LINE情報の表示と編集)
# ==========================================
with st.sidebar:
    st.header("⚙️ システム設定")
    
    # E列(line_token)とF列(line_user_id)をサイドバーで表示・編集可能にする
    st.subheader("LINE連携設定")
    line_token_val = st.text_input("LINE Token", 
                                   value=str(u_prof.get("line_token", "")) if pd.notna(u_prof.get("line_token")) else "", 
                                   type="password")
    line_user_val = st.text_input("LINE User ID", 
                                  value=str(u_prof.get("line_user_id", "")) if pd.notna(u_prof.get("line_user_id")) else "")
    
    st.divider()
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    ms = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    st.session_state.sel_model = st.selectbox("AI Model", ms, index=0)

# ==========================================
# 5. 詳細設定 (項目追加と削除の分離)
# ==========================================
with st.expander("⚙️ 詳細設定（プロフィール・項目管理）", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=str(u_prof.get("user_id", "")))
    u_goal = st.text_area("現在の目標", value=str(u_prof.get("goal", "")))
    u_coach = st.selectbox("担当コーチ", options=["安西先生", "熱血タイプ", "論理タイプ"], 
                           index=["安西先生", "熱血タイプ", "論理タイプ"].index(u_prof.get("coach_name")) if u_prof.get("coach_name") in ["安西先生", "熱血タイプ", "論理タイプ"] else 0)

    # 現在の計測項目
    m_str = st.text_input("計測項目（カンマ区切り）", 
                          value=str(u_prof.get("tracked_metrics", "シュート率,ハンドリング")))
    
    st.info("※項目の追加・削除は上の「計測項目」欄を直接編集して保存してください。")

# ==========================================
# 6. 本日のメニュー (タスク達成率)
# ==========================================
st.divider()
st.subheader("📋 本日の練習メニュー")
tasks = ["シュート練習 50本", "ハンドリング 10分", "フットワーク", "対人練習"]
done_count = 0
for t in tasks:
    if st.checkbox(t):
        done_count += 1

achieve_rate = int((done_count / len(tasks)) * 100)
st.metric("達成率", f"{achieve_rate}%")
st.progress(achieve_rate / 100)

# ==========================================
# 7. 振り返り入力 (以前の成功ロジックを完全再現)
# ==========================================
st.divider()
st.subheader(f"📝 {target_date_str} の振り返り")

try: def_rate = int(float(existing_history.get("rate", 3)))
except: def_rate = 3
rate = st.slider("自己評価", 1, 5, def_rate)
note = st.text_area("練習の気づき", value=str(existing_history.get("note", "")), height=150)

# --- 重要: ハンドリング等の数値反映 (成功時のコードをそのまま適用) ---
metric_inputs = {}
if m_str:
    for m_name in m_str.split(","):
        m_name = m_name.strip()
        if m_name:
            prev_val = 0.0
            if not existing_metrics.empty:
                m_match = existing_metrics[existing_metrics["metric_name"] == m_name]
                if not m_match.empty:
                    try: prev_val = float(m_match.iloc[-1]["value"])
                    except: prev_val = 0.0
            metric_inputs[m_name] = st.number_input(f"{m_name} の結果", value=prev_val, key=f"n_{m_name}")

# ==========================================
# 8. 保存 & LINE報告 (データ保護維持)
# ==========================================
if st.button("💾 記録を保存してLINE報告", use_container_width=True):
    if not u_id:
        st.error("ユーザーIDを入力してください")
    else:
        with st.spinner("処理中..."):
            # Profiles更新 (LINE情報を守るために既存行を読み直して更新)
            p_latest = conn.read(worksheet="Profiles", ttl=0)
            new_p_data = {
                "user_id": u_id, "goal": u_goal, "coach_name": u_coach, 
                "tracked_metrics": m_str, "line_token": line_token_val, "line_user_id": line_user_val
            }
            if u_id in p_latest["user_id"].astype(str).values:
                idx = p_latest[p_latest["user_id"].astype(str) == u_id].index[0]
                for k, v in new_p_data.items(): p_latest.at[idx, k] = v
                final_p = p_latest
            else:
                final_p = pd.concat([p_latest, pd.DataFrame([new_p_data])], ignore_index=True)

            # History & Metrics のマージ
            h_upd = pd.concat([history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == target_date_str))], 
                               pd.DataFrame([{"user_id": u_id, "date": target_date_str, "rate": rate, "note": note}])], ignore_index=True)
            
            m_new_rows = [{"user_id": u_id, "date": target_date_str, "metric_name": k, "value": v} for k, v in metric_inputs.items()]
            m_upd = pd.concat([metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == target_date_str))], pd.DataFrame(m_new_rows)], ignore_index=True)

            # スプレッドシート保存
            conn.update(worksheet="Profiles", data=final_p)
            conn.update(worksheet="History", data=h_upd)
            conn.update(worksheet="Metrics", data=m_upd)

            # LINE送信
            if line_token_val and line_user_val:
                m_txt = "\n".join([f"・{k}: {v}" for k, v in metric_inputs.items()])
                line_msg = f"【AI報告】{target_date_str}\n達成率: {achieve_rate}%\n評価: {int(rate)}\n内容: {str(note)}\n\n[数値]\n{m_txt}"
                payload = {"to": str(line_user_id_input), "messages": [{"type": "text", "text": line_msg}]}
                headers = {"Authorization": f"Bearer {line_token_val}", "Content-Type": "application/json"}
                requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json={"to": str(line_user_val), "messages": [{"type": "text", "text": line_msg}]})
            
            st.success("全て完了しました！")
            st.rerun()
