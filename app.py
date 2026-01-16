import streamlit as st

# --- 1. トップセクション：ユーザー管理 ---
st.title("🏀 Basketball Coach AI")

# Profilesシートからユーザー名を取得（仮のリスト）
user_list = ["息子さん", "ゲストA"] 
selected_user = st.selectbox("ユーザーを選択してください", user_list)

with st.expander("＋ 新規ユーザーを登録する"):
    new_name = st.text_input("名前")
    if st.button("登録"):
        # スプレッドシートへの保存ロジック
        pass

st.divider()

# --- 2. メイン表示：コーチと目標（サイドバーから移動） ---
col1, col2 = st.columns(2)
with col1:
    st.metric(label="現在のコーチ", value="安西コーチ")
with col2:
    st.info(f"**目標:** ハンドリング速度向上！")

# --- 3. 視認性を上げたカレンダーエリア ---
st.subheader("🗓️ 今週の練習記録")
# ここに横長、あるいはカード型のカレンダー描画ロジックを配置
