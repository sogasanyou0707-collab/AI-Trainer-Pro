import streamlit as st
import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# --- 1. 定数とキャッシュの読み込み ---
CONFIG_FILE = "app_settings.json"
SPREADSHEET_NAME = "AI_Trainer_DB"
SHEET_NAME = "Profiles"

def load_settings():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"selected_model": "gemini-3-pro", "line_token": "", "line_user_id": ""}

def save_settings(settings):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

# --- 2. 各種機能の定義 ---
def get_latest_models(api_key):
    try:
        genai.configure(api_key=api_key)
        models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                model_id = m.name.replace('models/', '')
                # 1.5系を除外
                if "1.5" not in model_id:
                    models.append(model_id)
        return models
    except Exception as e:
        return ["gemini-3-pro"]

def sync_from_sheets():
    """スプレッドシートのProfiles(E列, F列)から情報を取得"""
    try:
        # StreamlitのSecretsまたはローカルファイルから認証
        # サービスアカウントのJSONが必要です
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        # ここでは 'service_account.json' を使用
        creds = Credentials.from_service_account_file('service_account.json', scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open(SPREADSHEET_NAME).worksheet(SHEET_NAME)
        
        token = sheet.acell('E2').value
        user_id = sheet.acell('F2').value
        return token, user_id
    except Exception as e:
        st.error(f"スプレッドシート同期エラー: {e}")
        return None, None

def send_line(message, token, user_id):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    data = {"to": user_id, "messages": [{"type": "text", "text": message}]}
    res = requests.post(url, headers=headers, json=data)
    return res.status_code == 200

# --- 3. Streamlit UIレイアウト ---
st.set_page_config(page_title="AI Trainer Pro", layout="centered")
settings = load_settings()

st.title("AI Trainer 業務報告")

# メイン画面の操作
report_text = st.text_area("本日の報告内容を入力してください", placeholder="例：検体検査の結果、異常なし")
if st.button("LINEで報告を送信"):
    if settings["line_token"] and settings["line_user_id"]:
        full_msg = f"【AI報告】\n使用モデル: {settings['selected_model']}\n内容: {report_text}"
        if send_line(full_msg, settings["line_token"], settings["line_user_id"]):
            st.success("LINEに送信しました！")
        else:
            st.error("送信に失敗しました。トークンを確認してください。")
    else:
        st.warning("設定画面でLINE情報を設定してください。")

# --- 4. 目立たない設定画面 (Sidebarの下部) ---
with st.sidebar:
    st.write("---")
    with st.expander("⚙️ 高度な設定 (管理用)", expanded=False):
        st.caption("モデル選択とLINE連携情報の管理")
        
        # APIキーの入力（通常はSecretsで管理すべきですがデバッグ用）
        api_key = st.text_input("Gemini API Key", type="password")
        
        # モデル動的取得
        if api_key:
            available_models = get_latest_models(api_key)
            selected = st.selectbox("使用モデルを選択", available_models, 
                                   index=available_models.index(settings["selected_model"]) if settings["selected_model"] in available_models else 0)
            settings["selected_model"] = selected
        
        st.write("---")
        # LINE情報同期
        if st.button("スプレッドシートからLINE情報を同期"):
            token, user_id = sync_from_sheets()
            if token and user_id:
                settings["line_token"] = token
                settings["line_user_id"] = user_id
                st.info("同期完了：E列(Token), F列(ID)を取得しました")
        
        # 保存ボタン
        if st.button("設定を保存"):
            save_settings(settings)
            st.success("キャッシュを更新しました")
