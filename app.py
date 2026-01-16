import streamlit as st
import datetime

# --- 1. CSSによるモバイル微調整 ---
st.markdown("""
    <style>
    /* 1画面に情報を収めるための余白調整 */
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
    /* カード風の見た目 */
    .status-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 10px;
        border-left: 5px solid #ff4b4b;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ユーザー選択・登録セクション ---
st.title("🏀 AI Basketball Coach")

# 本来はGoogle Sheetsから取得するデータを想定
user_list = ["息子さん", "ユーザーB"] 
selected_user = st.selectbox("👤 ユーザーを選択", user_list, help="登録済みのユーザーを切り替えます")

# 新規登録はエクスパンダーで「隠して」おく（画面を広く使うため）
with st.expander("✨ 新規ユーザーを登録する"):
    with st.form("new_user_form"):
        new_name = st.text_input("名前を入力")
        new_goal = st.text_input("目標（例：ハンドリング20秒切り）")
        if st.form_submit_button("登録実行"):
            st.success(f"{new_name}さんを登録しました！")

st.divider()

# --- 3. トップ画で見える「現在のステータス」 ---
# サイドバーからメイン画面のトップへ移動
col1, col2 = st.columns(2)

with col1:
    st.markdown(f"""
        <div class="status-card">
            <small>現在のコーチ</small><br>
            <strong>🔥 安西コーチ</strong>
        </div>
    """, unsafe_allow_html=True)

with col2:
    # Google SheetsのProfilesから取得した目標を表示
    current_goal = "ハンドリングスピード 18秒台！" 
    st.markdown(f"""
        <div class="status-card">
            <small>現在の目標</small><br>
            <strong>🎯 {current_goal}</strong>
        </div>
    """, unsafe_allow_html=True)

st.divider()

# --- 4. 視認性を上げた「カード型カレンダー」 ---
st.subheader("🗓️ 今週の進捗")

# 直近7日間の日付を生成
today = datetime.date.today()
days = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]

# モバイルでは横並びは限界があるため、4列（または2列×2段）で表示
cols = st.columns(7) # 1週間分
for i, day in enumerate(days):
    with cols[i]:
        # 達成率に応じた色判定（仮）
        is_done = (i % 2 == 0) # 偶数日は練習したことにする
        color = "🟢" if is_done else "⚪"
        st.markdown(f"<div style='text-align: center;'><small>{day.strftime('%a')}</small><br>{color}<br><b>{day.day}</b></div>", unsafe_allow_html=True)

st.info("💡 各日付をタップすると詳細（コーチのフィードバック）を確認できます。")
