import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# --- 定数・設定管理 ---
CONFIG_FILE = "app_settings.json"
[cite_start]SPREADSHEET_NAME = "AI_Trainer_DB"  # スプレッドシート名 [cite: 1]
[cite_start]SHEET_NAME = "Profiles"             # シート名 [cite: 1]

class AppManager:
    def __init__(self, gemini_api_key):
        genai.configure(api_key=gemini_api_key)
        self.settings = self.load_settings()

    def load_settings(self):
        """ローカルのキャッシュから設定を読み込む"""
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"selected_model": None, "line_token": None, "line_user_id": None}

    def save_settings(self):
        """現在の設定（モデル名やLINE情報）をキャッシュに保存"""
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=4, ensure_ascii=False)

    # --- モデル動的取得機能 ---
    def get_latest_models(self):
        """1.5系に依存せず、現在利用可能な最新モデルを動的に取得"""
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                model_name = m.name.replace('models/', '')
                # 1.5系（Flashなど）を除外、あるいは最新世代(2.5/3.0以降)を優先するロジック
                if "1.5" not in model_name: 
                    available_models.append(model_name)
        return available_models

    # --- スプレッドシート連携機能 ---
    def fetch_line_credentials(self, service_account_json):
        """スプレッドシートのProfilesシート（E列、F列）からLINE情報を取得"""
        [cite_start]# [cite: 1]に基づき、E列(line_token)とF列(line_user_id)を読み込む
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file(service_account_json, scopes=scopes)
        client = gspread.authorize(creds)
        
        sheet = client.open(SPREADSHEET_NAME).worksheet(SHEET_NAME)
        
        # 2行目のデータを取得（必要に応じて検索ロジックを追加）
        [cite_start]self.settings["line_token"] = sheet.acell('E2').value   # E列: line_token [cite: 1]
        [cite_start]self.settings["line_user_id"] = sheet.acell('F2').value # F列: line_user_id [cite: 1]
        self.save_settings()
        return self.settings["line_token"], self.settings["line_user_id"]

    # --- LINE報告機能 ---
    def send_line_report(self, message):
        """本日のサマリーを指定されたLINEアカウントに送信"""
        token = self.settings.get("line_token")
        user_id = self.settings.get("line_user_id")
        
        if not token or not user_id:
            print("LINEの連携情報が設定されていません。")
            return False

        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        data = {
            "to": user_id,
            "messages": [{"type": "text", "text": message}]
        }
        
        response = requests.post(url, headers=headers, json=data)
        return response.status_code == 200

# --- 実行イメージ ---
if __name__ == "__main__":
    # 初期化（APIキーなどは環境に合わせて設定）
    GEMINI_KEY = "YOUR_GEMINI_API_KEY"
    SERVICE_ACCOUNT = "service_account.json" # Google Cloudの認証ファイル
    
    app = AppManager(GEMINI_KEY)

    # 1. ログイン時などに最新モデルリストを取得（設定画面のプルダウン用）
    models = app.get_latest_models()
    print(f"利用可能な最新モデル: {models}")

    # 2. モデルを選択して保存（例としてリストの先頭を選択）
    if models:
        app.settings["selected_model"] = models[0]
        app.save_settings()

    # 3. 必要に応じてスプレッドシートからLINE情報を同期
    # 設定画面の「LINE情報更新」ボタンなどで実行
    app.fetch_line_credentials(SERVICE_ACCOUNT)

    # 4. 本日の内容を報告
    summary_text = "【本日の報告】解析作業が完了しました。使用モデル: " + app.settings["selected_model"]
    if app.send_line_report(summary_text):
        print("LINEへの報告が完了しました。")
    else:
        print("報告に失敗しました。")
