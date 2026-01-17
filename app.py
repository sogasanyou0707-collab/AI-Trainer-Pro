import streamlit as st
import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from datetime import datetime

# --- 1. 設定管理 ---
CONFIG_FILE = "app_settings.json"
SHEET_NAME = "Profiles"

def load_cache():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"selected_model": "gemini-3-pro"}

def save_cache(settings):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

# --- 2. スプレッドシートからの自動同期ロジック ---
def auto_sync_from_sheets():
    """起動時に自動でA2, B2, E2, F2を取得する"""
    try:
        creds_info = st.secrets["connections"]["gsheets"]
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(creds)
        sh = client.open_by_url(creds_info["spreadsheet"])
        sheet = sh.worksheet(SHEET_NAME)
        
        # 情報を一括取得してセッションに格納
        data = {
            "user_name": sheet.acell('A2').value,
            "user_role": sheet.acell('B2').value,
            "line_token": sheet.acell('E2').value,
            "line_user_id": sheet.acell('F2').value
        }
        return data
    except Exception as e:
        st.error(f"自動同期に失敗しました。Secretsを確認してください: {e}")
        return None

# --- 3. AIロジック ---
def get_latest_models():
    """1.5系を除外した最新モデルを動的に取得"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        return [m.name.replace('models/', '') for m in genai.list_models() 
                if 'generateContent' in m.supported_generation_methods and "1.5" not in m.name]
    except:
        return ["gemini-3-pro"]

def ai_coach_advice(content, model_name, role):
    """報告内容に基づきAIがコーチングとタスクを提案"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel(model_name)
        prompt = f"""
        あなたは{role}の専門コーチです。以下の業務報告に基づき、フィードバックと明日へのタスク提案を行ってください。
        1. 業務への専門的フィードバック
        2. 明日優先すべき具体的なタスク3選
        
        内容: {content}
        """
        return model.generate_content(prompt).text
    except Exception as e:
        return f"AIコーチング失敗: {e}"

# --- 4. UI 構築 (シンプル＆高速) ---
st.set_page_config(page_title="AI Trainer Pro", layout="centered")

# A. 自動同期（初回およびリロード時）
if 'user_info' not in st.session_state:
    with st.spinner("スプレッドシートから最新情報を同期中..."):
        info = auto_sync_from_sheets()
        if info:
            st.session_state.user_info = info
            st.session_state.cache = load_cache()
            st.session_state.cache.update(info) # キャッシュも更新

user = st.session_state.user_info
cache = st.session_state.cache

# タイトル
st.title("AI Trainer 業務報告")

# ユーザー情報表示
st.info(f"👤 **{user['user_name']}** | 🏷️ **{user['user_role']}**")

# カレンダー
selected_date = st.date_input("報告日", datetime.now())

st.write("---")

# 報告入力
report_text = st.text_area("本日の報告内容", placeholder="解析結果や実施事項を入力...", height=250)

# アクションボタン
col1, col2 = st.columns(2)

with col1:
    if st.button("🚀 LINEで報告を送信", use_container_width=True):
        if user["line_token"] and user["line_user_id"]:
            msg = f"【{selected_date} 報告】\n担当: {user['user_name']}\n---\n{report_text}"
            headers = {"Authorization": f"Bearer {user['line_token']}", "Content-Type": "application/json"}
            data = {"to": user["line_user_id"], "messages": [{"type": "text", "text": msg}]}
            if requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data).status_code == 200:
                st.success("LINE送信完了")
            else: st.error("送信失敗")
        else: st.warning("LINE情報がスプレッドシートにありません")

with col2:
    if st.button("💡 AIコーチのタスク提案", use_container_width=True):
        if report_text:
            with st.spinner("AIが思考中..."):
                advice = ai_coach_advice(report_text, cache['selected_model'], user['user_role'])
                st.session_state.advice = advice
        else: st.warning("内容を入力してください")

# AI提案の表示
if 'advice' in st.session_state:
    st.write("---")
    st.subheader("🤖 AIコーチからのアドバイス")
    st.markdown(st.session_state.advice)

# --- 5. サイドバー (設定はここへ集約) ---
with st.sidebar:
    st.header("⚙️ 設定")
    with st.expander("詳細設定"):
        models = get_latest_models()
        sel = st.selectbox("AIモデル選択", models, index=0)
        cache["selected_model"] = sel
        
        if st.button("設定を強制保存"):
            save_cache(cache)
            st.toast("保存完了")
    
    st.write("---")
    if st.button("🔄 情報を再同期"):
        st.session_state.pop('user_info')
        st.rerun()

st.caption(f"Status: {cache['selected_model']} 稼働中")
