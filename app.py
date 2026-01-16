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
st.set_page_config(page_title="AI Trainer Pro: Ultimate v1.1", layout="wide")

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    genai.configure(api_key=API_KEY)
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"初期設定エラー: {e}")
    st.stop()

@st.cache_resource
def get_available_models():
    try:
        models = [m.name.replace("models/", "") for m in genai.list_models() 
                  if "generateContent" in m.supported_generation_methods]
        return models
    except:
        return ["gemini-1.5-flash", "gemini-pro"]

available_models = get_available_models()

# --- 2. データ読み書き関数 (列名の曖昧さを解消) ---
def load_full_data_gs(user_id):
    u_id = str(user_id).strip().lower() # 照合用に正規化
    default_data = {
        "profile": {"height": 170.0, "weight": 65.0, "goal": "バスケのスキルアップ"},
        "history": {}, "notes": {}, "metrics_data": pd.DataFrame(), "metrics_defs": ["体重"],
        "line": {"token": "", "uid": "", "en": False},
        "daily_message": "今日も最高の練習を！", "tasks": [], "roadmap": ""
    }
    try:
        # シートを読み込み、列名を小文字に統一
        def read_normalized(ws_name):
            df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=ws_name, ttl=0)
            df.columns = [c.lower().strip() for c in df.columns] # 全ての列名を小文字＋空白除去
            return df

        p_df = read_normalized("Profiles")
        h_df = read_normalized("History")
        m_df = read_normalized("Metrics")
        s_df = read_normalized("Settings")

        # Profilesの復元 (user_idが一致する行を探す)
        p_df['user_id_norm'] = p_df['user_id'].astype(str).str.lower().str.strip()
        prof = p_df[p_df['user_id_norm'] == u_id].to_dict('records')
        
        if prof:
            p = prof[0]
            default_data["profile"] = {"height": p.get('height', 170), "weight": p.get('weight', 65), "goal": p.get('goal', "未設定")}
            default_data["line"] = {"token": p.get('line_token', ""), "uid": p.get('line_user_id', ""), "en": p.get('line_enabled', False)}
            default_data["daily_message"] = p.get('daily_message', "準備はいいか！")
            
            # 【復元ポイント】ロードマップを確実に取得
            roadmap_val = p.get('roadmap', "")
            default_data["roadmap"] = str(roadmap_val) if pd.notna(roadmap_val) else ""
            
            t_json = p.get('tasks_json', "[]")
            default_data["tasks"] = json.loads(t_json) if t_json and t_json != "nan" else []

        # 歴史・メモ
        if not h_df.empty:
            h_df['user_id_norm'] = h_df['user_id'].astype(str).str.lower().str.strip()
            sub_h = h_df[h_df['user_id_norm'] == u_id]
            default_data["history"] = sub_h.set_index('date')['rate'].to_dict()
            default_data["notes"] = sub_h.set_index('date')['note'].to_dict()

        # グラフデータ
        if not m_df.empty:
            m_df['user_id_norm'] = m_df['user_id'].astype(str).str.lower().str.strip()
            default_data["metrics_data"] = m_df[m_df['user_id_norm'] == u_id]

        # 【復元ポイント】Settingsから追加項目を確実に復元
        if not s_df.empty:
            s_df['user_id_norm'] = s_df['user_id'].astype(str).str.lower().str.strip()
            user_items = s_df[s_df['user_id_norm'] == u_id]['metric_defs'].dropna().unique().tolist()
            if user_items:
                default_data["metrics_defs"] = sorted(user_items)

        return default_data
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
        return default_data

def save_to_gs(worksheet_name, new_df, key_cols=['user_id', 'date']):
    try:
        # 保存前に全ての列名を小文字にする
        new_df.columns = [c.lower().strip() for c in new_df.columns]
        existing_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
        existing_df.columns = [c.lower().strip() for c in existing_df.columns]
        
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        # キーの重複を排除（最新を保持）
        key_cols = [k.lower().strip() for k in key_cols]
        combined = combined.drop_duplicates(subset=key_cols, keep='last')
        
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=combined)
        return True
    except Exception as e:
        st.error(f"保存エラー ({worksheet_name}): {e}")
        return False

# --- 3. ログイン & セッション ---
st.sidebar.title("🔑 ログイン")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    st.session_state.db = load_full_data_gs(login_id)
    st.session_state.current_user = login_id

selected_coach = st.sidebar.selectbox("🤖 コーチ選択", ["バスケットコーチ", "熱血コーチ", "論理派"])
selected_model = st.sidebar.selectbox("AIモデル", available_models, index=0)
model = genai.GenerativeModel(selected_model, system_instruction=f"あなたは{selected_coach}です。目標:{st.session_state.db['profile']['goal']}")

