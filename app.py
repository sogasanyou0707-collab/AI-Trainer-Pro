import streamlit as st
import google.generativeai as genai
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import re

# --- 1. ページ設定 ---
st.set_page_config(page_title="AI Trainer Pro", layout="wide")
st.title("🏃‍♂️ AI Trainer Pro")

# --- 2. 接続設定 (Secrets) ---
try:
    # Gemini API設定
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
    # ご指定のモデル（Gemini 3）
    model = genai.GenerativeModel("gemini-3-flash-preview")

    # GSheets設定
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"接続設定エラー: {e}")
    st.stop()

# --- 3. データ処理関数 ---
def load_data():
    return conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0)

# --- 4. メイン画面（タブ構成） ---
tab1, tab2, tab3 = st.tabs(["プロフィール", "カレンダー", "項目管理"])

# --- Tab 1: プロフィール（検索・保存・新規登録） ---
with tab1:
    st.subheader("👤 ユーザー設定")
    df = load_data()
    
    # ID入力（トリガー）
    input_id = st.text_input("ログインIDを入力してください", value="")

    if input_id:
        # 列名チェック（UserIDがない場合のエラー回避）
        if "UserID" not in df.columns:
            st.error("スプレッドシートに 'UserID' 列が見つかりません。1行目の見出しを確認してください。")
        else:
            # ユーザー検索
            user_data = df[df["UserID"] == input_id]
            
            # 既存ユーザーか新規ユーザーかの判定
            is_new_user = user_data.empty
            
            if not is_new_user:
                st.success(f"{input_id} さんのデータを読み込みました")
                row = user_data.iloc[0]
                h_val, w_val, a_val, g_val = row["Height"], row["Weight"], row["Age"], row["Goal"]
            else:
                st.warning(f"ID: {input_id} は未登録です。新規登録を行います。")
                h_val, w_val, a_val, g_val = 170.0, 60.0, 30, "ここに目標を入力"

            # 入力フォーム
            col1, col2 = st.columns(2)
            with col1:
                new_height = st.number_input("身長 (cm)", value=float(h_val))
                new_weight = st.number_input("体重 (kg)", value=float(w_val))
            with col2:
                new_age = st.number_input("年齢", value=int(a_val))
                new_goal = st.text_area("目標", value=str(g_val))

            # 保存ボタン（更新・新規追加）
            if st.button("スプレッドシートに保存"):
                new_entry = {
                    "UserID": input_id,
                    "Height": new_height,
                    "Weight": new_weight,
                    "Age": new_age,
                    "Goal": new_goal
                }
                
                if is_new_user:
                    # 新規追加
                    updated_df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
                else:
                    # 既存行の更新
                    df.loc[df["UserID"] == input_id, ["Height", "Weight", "Age", "Goal"]] = \
                        [new_height, new_weight, new_age, new_goal]
                    updated_df = df
                
                try:
                    conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", data=updated_df)
                    st.balloons()
                    st.success("スプレッドシートを更新しました！")
                except Exception as e:
                    st.error(f"保存エラー: {e}")

# --- Tab 2: カレンダー（Gemini 3 連携） ---
with tab2:
    st.subheader("🗓 今日のメニュー生成")
    if "db" not in st.session_state:
        st.session_state.db = {"daily_message": "生成ボタンを押してください", "tasks": []}

    # 目標に基づいたプロンプト（プロフィールが読み込まれている場合）
    user_goal = new_goal if 'new_goal' in locals() else "健康維持"

    if st.button("Gemini 3 でメニュー生成"):
        with st.spinner("AIが考案中..."):
            try:
                prompt = f"目標「{user_goal}」に適した運動タスクを4つと、励ましを [MESSAGE]...[/MESSAGE] で出力してください。"
                res = model.generate_content(prompt)
                full_text = res.text
                msg_match = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", full_text, re.DOTALL)
                st.session_state.db["daily_message"] = msg_match.group(1).strip() if msg_match else full_text
                tasks = [l.strip("- *") for l in full_text.split("\n") if l.strip().startswith(("-", "*"))]
                st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks[:4]]
                st.rerun()
            except Exception as e:
                st.error(f"AI生成エラー: {e}")

    st.info(st.session_state.db["daily_message"])
    for i, t in enumerate(st.session_state.db["tasks"]):
        st.checkbox(t["task"], key=f"task_{i}")

# --- Tab 3: 項目管理 ---
with tab3:
    st.subheader("全データ確認")
    st.dataframe(load_data())
