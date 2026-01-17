import streamlit as st
import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# --- 1. 定数・キャッシュ設定 ---
CONFIG_FILE = "app_settings.json"
SHEET_NAME = "Profiles"

def load_cache():
    """設定（選択モデル・LINE情報）をローカルファイルから読み込む"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    # デフォルト値
    return {"selected_model": "gemini-3-pro", "line_token": "", "line_user_id": ""}

def save_cache(settings):
    """設定をローカルファイルに保存する"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

# --- 2. 外部連携・ロジック ---
def get_latest_models():
    """Gemini APIから最新モデルを取得し、1.5系を排除したリストを返す"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                model_id = m.name.replace('models/', '')
                # 1.5系に依存しない構成：名前に "1.5" を含むものを除外
                if "1.5" not in model_id:
                    models.append(model_id)
        
        # リストが空の場合はフォールバック
        return models if models else ["gemini-3-pro"]
    except Exception:
        return ["gemini-3-pro"]

def sync_line_from_sheets():
    """Secretsの[connections.gsheets]を使用してLINE情報を同期"""
    try:
        if "connections" not in st.secrets or "gsheets" not in st.secrets["connections"]:
            st.error("Secretsの設定 [connections.gsheets] が見つかりません。")
            return None, None

        creds_info = st.secrets["connections"]["gsheets"]
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        
        # サービスアカウント認証
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(creds)
        
        # Secrets内のURLでスプレッドシートを開く
        if "spreadsheet" in creds_info:
            sh = client.open_by_url(creds_info["spreadsheet"])
        else:
            # フォールバック
            sh = client.open("AI_Trainer_DB")
            
        sheet = sh.worksheet(SHEET_NAME)
        
        # E2: Token, F2: UserID を取得
        token = sheet.acell('E2').value
        user_id = sheet.acell('F2').value
        return token, user_id
        
    except Exception as e:
        st.error(f"同期エラー: {e}")
        return None, None

def send_line_report(message, token, user_id):
    """LINE Messaging API を使用してプッシュ送信"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    data = {
        "to": user_id,
        "messages": [{"type": "text", "text": message}]
    }
    res = requests.post(url, headers=headers, json=data)
    return res.status_code == 200

# --- 3. UI 構築 (Streamlit) ---
st.set_page_config(page_title="AI Trainer Pro", layout="centered")

# キャッシュの読み込み
if 'app_cache' not in st.session_state:
    st.session_state.app_cache = load_cache()

cache = st.session_state.app_cache

st.title("AI Trainer 業務報告")

# メイン操作画面
report_text = st.text_area("報告内容を入力してください", placeholder="業務内容、気づき、解析結果など", height=200)

if st.button("LINEで報告を送信", use_container_width=True):
    if cache["line_token"] and cache["line_user_id"]:
        # メッセージの組み立て
        full_msg = f"【AI Trainer 報告】\n使用モデル: {cache['selected_model']}\n---\n{report_text}"
        
        with st.spinner("送信中..."):
            if send_line_report(full_msg, cache["line_token"], cache["line_user_id"]):
                st.success("LINEに送信完了しました！")
            else:
                st.error("送信に失敗しました。トークンの有効期限等を確認してください。")
    else:
        st.warning("先に設定画面から「LINE情報の同期」を行ってください。")

# --- 4. サイドバー (目立たない仕様の設定画面) ---
with st.sidebar:
    st.write("### システムメニュー")
    # Expanderで「目立たない」仕様を実現
    with st.expander("⚙️ 詳細設定", expanded=False):
        st.caption("モデルと外部連携の管理")
        
        # A. モデル選択 (動的)
        available_models = get_latest_models()
        current_model = cache.get("selected_model", "gemini-3-pro")
        
        # 現在のモデルがリストにない場合のインデックス処理
        try:
            model_idx = available_models.index(current_model)
        except ValueError:
            model_idx = 0
            
        selected = st.selectbox("使用AIモデル", available_models, index=model_idx)
        
        if selected != current_model:
            cache["selected_model"] = selected
            save_cache(cache)
            st.toast(f"モデルを {selected} に変更しました")

        st.write("---")
        
        # B. LINE情報の同期ボタン (名称変更済み)
        if st.button("LINE情報の同期", use_container_width=True):
            with st.spinner("同期中..."):
                t, u = sync_line_from_sheets()
                if t and u:
                    cache["line_token"] = t
                    cache["line_user_id"] = u
                    save_cache(cache)
                    st.success("E2/F2セルから同期しました")
                    st.rerun()

        st.caption("※設定は `app_settings.json` に自動保存されます")
