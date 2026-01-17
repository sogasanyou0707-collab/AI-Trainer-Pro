import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime

# ==========================================
# 1. ページ設定 & [Phase 1] モバイル表示対策CSS
# ==========================================
st.set_page_config(page_title="バスケ練習管理", layout="wide")

st.markdown("""
    <style>
    /* 全体の基本設定（白背景・黒文字） */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: white !important;
        color: black !important;
    }
    /* すべてのテキストを黒に強制 */
    h1, h2, h3, p, span, label, li, .stMarkdown {
        color: black !important;
    }
    /* ボタン（保存、新規登録など）のスタイル：白背景・黒枠・黒文字 */
    button, div.stButton > button, div.stFormSubmitButton > button {
        background-color: white !important;
        color: black !important;
        border: 2px solid black !important;
        border-radius: 8px !important;
        font-weight: bold !important;
    }
    /* セレクトボックス（ユーザー選択など）のリスト対策 */
    div[data-baseweb="select"] > div, ul[role="listbox"], li[role="option"] {
        background-color: white !important;
        color: black !important;
    }
    /* 入力エリア（四角い枠）が黒くなるのを防ぐ */
    input, textarea, div[data-baseweb="input"] {
        background-color: white !important;
        color: black !important;
        border: 1px solid black !important;
        -webkit-text-fill-color: black !important; /* iPhone Safari対策 */
    }
    /* スライダーなどの色調整 */
    .stSlider { color: black !important; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. Google Sheets 接続 & データ読み込み
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)

def load_all_sheets():
    try:
        p = conn.read(worksheet="Profiles", ttl=0)
        s = conn.read(worksheet="Settings", ttl=0)
        h = conn.read(worksheet="History", ttl=0)
        m = conn.read(worksheet="Metrics", ttl=0)
        return p, s, h, m
    except Exception as e:
        st.error(f"シートの読み込みに失敗しました。名前を確認してください: {e}")
        return [pd.DataFrame()] * 4

profiles_df, settings_df, history_df, metrics_df = load_all_sheets()

# ==========================================
# 3. メインUI：ユーザー選択
# ==========================================
st.title("🏀 バスケ練習管理システム")

user_list = profiles_df["user_id"].unique().tolist() if not profiles_df.empty else []
selected_user = st.selectbox("👤 ユーザーを選択", options=["新規登録"] + user_list)

is_new = selected_user == "新規登録"
# 既存ユーザーの場合はデータを抽出（nan対策付き）
u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0] if not is_new else pd.Series()

# ==========================================
# 4. [Phase 2] ロードマップ & 今日のタスク表示
# ==========================================
done_tasks = [] # 完了タスク格納用

if not is_new:
    st.divider()
    
    # --- ロードマップ ---
    st.subheader("🏁 成長ロードマップ")
    raw_roadmap = u_prof.get("roadmap")
    roadmap_text = raw_roadmap if pd.notna(raw_roadmap) and raw_roadmap != "" else "ロードマップが設定されていません。"
    st.info(roadmap_text)

    # --- 今日の練習タスク（チェックボックス形式） ---
    st.subheader("📋 今日の練習タスク")
    tasks_raw = u_prof.get("tasks_json")
    
    if pd.isna(tasks_raw) or tasks_raw == "" or tasks_raw == "[]":
        st.write("今日のタスクは設定されていません。")
    else:
        try:
            tasks_list = json.loads(tasks_raw)
            for i, task in enumerate(tasks_list):
                if st.checkbox(task, key=f"task_{i}"):
                    done_tasks.append(task)
        except:
            st.error("⚠️ tasks_json の形式が正しくありません。 [\"練習1\", \"練習2\"] の形式で入力してください。")
            st.code(f"現在の値: {tasks_raw}")
    st.divider()

# ==========================================
# 5. 設定・プロフィール編集セクション
# ==========================================
with st.expander("⚙️ ユーザー詳細設定・項目カスタマイズ", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=u_prof.get("user_id", ""))
    col1, col2 = st.columns(2)
    height = col1.number_input("身長 (cm)", value=float(u_prof.get("height", 0.0)))
    weight = col2.number_input("体重 (kg)", value=float(u_prof.get("weight", 0.0)))
    
    goal = st.text_area("現在の目標 (goal)", value=u_prof.get("goal", "") if pd.notna(u_prof.get("goal")) else "")
    coach = st.text_input("担当コーチ (coach_name)", value=u_prof.get("coach_name", "") if pd.notna(u_prof.get("coach_name")) else "")
    
    # 計測項目の整理（カンマ区切りでMetricsシートに飛ばす項目を定義）
    raw_metrics = u_prof.get("tracked_metrics")
    metrics_str = st.text_input("計測項目（カンマ区切り）", 
                                value=raw_metrics if pd.notna(raw_metrics) else "シュート率,ハンドリング")

# ==========================================
# 6. 今日の記録入力セクション
# ==========================================
st.subheader("📝 今日の振り返り")
today_date = datetime.now().strftime("%Y-%m-%d")

rate = st.slider("自己評価 (rate)", 1, 5, 3)
user_note = st.text_area("今日頑張ったこと (note)")

# 動的に計測項目の入力欄を作成
metric_inputs = {}
for m_name in metrics_str.split(","):
    m_name = m_name.strip()
    if m_name:
        metric_inputs[m_name] = st.number_input(f"{m_name} の結果", value=0.0)

# ==========================================
# 7. 保存ロジック（History / Metrics / Profiles）
# ==========================================
if st.button("設定と記録を保存する"):
    if not u_id:
        st.error("ユーザーIDを入力してください。")
    else:
        # --- A. Profilesシートの更新（既存なら置換、新規なら追加） ---
        new_profile_data = {
            "user_id": u_id, "height": height, "weight": weight, "goal": goal,
            "coach_name": coach, "tracked_metrics": metrics_str,
            "roadmap": u_prof.get("roadmap") if not is_new else
