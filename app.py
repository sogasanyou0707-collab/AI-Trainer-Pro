import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime
import google.generativeai as genai

# ==========================================
# 1. ページ設定 & モバイル表示対策CSS
# ==========================================
st.set_page_config(page_title="バスケ練習管理 AI Pro", layout="wide")

st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: white !important; color: black !important;
    }
    h1, h2, h3, p, span, label, li, .stMarkdown { color: black !important; }
    button, div.stButton > button {
        background-color: white !important; color: black !important;
        border: 2px solid black !important; border-radius: 8px !important;
        font-weight: bold !important;
    }
    div[data-baseweb="select"] > div, ul[role="listbox"], li[role="option"] {
        background-color: white !important; color: black !important;
    }
    input, textarea, div[data-baseweb="input"] {
        background-color: white !important; color: black !important;
        border: 1px solid black !important; -webkit-text-fill-color: black !important;
    }
    .stSlider { color: black !important; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 接続設定
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except:
    st.warning("⚠️ Gemini APIキーを設定してください。")

def load_all_sheets():
    try:
        p = conn.read(worksheet="Profiles", ttl=0)
        h = conn.read(worksheet="History", ttl=0)
        m = conn.read(worksheet="Metrics", ttl=0)
        return p, h, m
    except:
        return [pd.DataFrame()] * 3

profiles_df, history_df, metrics_df = load_all_sheets()

# ==========================================
# 3. メインUI：ユーザーと日付選択
# ==========================================
st.title("🏀 AIコーチ & 成長グラフ")

col_u, col_d = st.columns(2)
with col_u:
    user_list = profiles_df["user_id"].dropna().unique().tolist() if not profiles_df.empty else []
    selected_user = st.selectbox("👤 ユーザーを選択", options=["新規登録"] + user_list)
with col_d:
    selected_date = st.date_input("📅 記録日を選択", value=datetime.now())
    target_date_str = selected_date.strftime("%Y-%m-%d")

is_new = selected_user == "新規登録"
u_prof = profiles_df[profiles_df["user_id"] == selected_user].iloc[0] if not is_new else pd.Series()

# ==========================================
# 4. 成長グラフ機能（新機能）
# ==========================================
if not is_new and not metrics_df.empty:
    st.divider()
    st.subheader("📈 成長グラフ")
    user_metrics = metrics_df[metrics_df["user_id"] == selected_user].copy()
    if not user_metrics.empty:
        # 日付でソート
        user_metrics["date"] = pd.to_datetime(user_metrics["date"])
        user_metrics = user_metrics.sort_values("date")
        
        # 項目ごとにグラフを表示
        metric_names = user_metrics["metric_name"].unique()
        for m_name in metric_names:
            m_data = user_metrics[user_metrics["metric_name"] == m_name]
            st.write(f"**{m_name} の推移**")
            st.line_chart(data=m_data, x="date", y="value")
    else:
        st.write("まだグラフにするデータがありません。")

# ==========================================
# 5. ユーザー詳細設定
# ==========================================
st.divider()
with st.expander("⚙️ ユーザー詳細設定", expanded=is_new):
    u_id = st.text_input("ユーザーID", value=str(u_prof.get("user_id", "")) if pd.notna(u_prof.get("user_id")) else "")
    goal_val = st.text_area("現在の目標", value=str(u_prof.get("goal", "")) if pd.notna(u_prof.get("goal")) else "")
    metrics_str = st.text_input("計測項目（カンマ区切り）", value=str(u_prof.get("tracked_metrics", "シュート率,ハンドリング")))

# ==========================================
# 6. AIメニュー提案機能（新機能）
# ==========================================
if not is_new:
    st.divider()
    st.subheader("📋 今日の練習メニュー")
    
    # AI提案ボタン
    if st.button("🪄 AIに練習メニューを提案してもらう"):
        with st.spinner("AIコーチがメニューを作成中..."):
            prompt = f"""
            あなたはバスケのプロコーチです。以下の目標を持つ小学6年生の選手に、今日やるべき練習メニューを3〜5つ提案してください。
            返信は必ず Pythonのリスト形式 ["練習1", "練習2", "練習3"] のみで出力してください。
            
            目標: {goal_val}
            最近の計測項目: {metrics_str}
            """
            try:
                response = model.generate_content(prompt)
                # AIの回答からJSON（リスト）部分を抽出
                ai_tasks_json = response.text.strip()
                if "```json" in ai_tasks_json:
                    ai_tasks_json = ai_tasks_json.split("```json")[1].split("```")[0].strip()
                elif "```" in ai_tasks_json:
                    ai_tasks_json = ai_tasks_json.split("```")[1].split("```")[0].strip()
                
                # Profilesシートのtasks_jsonを更新
                new_p = u_prof.to_dict()
                new_p["tasks_json"] = ai_tasks_json
                p_upd = pd.concat([profiles_df[profiles_df["user_id"] != selected_user], pd.DataFrame([new_p])], ignore_index=True)
                conn.update(worksheet="Profiles", data=p_upd)
                st.success("AIメニューを反映しました！ページを再読み込みしてください。")
                st.rerun()
            except Exception as e:
                st.error(f"メニュー生成エラー: {e}")

    # タスク表示
    tasks_raw = u_prof.get("tasks_json", "[]")
    done_tasks = []
    try:
        tasks_list = json.loads(tasks_raw)
        for i, t in enumerate(tasks_list):
            if st.checkbox(t, key=f"t_{i}"): done_tasks.append(t)
        if tasks_list:
            rate_val = int((len(done_tasks)/len(tasks_list))*100)
            st.write(f"📊 達成率: {rate_val}%")
            st.progress(rate_val/100)
    except: st.write("メニューが設定されていません。AIに提案してもらいましょう。")

# ==========================================
# 7. 今日の振り返り & 保存
# ==========================================
st.divider()
st.subheader(f"📝 {target_date_str} の振り返り")

# 過去の記録確認
existing_h = pd.Series()
if not is_new and not history_df.empty:
    m = history_df[(history_df["user_id"] == selected_user) & (history_df["date"] == target_date_str)]
    if not m.empty: existing_h = m.iloc[-1]

if not existing_h.empty and pd.notna(existing_h.get("coach_comment")):
    with st.chat_message("assistant"):
        st.write(existing_h.get("coach_comment"))

rate = st.slider("自己評価", 1, 5, int(existing_h.get("rate", 3)) if pd.notna(existing_h.get("rate")) else 3)
user_note = st.text_area("今日頑張ったこと", value=str(existing_h.get("note", "")) if pd.notna(existing_h.get("note")) else "")

# 数値入力
metric_inputs = {}
if metrics_str:
    m_names = metrics_str.split(",")
    cols = st.columns(len(m_names))
    for idx, m_name in enumerate(m_names):
        m_name = m_name.strip()
        prev = 0.0
        if not metrics_df.empty:
            m_m = metrics_df[(metrics_df["user_id"] == selected_user) & (metrics_df["date"] == target_date_str) & (metrics_df["metric_name"] == m_name)]
            if not m_m.empty: prev = float(m_m.iloc[-1]["value"])
        with cols[idx]:
            metric_inputs[m_name] = st.number_input(f"{m_name}", value=prev)

# 保存ボタン
if st.button("練習結果を保存してコーチに報告"):
    with st.spinner("AIコーチが確認中..."):
        # AIアドバイス生成
        prompt = f"コーチとしてアドバイスを。目標:{goal_val}, 評価:{rate}/5, 内容:{user_note}, 数値:{metric_inputs}"
        try:
            ai_comment = model.generate_content(prompt).text
        except:
            ai_comment = "ナイス練習！"

        # 各シート更新
        tasks_sum = "\n[完了]: " + ", ".join(done_tasks) if done_tasks else ""
        
        h_new = {"user_id": u_id, "date": target_date_str, "rate": rate, "note": user_note + tasks_sum, "coach_comment": ai_comment}
        h_upd = pd.concat([history_df[~((history_df["user_id"] == u_id) & (history_df["date"] == target_date_str))], pd.DataFrame([h_new])], ignore_index=True)
        
        m_rows = [{"user_id": u_id, "date": target_date_str, "metric_name": k, "value": v} for k, v in metric_inputs.items()]
        m_upd = pd.concat([metrics_df[~((metrics_df["user_id"] == u_id) & (metrics_df["date"] == target_date_str))], pd.DataFrame(m_rows)], ignore_index=True)

        conn.update(worksheet="History", data=h_upd)
        conn.update(worksheet="Metrics", data=m_upd)
        
        st.success("保存しました！グラフを確認してみよう。")
        st.rerun()
