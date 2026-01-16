import streamlit as st
import google.generativeai as genai
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import re

# --- 1. ページ設定 ---
st.set_page_config(page_title="AI Trainer Pro", layout="wide")
st.title("🏃‍♂️ AI Trainer Pro")

# --- 2. 接続設定 ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-3-flash-preview")

    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"接続設定エラー: {e}")
    st.stop()

# --- 3. データ処理関数 ---
def load_data():
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0)
        df.columns = df.columns.str.strip() # 空白除去
        return df
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return pd.DataFrame()

# --- 4. メイン画面 ---
tab1, tab2, tab3 = st.tabs(["プロフィール", "カレンダー", "項目管理"])

# --- Tab 1: プロフィール ---
with tab1:
    st.subheader("👤 ユーザー設定")
    df = load_data()
    
    input_id = st.text_input("ログインIDを入力してください", value="")

    if input_id:
        # 【重要】実際のスプレッドシートに合わせて「user_id」を使用
        target_col = "user_id" 
        
        if target_col not in df.columns:
            st.error(f"列名エラー: スプレッドシートの1行目を 'user_id' に修正してください。現在の列名: {list(df.columns)}")
        else:
            user_data = df[df[target_col].astype(str) == str(input_id)]
            is_new_user = user_data.empty
            
            if not is_new_user:
                st.success(f"{input_id} さんのデータを読み込みました")
                row = user_data.iloc[0]
                # スプレッドシートに合わせて小文字のキーで取得（無い場合はデフォルト値）
                h_val = row.get("height", 170.0)
                w_val = row.get("weight", 60.0)
                g_val = row.get("goal", "")
            else:
                st.warning(f"ID: {input_id} は未登録です。新規登録を行います。")
                h_val, w_val, g_val = 170.0, 60.0, "ここに目標を入力"

            # フォーム表示（年齢はスプレッドシートに無いため、一旦目標と身体データのみ）
            col1, col2 = st.columns(2)
            with col1:
                new_height = st.number_input("身長 (cm)", value=float(h_val))
                new_weight = st.number_input("体重 (kg)", value=float(w_val))
            with col2:
                new_goal = st.text_area("目標", value=str(g_val))

            if st.button("スプレッドシートに保存"):
                # 新しい行の作成（列名をスプレッドシートに合わせる）
                new_entry = {
                    "user_id": input_id,
                    "height": new_height,
                    "weight": new_weight,
                    "goal": new_goal
                }
                
                if is_new_user:
                    updated_df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
                else:
                    # 既存行の更新
                    df.loc[df["user_id"].astype(str) == str(input_id), ["height", "weight", "goal"]] = [new_height, new_weight, new_goal]
                    updated_df = df
                
                try:
                    conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", data=updated_df)
                    st.balloons()
                    st.success("保存が完了しました！")
                except Exception as e:
                    st.error(f"更新エラー: {e}")

# --- Tab 2: カレンダー ---
with tab2:
    st.subheader("🗓 今日のメニュー生成")
    if "db" not in st.session_state:
        st.session_state.db = {"daily_message": "生成ボタンを押してください", "tasks": []}

    target_goal = new_goal if 'new_goal' in locals() else "健康維持"

    if st.button("Gemini 3 でメニュー生成"):
        with st.spinner("Gemini 3 が考案中..."):
            try:
                prompt = f"目標「{target_goal}」に適した運動タスクを4つと、励ましを [MESSAGE]...[/MESSAGE] で出力してください。"
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
