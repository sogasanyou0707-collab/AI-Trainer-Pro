import streamlit as st
import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# --- 1. 設定管理 (キャッシュ用) ---
CONFIG_FILE = "app_settings.json"
# 以前ご指定いただいたシート名
SHEET_NAME = "Profiles"

def load_cache():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"selected_model": "gemini-3-pro", "line_token": "", "line_user_id": ""}

def save_cache(settings):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

# --- 2. 外部連携ロジック ---
def get_latest_models():
    """SecretsのAPIキーを使用し、1.5系以外の最新モデルを動的に取得"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                model_id = m.name.replace('models/', '')
                # 1.5系（Flash等）を除外し、2.5や3.0系を抽出
                if "1.5" not in model_id:
                    models.append(model_id)
        return models
    except Exception:
        return ["gemini-3-pro"]

def sync_from_sheets():
    """[connections.gsheets] セクションから情報を取得し、E2・F2を読み込む"""
    try:
        # Secrets の階層に合わせて取得先を修正
        if "connections" not in st.secrets or "gsheets" not in st.secrets["connections"]:
            st.error("Secrets 内に [connections.gsheets] が見つかりません。設定を確認してください。")
            return None, None

        creds_info = st.secrets["connections"]["gsheets"]
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        
        # credentials情報のみを抽出して認証
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(creds)
        
        # Secrets内の URL を使用してスプレッドシートを開く
        if "spreadsheet" in creds_info:
            sh = client.open_by_url(creds_info["spreadsheet"])
        else:
            # URLがない場合のフォールバック（以前の名前指定）
            sh = client.open("AI_Trainer_DB")
            
        sheet = sh.worksheet(SHEET_NAME)
        
        # E2: LINE Token, F2: LINE User ID を取得
        token = sheet.acell('E2').value
        user_id = sheet.acell('F2').value
        return token, user_id
        
    except Exception as e:
        st.error(f"同期失敗: {e}")
        return None, None

def send_line(message, token, user_id):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    data = {"to": user_id, "messages": [{"type": "text", "text": message}]}
    res = requests.post(url, headers=headers, json=data)
    return res.status_code == 200

# --- 3. UI 構築 ---
st.set_page_config(page_title="AI Trainer Pro", layout="centered")
cache = load_cache()

st.title("AI Trainer 業務報告")

# メイン画面
report_text = st.text_area("報告内容", placeholder="内容を入力してください")

if st.button("LINE送信"):
    if cache["line_token"] and cache["line_user_id"]:
        msg = f"【AI報告】\nモデル: {cache['selected_model']}\n内容: {report_text}"
        if send_line(msg, cache["line_token"], cache["line_user_id"]):
            st.success("LINEに送信しました")
        else:
            st.error("送信に失敗しました")
    else:
        st.warning("設定から情報を同期してください")

# サイドバー設定
with st.sidebar:
    with st.expander("⚙️ 詳細設定", expanded=False):
        # 1. 最新モデル選択
        models = get_latest_models()
        current = cache.get("selected_model", "gemini-3-pro")
        idx = models.index(current) if current in models else 0
        
        selected = st.selectbox("使用モデル", models, index=idx)
        if selected != current:
            cache["selected_model"] = selected
            save_cache(cache)
            st.toast(f"モデルを {selected} に設定")

        st.write("---")
        
        # 2. LINE情報同期
        if st.button("Profilesシートから同期"):
            t, u = sync_from_sheets()
            if t and u:
                cache["line_token"] = t
                cache["line_user_id"] = u
                save_cache(cache)
                st.success("E2・F2 から LINE 情報を取得しました")
