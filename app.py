import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

st.title("AIトレーナー・プロ")

# 1. スプレッドシートへの接続設定
conn = st.connection("gsheets", type=GSheetsConnection)

# 全データを読み込み（シート名: Profiles）
df = conn.read(worksheet="Profiles")
df.columns = df.columns.str.strip() # 列名の空白を整理

# 2. ユーザーIDの入力
user_id_input = st.text_input("UserIDを入力してください", placeholder="例: takine")

if user_id_input:
    # 既存ユーザーかどうかをチェック
    user_data = df[df['user_id'] == user_id_input]

    if not user_data.empty:
        # --- 既存ユーザーの場合：データを読み取る ---
        st.success(f"おかえりなさい、{user_id_input}さん！")
        
        # 既存データを初期値としてフォームを表示（編集も可能に）
        with st.form("update_form"):
            height = st.number_input("身長 (cm)", value=float(user_data.iloc[0]['height']))
            weight = st.number_input("体重 (kg)", value=float(user_data.iloc[0]['weight']))
            goal = st.text_area("目標", value=str(user_data.iloc[0]['goal']))
            
            if st.form_submit_button("データを更新する"):
                # 該当行を更新して保存する処理（今回は簡易的に全上書き更新）
                df.loc[df['user_id'] == user_id_input, ['height', 'weight', 'goal']] = [height, weight, goal]
                conn.update(worksheet="Profiles", data=df)
                st.balloons()
                st.success("スプレッドシートのデータを更新しました！")

    else:
        # --- 新規ユーザーの場合：登録フォームを表示 ---
        st.info("新規ユーザーです。プロフィールを登録してください。")
        
        with st.form("registration_form"):
            height = st.number_input("身長 (cm)", min_value=0.0, step=0.1)
            weight = st.number_input("体重 (kg)", min_value=0.0, step=0.1)
            goal = st.text_area("目標を入力してください")
            
            if st.form_submit_button("新規登録して保存"):
                # 新しい行を作成
                new_row = pd.DataFrame([{
                    "user_id": user_id_input,
                    "height": height,
                    "weight": weight,
                    "goal": goal
                }])
                # 既存のデータフレームに結合してスプレッドシートを更新
                updated_df = pd.concat([df, new_row], ignore_index=True)
                conn.update(worksheet="Profiles", data=updated_df)
                st.success(f"{user_id_input}さんの情報をスプレッドシートに保存しました！")
                st.rerun() # 画面をリフレッシュしてログイン状態にする
