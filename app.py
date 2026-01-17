import streamlit as st
import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# --- 1. 設定とキャッシュの管理 ---
CONFIG_FILE = "app_settings.json"
SPREADSHEET_NAME = "AI_Trainer_DB"
SHEET_NAME = "Profiles"

def load_cache():
    """ローカルに保存された設定（前回選択モデルなど）を読み込む"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"selected_model": "gemini-3-pro", "line_token": "", "line_user_id": ""}

def save_cache(settings):
    """設定をローカルに保存する"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

# --- 2. 外部連携ロジック（Secrets使用） ---
def get_latest_models():
    """SecretsのAPIキーを使用し、1.5系以外の最新モデルを動的に取得"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                model_id = m.name.replace('models/', '')
                # 1.5系を排除し、最新(2.5/3.0等)のみを抽出
                if "1.5" not in model_id:
                    models.append(model_id)
        return models
    except Exception:
        return ["gemini-3-pro"]

def sync_from_sheets():
    """Secrets内のサービスアカウント情報を使用し、Profilesシート(E列, F列)から情報を取得"""
    try:
        # st.secrets["gcp_service_account"] (辞書形式) を使用して認証
        creds_info = st.secrets["gcp_service_account"]
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(creds)
        
        # スプレッドシートを開く
        sheet = client.open(SPREADSHEET_NAME).worksheet(SHEET_NAME)
        
        # E2列: LINE Token, F2列: LINE User ID を取得
        token = sheet.acell('E2').value
        user_id = sheet.acell('F2').value
        return token, user_id
    except Exception as e:
        st.error(f"スプレッドシート同期エラー: {e}")
        return None, None

def send_line(message, token, user_id):
    """LINEへのプッシュ送信"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    data = {"to": user_id, "messages": [{"type": "text", "text": message}]}
    res = requests.post(url, headers=headers, json=data)
    return res.status_code == 200

# --- 3. メイン UI 構築 ---
st.set_page_config(page_title="AI Trainer Pro", layout="centered")
cache = load_cache()

st.title("AI Trainer 業務報告")

# 報告入力エリア
report_text = st.text_area("本日のサマリー（LINEに送信されます）", placeholder="こちらに内容を入力...")

if st.button("LINEで報告を送信"):
    if cache["line_token"] and cache["line_user_id"]:
        full_msg = f"【AI報告】\n使用モデル: {cache['selected_model']}\n内容: {report_text}"
        if send_line(full_msg, cache["line_token"], cache["line_user_id"]):
            st.success("LINEに送信完了しました")
        else:
            st.error("送信に失敗しました")
    else:
        st.warning("設定画面から情報を同期してください")

# --- 4. サイドバー（目立たない設定画面） ---
with st.sidebar:
    st.write("### システム管理")
    with st.expander("⚙️ 詳細設定", expanded=False):
        st.caption("モデル・外部連携の同期")
        
        # 1. モデル選択（動的に取得）
        models = get_latest_models()
        current_model = cache.get("selected_model", "gemini-3-pro")
        idx = models.index(current_model) if current_model in models else 0
        
        selected = st.selectbox("使用モデルを選択", models, index=idx)
        if selected != current_model:
            cache["selected_model"] = selected
            save_cache(cache)
            st.toast(f"モデルを {selected} に設定しました")

        st.write("---")
        
        # 2. LINE情報の同期ボタン
        if st.button("Profilesシートから情報を同期"):
            t, u = sync_from_sheets()
            if t and u:
                cache["line_token"] = t
                cache["line_user_id"] = u
                save_cache(cache)
                st.success("E列・F列から情報を取得しました")
