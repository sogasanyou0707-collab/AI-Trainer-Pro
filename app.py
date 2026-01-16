import streamlit as st
import google.generativeai as genai
import re
import json
import pandas as pd
import datetime
import calendar
import requests
from PIL import Image
from streamlit_gsheets import GSheetsConnection

# --- 1. 初期設定 ---
st.set_page_config(page_title="AI Trainer Pro: Professional Beta v1.5", layout="wide")

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    genai.configure(api_key=API_KEY)
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"初期設定エラー: {e}")
    st.stop()

# --- 2. モデル取得機能（復活：選択画面用） ---
@st.cache_resource
def get_available_models():
    """現在のアカウントで利用可能なモデルをリストアップ"""
    try:
        models = [m.name.replace("models/", "") for m in genai.list_models() 
                  if "generateContent" in m.supported_generation_methods]
        return models
    except:
        # 取得失敗時のフォールバック
        return ["gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-pro"]

available_models = get_available_models()

# --- 3. データ読み書き関数 (復元ロジックをより精密に) ---
def load_full_data_gs(user_id):
    u_id = str(user_id).strip() # 空白を除去
    default_data = {
        "profile": {"height": 170.0, "weight": 65.0, "goal": "バスケ上達"},
        "history": {}, "notes": {}, "metrics_data": pd.DataFrame(), "metrics_defs": ["体重"],
        "line": {"token": "", "uid": "", "en": False},
        "daily_message": "今日も最高の練習を！", "tasks": [], "roadmap": ""
    }
    try:
        # 各シートを確実に読み込む（エラーが出た場所を特定できるようにする）
        with st.spinner(f"ユーザー {u_id} のデータを読み込み中..."):
            p_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0)
            h_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="History", ttl=0)
            m_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Metrics", ttl=0)
            s_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Settings", ttl=0)

        # 全てのシートの列名を小文字＋空白除去で統一
        for df in [p_df, h_df, m_df, s_df]:
            df.columns = [c.lower().strip() for c in df.columns]

        # ユーザーIDを文字列として比較（Profilesシート）
        prof = p_df[p_df['user_id'].astype(str).str.strip() == u_id].to_dict('records')
        if prof:
            p = prof[0]
            default_data["profile"] = {"height": p.get('height', 170), "weight": p.get('weight', 65), "goal": p.get('goal', "未設定")}
            default_data["line"] = {"token": p.get('line_token', ""), "uid": p.get('line_user_id', ""), "en": p.get('line_enabled', False)}
            default_data["daily_message"] = p.get('daily_message', "準備はいいか！")
            
            # ロードマップとタスクの復元
            default_data["roadmap"] = str(p.get('roadmap', "")) if pd.notna(p.get('roadmap')) else ""
            t_json = p.get('tasks_json', "[]")
            default_data["tasks"] = json.loads(t_json) if t_json and t_json != "nan" else []

        # 追加項目 (Settingsシート) からの読み込み
        if not s_df.empty:
            user_items = s_df[s_df['user_id'].astype(str).str.strip() == u_id]['metric_defs'].dropna().unique().tolist()
            if user_items:
                default_data["metrics_defs"] = sorted(user_items)

        # 履歴・グラフデータ
        if not h_df.empty:
            sub_h = h_df[h_df['user_id'].astype(str).str.strip() == u_id]
            default_data["history"] = sub_h.set_index('date')['rate'].to_dict()
            default_data["notes"] = sub_h.set_index('date')['note'].to_dict()
        if not m_df.empty:
            default_data["metrics_data"] = m_df[m_df['user_id'].astype(str).str.strip() == u_id]

        return default_data
    except Exception as e:
        st.error(f"読み込み中に問題が発生しました: {e}")
        return default_data

def save_to_gs(worksheet_name, new_df, key_cols=['user_id', 'date']):
    try:
        new_df.columns = [c.lower().strip() for c in new_df.columns]
        existing_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
        existing_df.columns = [c.lower().strip() for c in existing_df.columns]
        combined = pd.concat([existing_df, new_df], ignore_index=True).drop_duplicates(subset=[k.lower() for k in key_cols], keep='last')
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=combined)
        return True
    except:
        return False

# --- 4. ログイン ＆ UI ---
st.sidebar.title("🔑 ログイン設定")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    st.session_state.db = load_full_data_gs(login_id)
    st.session_state.current_user = login_id

# 【復活】最新モデルの選択画面
st.sidebar.divider()
selected_coach = st.sidebar.selectbox("🤖 コーチ選択", ["バスケットコーチ", "熱血コーチ", "論理派"])
selected_model_name = st.sidebar.selectbox("🚀 使用AIモデル", available_models, index=0)
model = genai.GenerativeModel(selected_model_name, system_instruction=f"あなたは{selected_coach}です。目標:{st.session_state.db['profile']['goal']}")

