import streamlit as st
import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from datetime import datetime

# --- 1. 設定・キャッシュ管理 ---
CONFIG_FILE = "app_settings.json"
SHEET_NAME = "Profiles"

def load_cache():
    """設定を読み込み、不足項目があればデフォルトで補完"""
    defaults = {
        "user_name": "未設定",
        "user_role": "未設定",
        "selected_model": "gemini-3-pro",
        "line_token": "",
        "line_user_id": ""
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults.update(data)
        except:
            pass
    return defaults

def save_cache(settings):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

# --- 2. 外部連携ロジック ---
def get_latest_models():
    """1.5系を除外した最新モデルを動的に取得"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        models = [m.name.replace('models/', '') for m in genai.list_models() 
                if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
        return models if models else ["gemini-3-pro"]
    except:
        return ["gemini-3-pro"]

def sync_all_from_sheets():
    """スプレッドシートのProfilesシートから全情報を同期"""
    try:
        creds_info = st.secrets["connections"]["gsheets"]
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(creds)
        sh = client.open_by_url(creds_info["spreadsheet"])
        sheet = sh.worksheet(SHEET_NAME)
        
        # 各セルから情報を取得 (A2:名前, B2:役割, E2:トークン, F2:ID)
        return {
            "user_name": sheet.acell('A2').value,
            "user_role": sheet.acell('B2').value,
            "line_token": sheet.acell('E2').value,
            "line_user_id": sheet.acell('F2').value
        }
    except Exception as e:
        st.error(f"同期失敗: {e}")
        return None

def ai_get_suggestions(content, model_name, role):
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel(model_name)
        prompt = f"あなたは{role}の専門アシスタントです。以下の業務報告に基づき、明日以降のタスクを3つ具体的に提案してください。\n\n内容:\n{content}"
        return model.generate_content(prompt).text
    except Exception as e:
        return f"提案生成エラー: {e}"

# --- 3. UI 構築 ---
st.set_page_config(page_title="AI Trainer Pro", layout="centered")

if 'cache' not in st.session_state:
    st.session_state.cache = load_cache()
cache = st.session_state.cache

st.title("AI Trainer 業務報告")

# スプレッドシートから読み込んだユーザー情報を表示
st.write(f"👤 **{cache.get('user_name')}** ({cache.get('user_role')})")
selected_date = st.date_input("報告日を選択", datetime.now())

st.write("---")

report_text = st.text_area("本日の報告内容", placeholder="こちらに業務内容を入力してください", height=250)

if st.button("🚀 LINEで報告を送信", use_container_width=True):
    if cache.get("line_token") and cache.get("line_user_id"):
        msg = f"【{selected_date} 報告】\n担当: {cache['user_name']}\n---\n{report_text}"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {cache['line_token']}"}
        data = {"to": cache["line_user_id"], "messages": [{"type": "text", "text": msg}]}
        
        with st.spinner("送信中..."):
            res = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)
            if res.status_code == 200:
                st.success("LINEに送信しました！")
            else:
                st.error("送信失敗。")
    else:
        st.warning("設定画面から情報を同期してください。")

if st.button("💡 AIにタスクを相談する", use_container_width=True):
    if report_text:
        with st.spinner("思考中..."):
            suggestions = ai_get_suggestions(report_text, cache['selected_model'], cache['user_role'])
            st.markdown("### AIからの提案")
            st.info(suggestions)
    else:
        st.warning("先に報告内容を入力してください。")

# --- 4. サイドバー ---
with st.sidebar:
    st.header("⚙️ システム設定")
    with st.expander("詳細設定を開く", expanded=False):
        
        # モデル選択
        models = get_latest_models()
        cur_model = cache.get("selected_model", "gemini-3-pro")
        idx = models.index(cur_model) if cur_model in models else 0
        cache["selected_model"] = st.selectbox("使用モデル", models, index=idx)
        
        st.write("---")
        
        # 情報同期ボタン
        if st.button("LINE情報の同期", use_container_width=True):
            with st.spinner("スプレッドシートから取得中..."):
                new_data = sync_all_from_sheets()
                if new_data:
                    cache.update(new_data)
                    save_cache(cache)
                    st.success("スプレッドシートの全情報を同期しました")
                    st.rerun()
        
        if st.button("設定を保存", use_container_width=True):
            save_cache(cache)
            st.toast("現在の設定を保存しました")

st.write("---")
st.caption(f"Model: {cache['selected_model']}")
