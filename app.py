import streamlit as st
import datetime

# --- CSS: スマホでも縦に並ばせないための設定 ---
st.markdown("""
    <style>
    /* 横スクロール可能なコンテナ */
    .scroll-container {
        display: flex;
        overflow-x: auto;
        gap: 15px;
        padding: 10px 5px;
        white-space: nowrap;
        -webkit-overflow-scrolling: touch; /* iOSのスクロールを滑らかに */
    }
    /* 各日付のカード */
    .day-card {
        min-width: 55px;
        text-align: center;
        background: #ffffff;
        border-radius: 12px;
        padding: 10px 5px;
        box-shadow: 0px 2px 4px rgba(0,0,0,0.1);
        border: 1px solid #eee;
    }
    .day-label { font-size: 0.7rem; color: #666; margin-bottom: 5px; }
    .day-status { font-size: 1.2rem; margin: 5px 0; }
    .day-num { font-size: 0.9rem; font-weight: bold; }
    /* 練習した日の強調 */
    .done { background-color: #e6f9ec; border-color: #28a745; }
    </style>
    """, unsafe_allow_html=True)

st.subheader("🗓️ 今週の進捗")

# データ準備（本来はスプレッドシートから取得）
today = datetime.date.today()
days = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
# 仮の達成データ（Metricsシートのデータと照合する想定）
done_days = [True, False, True, True, False, True, True] 

# --- HTMLの組み立て ---
html_str = '<div class="scroll-container">'
for i, day in enumerate(days):
    is_done = done_days[i]
    status_icon = "🏀" if is_done else "⚪"
    status_class = "day-card done" if is_done else "day-card"
    
    html_str += f"""
        <div class="{status_class}">
            <div class="day-label">{day.strftime('%a')}</div>
            <div class="day-status">{status_icon}</div>
            <div class="day-num">{day.day}</div>
        </div>
    """
html_str += '</div>'

# 描画
st.markdown(html_str, unsafe_allow_html=True)

st.info("💡 横にスワイプして過去の記録を確認できます")
