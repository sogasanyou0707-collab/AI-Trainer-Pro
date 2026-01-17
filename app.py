import os
import json
import requests
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# --- 設定値 ---
CONFIG_FILE = "app_settings.json"
# スプレッドシート名（ご自身の環境に合わせて変更してください）
SPREADSHEET_NAME = "AI_Trainer_DB"
SHEET_NAME = "Profiles"

class AppManager:
    def __init__(self, gemini_api_key):
        genai.configure(api_key=gemini_api_key)
        self.settings = self.load_settings()

    def load_settings(self):
        """ローカルキャッシュから設定を読み込む"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        # デフォルト値
        return {"selected_model": "gemini-3-pro", "line_token": None, "line_user_id": None}

    def save_settings(self):
        """設定をローカルに保存"""
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=4, ensure_ascii=False)

    def get_latest_models(self):
        """APIから利用可能なモデルを動的に取得（1.5系を除外するロジック付）"""
        try:
            available_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    model_id = m.name.replace('models/', '')
                    # 1.5系に依存しないよう、2.5や3.0系を優先（1.5を含むものを除外）
                    if "1.5" not in model_id:
                        available_models.append(model_id)
            return available_models
        except Exception as e:
            print(f"モデル取得失敗: {e}")
            return ["gemini-3-pro"] # フォールバック

    def sync_line_credentials(self, service_account_json):
        """スプレッドシートのE列(Token)とF列(ID)から情報を取得して保存"""
        try:
            scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            creds = Credentials.from_service_account_file(service_account_json, scopes=scopes)
            client = gspread.authorize(creds)
            
            sheet = client.open(SPREADSHEET_NAME).worksheet(SHEET_NAME)
            
            # E2セルにトークン、F2セルにユーザーIDがある前提
            self.settings["line_token"] = sheet.acell('E2').value
            self.settings["line_user_id"] = sheet.acell('F2').value
            
            self.save_settings()
            return True
        except Exception as e:
            print(f"スプレッドシート同期失敗: {e}")
            return False

    def send_line_report(self, message):
        """LINEへ内容を送信"""
        token = self.settings.get("line_token")
        user_id = self.settings.get("line_user_id")
        
        if not token or not user_id:
            return "LINE情報が未設定です"

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

# --- 使用例 ---
if __name__ == "__main__":
    # 実際のAPIキーとサービスアカウントのパスを指定してください
    API_KEY = "YOUR_GEMINI_API_KEY"
    JSON_PATH = "service_account.json"

    app = AppManager(API_KEY)

    # 1. モデルリストを取得（設定画面のプルダウン等で使用）
    latest_models = app.get_latest_models()
    print(f"利用可能モデル: {latest_models}")

    # 2. スプレッドシートからLINE情報を「目立たない設定画面」の更新ボタン等で実行
    if app.sync_line_credentials(JSON_PATH):
        print("LINE連携情報をスプレッドシートから更新しました。")

    # 3. 報告の実行
    report_msg = f"【AI報告】本日の業務が完了しました。\n使用モデル: {app.settings.get('selected_model')}"
    if app.send_line_report(report_msg):
        print("LINE報告送信成功")
