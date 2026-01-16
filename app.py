import streamlit as st
import google.generativeai as genai
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import re
import streamlit as st
import pandas as pd

# (1) まず、スプレッドシートやCSVを読み込んで「df」に代入する
# ※ここはご自身の読み込み処理（read_csvなど）に書き換えてください
df = pd.read_csv("your_data.csv") 

# (2) 「df」が作られた後で、中身を確認するコードを書く
st.write("データの行数:", len(df))
st.write("認識されている列名:", df.columns.tolist())

# (3) その後、特定の列（身長など）を表示する
if '身長' in df.columns:
    st.write(df['身長'])
else:
    st.error("列名 '身長' が見つかりません。")
# 読み込んだデータが空かどうか、列名が何かを表示する
print("データの行数:", len(df))
print("認識されている列名:", df.columns.tolist())

# 4. タブ作成
tab1, tab2, tab3 = st.tabs(["プロフィール", "カレンダー", "項目管理"])

# --- Tab 1: プロフィール (検索・表示・編集) ---
with tab1:
    st.subheader("👤 ユーザー設定")
    profiles_df = load_data("Profiles")
    
    # ID入力
    input_id = st.text_input("ログインIDを入力してください（例: User1）", value="")
    
    if input_id:
        if not profiles_df.empty and "UserID" in profiles_df.columns:
            # 入力されたIDでデータを抽出
            user_data = profiles_df[profiles_df["UserID"] == input_id]
            
            if not user_data.empty:
                st.success(f"{input_id} さんのデータを読み込みました")
                row = user_data.iloc[0]
                
                # 各項目の表示・編集欄
                col1, col2 = st.columns(2)
                with col1:
                    height = st.number_input("身長 (cm)", value=float(row.get("Height", 0)))
                    weight = st.number_input("体重 (kg)", value=float(row.get("Weight", 0)))
                with col2:
                    age = st.number_input("年齢", value=int(row.get("Age", 0)))
                    goal = st.text_area("現在の目標", value=str(row.get("Goal", "")))
                
                if st.button("プロフィールを更新"):
                    st.info("スプレッドシートへの保存処理を実行します（準備中）")
            else:
                st.warning(f"ID: {input_id} は見つかりません。新規登録してください。")
        else:
            st.error("スプレッドシートに 'UserID' 列が見つかりません。1行目の項目名を確認してください。")

# --- Tab 2: カレンダー (メニュー生成) ---
with tab2:
    st.subheader("🗓 今日のメニュー")
    if "db" not in st.session_state:
        st.session_state.db = {"daily_message": "生成ボタンを押してください", "tasks": []}

    if st.button("Gemini 3 でメニュー生成"):
        with st.spinner("AIがトレーニングを構築中..."):
            try:
                res = model.generate_content("運動タスク4つと励ましを [MESSAGE]...[/MESSAGE] で出力して。")
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
    st.subheader("マスタデータ")
    settings_df = load_data("Settings")
    st.dataframe(settings_df)


