import streamlit as st
import datetime
import pandas as pd

# --- 1. データ取得ロジック (Google Sheets連携の核) ---
def get_weekly_data(user_id):
    # 本来はここで st.connection("gsheets") 等を使用して Metrics シートを読み込む
    # 今回は表示ロジックを優先するため、ダミーデータを作成します
    today = datetime.date.today()
    dates = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
    
    # 実際はシートから df = conn.read(...) してフィルタリング
    data = {
        "date": dates,
        "is_done": [True, False, True, True, False, True, True],
        "speed": [19.5, 0, 19.2, 18.8, 0, 18.5, 18.2], # ハンドリングスピード
        "comment": ["絶好調！", "", "リズムが良い", "スピードアップ！", "", "最高記録！", "完璧！"]
    }
    return pd.DataFrame(data)

# --- 2. 状態管理 (どの日付が選択されているか) ---
if "selected_date_idx" not in st.session_state:
    st.session_state.selected_date_idx = 6 # デフォルトは「今日」

# --- 3. UI実装 ---
st.title("🏀 Team Effort Coach")

# A. ユーザー・コーチ情報 (固定表示)
with st.container():
    col1, col2 = st.columns(2)
    col1.metric("Player", "息子さん")
    col2.metric("Coach", "安西コーチ")
    st.info(f"🎯 **目標:** ハンドリング18秒切り！")

# B. 横スクロールカレンダー (データ連動)
df_weekly = get_weekly_data("user_001")

# CSSで横スクロールを強制
st.markdown("""
    <style>
    .scroll-wrapper { display: flex; overflow-x: auto; gap: 10px; padding: 10px 0; }
    .day-btn { 
        min-width: 60px; height: 80px; border-radius: 15px; 
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        border: 2px solid #ddd; background: white; cursor: pointer;
    }
    .selected { border-color: #ff4b4b; background-color: #fff0f0; }
    </style>
""", unsafe_allow_html=True)

# Streamlitのボタンで選択を切り替える(モバイルで押しやすくするため)
cols = st.columns(7)
for i, row in df_weekly.iterrows():
    label = f"{row['date'].strftime('%a')}\n{'🏀' if row['is_done'] else '⚪'}\n{row['date'].day}"
    if cols[i].button(label, key=f"btn_{i}"):
        st.session_state.selected_date_idx = i

# C. 選択された日の詳細表示 (カード形式)
selected_row = df_weekly.iloc[st.session_state.selected_date_idx]

st.markdown("---")
with st.container():
    st.subheader(f"📅 {selected_row['date'].strftime('%m/%d')} の記録")
    
    if selected_row['is_done']:
        c1, c2 = st.columns(2)
        c1.markdown(f"**ハンドリング:**\n## {selected_row['speed']} 秒")
        c2.markdown(f"**コーチの評価:**\n> {selected_row['comment']}")
    else:
        st.warning("この日の練習記録はありません。")

# D. アクションボタン (一番押しやすい場所に配置)
st.markdown("---")
if st.button("🚀 今日の練習を記録する", use_container_width=True, type="primary"):
    st.session_state.show_input_form = True # 入力フォームへ誘導