# --- 4. サイドバー設定 (保存機能) ---
with st.sidebar.expander("👤 プロフィール・LINE設定"):
    p_d = st.session_state.db["profile"]
    h_v = st.number_input("身長 (cm)", value=float(p_d["height"]))
    w_v = st.number_input("体重 (kg)", value=float(p_d["weight"]))
    g_v = st.text_area("目標", value=p_d["goal"])
    l_en = st.checkbox("LINE報告有効", value=st.session_state.db["line"]["en"])
    l_at = st.text_input("トークン", value=st.session_state.db["line"]["token"], type="password")
    l_ui = st.text_input("宛先UID", value=st.session_state.db["line"]["uid"])
    
    if st.button("全設定を保存"):
        t_json = json.dumps(st.session_state.db["tasks"], ensure_ascii=False)
        df_p = pd.DataFrame([{
            "user_id": login_id, "height": h_v, "weight": w_v, "goal": g_v,
            "line_token": l_at, "line_user_id": l_ui, "line_enabled": l_en,
            "daily_message": st.session_state.db["daily_message"], 
            "tasks_json": t_json, 
            "roadmap": st.session_state.db["roadmap"]
        }])
        if save_to_gs("Profiles", df_p, key_cols=['user_id']):
            st.session_state.db["profile"] = {"height": h_v, "weight": w_v, "goal": g_v}
            st.success("スプレッドシートに同期しました！")

with st.sidebar.expander("📊 記録項目の管理"):
    new_m = st.text_input("新規項目名（例：ハンドリングスピード）")
    if st.button("追加") and new_m:
        if new_m not in st.session_state.db["metrics_defs"]:
            st.session_state.db["metrics_defs"].append(new_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            # Settingsは全入れ替えではなく追加保存
            save_to_gs("Settings", df_s, key_cols=['user_id', 'metric_defs'])
            st.rerun()

# --- 5. メイン画面 ---
tabs = st.tabs(["📅 カレンダー", "📋 メニュー", "📈 グラフ", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()

with tabs[1]: # 今日のメニュー
    st.info(f"**【コーチより】**\n{st.session_state.db.get('daily_message', '生成してください')}")
    if st.button("AIメニュー生成"):
        res = model.generate_content("バスケ練習タスク4つと励ましを [MESSAGE]...[/MESSAGE] で。")
        st.session_state.db["daily_message"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", res.text, re.DOTALL).group(1).strip()
        tasks = [l.strip("- *123. ") for l in res.text.split("\n") if l.strip().startswith(("-", "*", "1."))]
        st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks][:4]
        # 即時保存
        t_json = json.dumps(st.session_state.db["tasks"], ensure_ascii=False)
        df_p = pd.DataFrame([{"user_id": login_id, "daily_message": st.session_state.db["daily_message"], "tasks_json": t_json, "roadmap": st.session_state.db["roadmap"]}])
        save_to_gs("Profiles", df_p, key_cols=['user_id'])
        st.rerun()
    
    col_l, col_r = st.columns([2, 1])
    with col_l:
        for i, t in enumerate(st.session_state.db["tasks"]):
            st.session_state.db["tasks"][i]["done"] = st.checkbox(t["task"], value=t["done"], key=f"tk_{i}_{t['task']}")
        done_n = sum(1 for t in st.session_state.db["tasks"] if t["done"])
        rate = done_n / len(st.session_state.db["tasks"]) if st.session_state.db["tasks"] else 0
        st.metric("達成率", f"{int(rate*100)}%")
        free_note = st.text_area("頑張りメモ", value=st.session_state.db["notes"].get(str(today), ""))

    with col_r:
        st.subheader("数値記録")
        today_metrics = {m: st.number_input(m, value=0.0, key=f"m_{m}") for m in st.session_state.db["metrics_defs"]}

    if st.button("保存 & LINE報告"):
        t_json = json.dumps(st.session_state.db["tasks"], ensure_ascii=False)
        save_to_gs("Profiles", pd.DataFrame([{"user_id": login_id, "daily_message": st.session_state.db["daily_message"], "tasks_json": t_json, "roadmap": st.session_state.db["roadmap"]}]), key_cols=['user_id'])
        save_to_gs("History", pd.DataFrame([{"user_id": login_id, "date": str(today), "rate": rate, "note": free_note}]))
        save_to_gs("Metrics", pd.DataFrame([{"user_id": login_id, "date": str(today), "metric_name": k, "value": v} for k, v in today_metrics.items()]), key_cols=['user_id', 'date', 'metric_name'])
        st.success("保存完了！")
        st.rerun()

with tabs[3]: # ロードマップ
    if st.button("AIロードマップ生成"):
        res = model.generate_content("目標達成戦略をMermaid mindmap形式で。```mermaid...```で囲んで。")
        match = re.search(r"```mermaid\s*(.*?)\s*```", res.text, re.DOTALL)
        if match:
            st.session_state.db["roadmap"] = match.group(1)
            #Profilesへ確実に保存
            df_p = pd.DataFrame([{"user_id": login_id, "roadmap": st.session_state.db["roadmap"], "tasks_json": json.dumps(st.session_state.db["tasks"])}])
            save_to_gs("Profiles", df_p, key_cols=['user_id'])
            st.success("ロードマップを保存しました")
            st.rerun()
    
    if st.session_state.db.get("roadmap"):
        st.components.v1.html(f"""
            <div class="mermaid" style="display:flex;justify-content:center;">
                {st.session_state.db["roadmap"]}
            </div>
            <script type="module">
                import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                mermaid.initialize({{ startOnLoad: true, theme: 'neutral' }});
            </script>
        """, height=500)