# --- 5. サイドバー機能 (プロフィール・項目・画像) ---
with st.sidebar.expander("👤 各種設定"):
    p_d = st.session_state.db["profile"]
    h_v = st.number_input("身長 (cm)", value=float(p_d["height"]))
    w_v = st.number_input("体重 (kg)", value=float(p_d["weight"]))
    g_v = st.text_area("目標", value=p_d["goal"])
    l_at = st.text_input("LINEトークン", value=st.session_state.db["line"]["token"], type="password")
    l_ui = st.text_input("宛先UID", value=st.session_state.db["line"]["uid"])
    l_en = st.checkbox("LINE報告有効", value=st.session_state.db["line"]["en"])
    
    if st.button("全設定を保存"):
        t_json = json.dumps(st.session_state.db["tasks"], ensure_ascii=False)
        df_p = pd.DataFrame([{
            "user_id": login_id, "height": h_v, "weight": w_v, "goal": g_v,
            "line_token": l_at, "line_user_id": l_ui, "line_enabled": l_en,
            "daily_message": st.session_state.db["daily_message"], 
            "tasks_json": t_json, "roadmap": st.session_state.db["roadmap"]
        }])
        save_to_gs("Profiles", df_p, key_cols=['user_id'])
        st.success("スプレッドシートに保存完了！")

with st.sidebar.expander("📊 項目管理（追加・削除）"):
    new_m = st.text_input("新規項目名")
    if st.button("追加") and new_m:
        if new_m not in st.session_state.db["metrics_defs"]:
            st.session_state.db["metrics_defs"].append(new_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            save_to_gs("Settings", df_s, key_cols=['user_id', 'metric_defs'])
            st.rerun()
    if st.session_state.db["metrics_defs"]:
        del_m = st.selectbox("削除項目", st.session_state.db["metrics_defs"])
        if st.button("削除実行"):
            st.session_state.db["metrics_defs"].remove(del_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df_s)
            st.rerun()

st.sidebar.divider()
uploaded_file = st.sidebar.file_uploader("写真分析 (食事・フォーム)", type=["jpg", "png", "jpeg"])

# --- 6. メイン画面 ---
tabs = st.tabs(["📅 カレンダー", "📋 今日のメニュー", "📈 グラフ", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()

# --- Tab 2: 今日のメニュー (復元・LINE報告強化) ---
with tabs[1]:
    st.info(f"**【コーチより】** {st.session_state.db.get('daily_message')}")
    if st.button("AIメニュー生成"):
        res = model.generate_content("バスケ練習タスク4つと励ましを [MESSAGE]...[/MESSAGE] で出力。")
        st.session_state.db["daily_message"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", res.text, re.DOTALL).group(1).strip()
        tasks = [l.strip("- *123. ") for l in res.text.split("\n") if l.strip().startswith(("-", "*", "1."))]
        st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks][:4]
        st.rerun()

    col_l, col_r = st.columns([2, 1])
    with col_l:
        st.subheader("✅ タスクリスト")
        for i, t in enumerate(st.session_state.db["tasks"]):
            st.session_state.db["tasks"][i]["done"] = st.checkbox(t["task"], value=t["done"], key=f"tk_{i}_{t['task']}")
        
        done_n = sum(1 for t in st.session_state.db["tasks"] if t["done"])
        rate = done_n / len(st.session_state.db["tasks"]) if st.session_state.db["tasks"] else 0
        st.metric("達成率", f"{int(rate*100)}%")
        st.progress(rate)
        free_note = st.text_area("頑張りメモ", value=st.session_state.db["notes"].get(str(today), ""))

    with col_r:
        st.subheader("数値記録")
        # 【重要】復元された項目がここに並びます
        today_metrics = {m: st.number_input(m, value=0.0, key=f"m_{m}") for m in st.session_state.db["metrics_defs"]}

    if st.button("🚀 保存 & LINE報告送信"):
        t_json = json.dumps(st.session_state.db["tasks"], ensure_ascii=False)
        save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "tasks_json": t_json, "daily_message": st.session_state.db["daily_message"], "roadmap": st.session_state.db["roadmap"]}]), key_cols=['user_id'])
        save_to_gs("History", pd.DataFrame([{"user_id": login_id, "date": str(today), "rate": rate, "note": free_note}]))
        save_to_gs("Metrics", pd.DataFrame([{"user_id": login_id, "date": str(today), "metric_name": k, "value": v} for k, v in today_metrics.items()]), key_cols=['user_id', 'date', 'metric_name'])
        
        if l_en and l_at:
            metrics_details = "\n".join([f"・{k}: {v}" for k, v in today_metrics.items() if v > 0])
            prompt = f"達成率{int(rate*100)}%、頑張り：『{free_note}』、記録：『{metrics_details}』へのフィードバックを作成して。"
            feedback = model.generate_content(prompt).text
            msg = f"\n【{login_id} 報告】\n達成率:
