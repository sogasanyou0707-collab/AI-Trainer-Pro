import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
from datetime import datetime

# --- 設定 ---
# Gemini APIの設定（Secretsから読み込み）
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
# 指定されたモデルに変更
model = genai.GenerativeModel('gemini-3-flash-preview')

# スプレッドシート接続
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 関数定義 ---
def load_data(worksheet):
    """指定したワークシートからデータを読み込み、列名の空白を削除する"""
    try:
        df = conn.read(worksheet=worksheet)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"シート '{worksheet}' の読み込みに失敗しました: {e}")
        return None

def save_history(user_id, data_dict, memo):
    """日々の記録をHistoryシートに保存する"""
    try:
        # 既存のHistoryデータを読み込む
        history_df = load_data("History")
        if history_df is None: return False

        # 保存する新しい行のデータを作成
        new_row_data = {
            "日付": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_id": user_id,
            "今日頑張ったこと": memo
        }
        # 記録項目のデータを追加
        new_row_data.update(data_dict)
        
        new_row = pd.DataFrame([new_row_data])
        
        # 既存データと結合して保存
        updated_df = pd.concat([history_df, new_row], ignore_index=True)
        conn.update(worksheet="History", data=updated_df)
        return True
    except Exception as e:
        st.error(f"データの保存に失敗しました: {e}")
        return False

# --- メインアプリ ---
st.set_page_config(page_title="AIトレーナー・プロ", layout="wide")

# サイドバーでユーザーID入力とメニュー選択
with st.sidebar:
    st.title("AIトレーナー・プロ")
    user_id = st.text_input("UserIDを入力", placeholder="例: takine")
    
    menu = st.radio(
        "メニューを選択",
        ["📋 今日のメニュー", "📈 グラフ", "📅 カレンダー", "🚀 ロードマップ", "💬 相談", "🏆 称号", "⚙️ 設定"]
    )

# ユーザーIDが入力されていない場合の表示
if not user_id:
    st.info("← サイドバーでUserIDを入力してください。")
    st.stop()

# ユーザー情報の読み込み（存在チェック用）
profiles_df = load_data("Profiles")
if profiles_df is None: st.stop()
user_data = profiles_df[profiles_df['user_id'] == user_id]

if user_data.empty:
    st.warning("ユーザー登録が見つかりません。「⚙️ 設定」メニューからプロフィールを登録してください。")
else:
    st.sidebar.success(f"ログイン中: {user_id}さん")

# --- メニューごとの画面表示 ---
if menu == "📋 今日のメニュー":
    st.header("📋 今日の記録と報告")
    
    # 設定シートから記録項目を読み込む
    settings_df = load_data("Settings")
    if settings_df is None or settings_df.empty:
        st.warning("記録項目が設定されていません。「⚙️ 設定」メニューで項目を追加してください。")
        st.stop()
        
    record_items = settings_df['項目名'].tolist()
    input_data = {}

    with st.form("daily_report_form"):
        st.subheader("本日の記録")
        # 記録項目を動的に表示
        cols = st.columns(2)
        for i, item in enumerate(record_items):
            with cols[i % 2]:
                # ここでは簡易的に全て数値入力としています。将来的にデータ型も設定可能にします。
                input_data[item] = st.number_input(f"{item}", step=0.1, key=f"input_{item}")
        
        st.subheader("振り返り")
        today_memo = st.text_area("今日頑張ったこと（自由報告）", placeholder="例：今日はスクワットを限界まで追い込みました！")
        
        # 保存ボタン
        submitted = st.form_submit_button("今日の成果を保存 ＆ LINE報告送信")
        
        if submitted:
            if save_history(user_id, input_data, today_memo):
                st.success("記録を保存しました！")
                st.info("（LINE報告機能は今後実装予定です）")
                
                # Geminiによる簡易フィードバック（例）
                prompt = f"ユーザーが以下のトレーニング報告をしました。「{today_memo}」。トレーナーとして短く励ましのコメントをしてください。"
                response = model.generate_content(prompt)
                st.write(f"🤖AIコーチからのコメント: {response.text}")
            else:
                st.error("保存に失敗しました。")

elif menu == "⚙️ 設定":
    st.header("⚙️ 設定")
    st.write("ここにプロフィール設定、記録項目の追加・削除、LINE設定などを実装します。")
    #前回のプロフィール更新コードをここに移動しても良いでしょう

# 他のメニューはプレースホルダーを表示
else:
    st.header(menu)
    st.write(f"「{menu}」機能は現在開発中です。")
