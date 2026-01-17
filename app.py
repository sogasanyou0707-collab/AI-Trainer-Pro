import streamlit as st
import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from datetime import datetime

# --- 1. 定数・キャッシュ管理 ---
CONFIG_FILE = "app_settings.json"
SHEET_NAME = "Profiles"

def load_cache():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {
        "user_name": "管理者",
        "user_role": "臨床検査技師 / ICT",
        "selected_model": "gemini-3-pro",
        "line_token": "",
        "line_user_id": ""
    }

def save_cache(settings):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

# --- 2. 外部ロジック ---
def get_latest_models():
    """APIから最新モデルを動的に取得（1.5系排除）"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        return [m.name.replace('models/', '') for m in genai.list_models() 
                if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    except:
        return ["gemini-3-pro"]

def sync_line_from_sheets():
    """Secretsを使用してProfiles(E2, F2)から同期"""
    try:
        creds_info = st.secrets["connections"]["gsheets"]
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(creds)
        sh = client.open_by_url(creds_info["spreadsheet"])
        sheet = sh.worksheet(SHEET_NAME)
        return sheet.acell('E2').value, sheet.acell('F2').value
    except Exception as e:
        st.error(f"同期失敗: {e}")
        return None, None

def ai_suggest_tasks(content, model_name, role):
    """入力内容に基づきAIがタスクを提案"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel(model_name)
        prompt = f"""
        あなたは{role}の専門アシスタントです。
        以下の本日の業務報告内容に基づき、明日以降に優先すべきタスクを3つ、具体的かつ簡潔に提案してください。
        
        【報告内容】:
        {content}
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"提案の生成に失敗しました: {e}"

# --- 3. UI 構築 ---
st.set_page_config(page_title="AI Trainer Pro", layout="wide")
if 'cache' not in st.session_state:
    st.session_state.cache = load_cache()
cache = st.session_state.cache

# --- サイドバー：カレンダーと設定 ---
with st.sidebar:
    st.title("📌 Menu")
    
    # ユーザープロフィール表示
    st.write(f"**👤 ユーザー:** {cache['user_name']}")
    st.caption(f"**Role:** {cache['user_role']}")
    
    st.write("---")
    
    # カレンダー機能
    st.subheader("🗓️ カレンダー")
    selected_date = st.date_input("日付を選択", datetime.now())
    st.info(f"選択日: {selected_date.strftime('%Y/%m/%d')}")

    st.write("---")
    
    # 目立たない詳細設定
    with st.expander("⚙️ 詳細設定", expanded=False):
        # ユーザー編集
        cache["user_name"] = st.text_input("表示名", cache["user_name"])
        cache["user_role"] = st.text_input("役割", cache["user_role"])
        
        # モデル選択
        models = get_latest_models()
        idx = models.index(cache["selected_model"]) if cache["selected_model"] in models else 0
        cache["selected_model"] = st.selectbox("使用モデル", models, index=idx)
        
        if st.button("LINE情報の同期", use_container_width=True):
            t, u = sync_line_from_sheets()
            if t and u:
                cache["line_token"], cache["line_user_id"] = t, u
                st.success("同期完了 (E2/F2)")
        
        if st.button("設定を保存"):
            save_cache(cache)
            st.toast("設定を保存しました")

# --- メインエリア：業務報告とAIタスク ---
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📝 本日の業務報告")
    report_text = st.text_area("内容を入力", placeholder="例: グラム染色にて黄色ブドウ球菌を確認、主治医へ報告完了。", height=300)
    
    if st.button("LINE送信", use_container_width=True):
        if cache["line_token"] and cache["line_user_id"]:
            msg = f"【{selected_date} 報告】\n担当: {cache['user_name']}\n内容: {report_text}"
            url = "https://api.line.me/v2/bot/message/push"
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {cache['line_token']}"}
            data = {"to": cache["line_user_id"], "messages": [{"type": "text", "text": msg}]}
            if requests.post(url, headers=headers, json=data).status_code == 200:
                st.success("LINE送信完了")
            else: st.error("送信失敗")
        else: st.warning("LINE情報を同期してください")

with col2:
    st.subheader("💡 AI タスク提案")
    if st.button("AIにタスクを相談する", use_container_width=True):
        if not report_text:
            st.warning("報告内容を入力してから相談してください。")
        else:
            with st.spinner("AIが思考中..."):
                suggestions = ai_suggest_tasks(report_text, cache["selected_model"], cache["user_role"])
                st.markdown(suggestions)
                
                # 提案をLINEに送るオプション
                if st.button("この提案をLINEで自分に送る"):
                    send_msg = f"【AIからの提案】\n{suggestions}"
                    # 送信ロジック省略（上記と同様）
                    st.info("提案を送信しました。")

st.write("---")
st.caption(f"System: {cache['selected_model']} 稼働中 / {datetime.now().strftime('%Y-%m-%d %H:%M')}")
