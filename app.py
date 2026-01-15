import streamlit as st
import google.generativeai as genai
import re
from PIL import Image
import datetime
import calendar
import pandas as pd
import requests
from streamlit_gsheets import GSheetsConnection

# ==========================================
# 1. 基本設定（ここを書き換えてください）
# ==========================================
# Googleスプレッドシートの「共有」設定で、サービスアカウントのメールアドレスを「編集者」にするのを忘れずに！
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1vzYjmLH3vGtbOv_4A6UwCN7Pe-W24Q6hln-vtxLr1GU/edit?gid=0#gid=0"
GEMINI_API_KEY = "AIzaSyBjyTP93S-dFC5l0d7WbFfepLsf0WPAsWo"

st.set_page_config(page_title="AI Trainer Pro: Ultimate", layout="wide")
genai.configure(api_key=GEMINI_API_KEY)

# Googleスプレッドシート接続（シンプルに初期化）
conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================
# 2. データ読み書き関数
# ==========================================

def load_full_data_gs(user_id):
    """スプレッドシートからユーザーデータを一括取得"""
    default_data = {
        "profile": {"height": 170.0, "weight": 65.0, "goal": "未設定"},
        "history": {},
        "metrics_data": pd.DataFrame(),
        "metrics_defs": ["体重"],
        "line_config": {"access_token": "", "user_id": "", "enabled": False},
        "daily_message": "準備はいいか！限界を超えていこう！",
        "tasks": [], "roadmap": ""
    }
    try:
        # すべての read に spreadsheet=SPREADSHEET_URL を明示的に渡す
        p_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0)
        h_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="History", ttl=0)
        m_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Metrics", ttl=0)
        s_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Settings", ttl=0)

        prof = p_df[p_df['user_id'] == user_id].to_dict('records')
        hist = h_df[h_df['user_id'] == user_id]
        metr = m_df[m_df['user_id'] == user_id]
        sett = s_df[s_df['user_id'] == user_id]

        if prof:
            p = prof[0]
            default_data["profile"] = {"height": p.get('height', 170), "weight": p.get('weight', 65), "goal": p.get('goal', "未設定")}
            default_data["line_config"] = {
                "access_token": p.get('line_token', ""),
                "user_id": p.get('line_user_id', ""),
                "enabled": p.get('line_enabled', False)
            }
            default_data["daily_message"] = p.get('daily_message', "準備はいいか！")

        if not hist.empty:
            # 日付をキー、達成率を値とした辞書に変換
            default_data["history"] = hist.set_index('date')['rate'].to_dict()
        
        if not metr.empty:
            default_data["metrics_data"] = metr
            
        if not sett.empty:
            default_data["metrics_defs"] = sett['metric_defs'].unique().tolist()

        return default_data
    except Exception as e:
        # 接続エラーやシート未作成時は初期データを返す
        return default_data

def save_to_gs(worksheet_name, new_df, key_cols=['user_id', 'date']):
    """スプレッドシートの指定シートを更新（既存データとマージして上書き）"""
    try:
        existing_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        if key_cols:
            combined = combined.drop_duplicates(subset=key_cols, keep='last')
        
        # update にも spreadsheet=SPREADSHEET_URL を渡す
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=combined)
        return True
    except Exception as e:
        st.error(f"保存エラー ({worksheet_name}): {e}")
        return False

# ==========================================
# 3. ログインとセッション管理
# ==========================================

st.sidebar.title("🔑 ユーザーログイン")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="default").strip()

if not login_id:
    st.info("サイドバーでユーザーIDを入力してログインしてください。")
    st.stop()

# ログインIDが切り替わった場合にデータを再読み込み
if "current_user" not in st.session_state or st.session_state.get("current_user") != login_id:
    st.session_state.db = load_full_data_gs(login_id)
    st.session_state.current_user = login_id

# ==========================================
# 4. サイドバー：各種設定管理
# ==========================================

st.sidebar.divider()
with st.sidebar.expander("🎯 プロフィール設定"):
    h_val = st.number_input("身長 (cm)", value=float(st.session_state.db["profile"]["height"]))
    w_val = st.number_input("体重 (kg)", value=float(st.session_state.db["profile"]["weight"]))
    g_val = st.text_area("目標", value=st.session_state.db["profile"]["goal"])
    if st.button("設定を保存"):
        df = pd.DataFrame([{
            "user_id": login_id, "height": h_val, "weight": w_val, "goal": g_val,
            "line_token": st.session_state.db["line_config"]["access_token"],
            "line_user_id": st.session_state.db["line_config"]["user_id"],
            "line_enabled": st.session_state.db["line_config"]["enabled"],
            "daily_message": st.session_state.db["daily_message"]
        }])
        if save_to_gs("Profiles", df, key_cols=['user_id']):
            st.session_state.db["profile"] = {"height": h_val, "weight": w_val, "goal": g_val}
            st.sidebar.success("プロフィールを保存しました！")

with st.sidebar.expander("📊 記録項目の追加・削除", expanded=True):
    new_m = st.text_input("追加する項目名")
    if st.button("項目を追加"):
        if new_m and new_m not in st.session_state.db["metrics_defs"]:
            st.session_state.db["metrics_defs"].append(new_m)
            df = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df)
            st.rerun()
    
    if st.session_state.db["metrics_defs"]:
        del_m = st.selectbox("削除する項目", st.session_state.db["metrics_defs"])
        if st.button("項目を削除"):
            st.session_state.db["metrics_defs"].remove(del_m)
            df = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df)
            st.rerun()

with st.sidebar.expander("💬 LINE報告設定"):
    l_en = st.checkbox("LINE報告を有効にする", value=st.session_state.db["line_config"]["enabled"])
    l_at = st.text_input("チャネルアクセストークン", value=st.session_state.db["line_config"]["access_token"], type="password")
    l_ui = st.text_input("宛先ユーザーID", value=st.session_state.db["line_config"]["user_id"])
    if st.button("LINE設定を更新"):
        st.session_state.db["line_config"] = {"access_token": l_at, "user_id": l_ui, "enabled": l_en}
        st.sidebar.info("プロフィールの「保存」ボタンを押すとスプレッドシートへ反映されます。")

st.sidebar.divider()
selected_coach = st.sidebar.selectbox("コーチ選択", ["熱血コーチ", "論理派トレーナー"])
uploaded_file = st.sidebar.file_uploader("写真分析 (食事・フォーム等)", type=["jpg", "jpeg", "png"])

# AIモデル設定
model = genai.GenerativeModel("gemini-3-flash-preview", 
                              system_instruction=f"あなたは{selected_coach}です。ユーザーID:{login_id}、目標:{g_val}")

# ==========================================
# 5. メイン画面（タブ構成）
# ==========================================

st.title(f"🔥 AI Trainer Pro: {login_id}")
tabs = st.tabs(["📅 カレンダー", "📋 今日のメニュー", "📈 グラフ", "🏆 称号", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()
today_str = str(today)

# --- Tab 1: カレンダー ---
with tabs[0]:
    st.header(f"🗓️ {today.strftime('%Y年 %m月')} の記録")
    cal_grid = calendar.monthcalendar(today.year, today.month)
    cols_h = st.columns(7)
    for i, d in enumerate(["月", "火", "水", "木", "金", "土", "日"]): cols_h[i].write(f"**{d}**")
    for week in cal_grid:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day != 0:
                d_key = f"{today.year}-{today.month:02d}-{day:02d}"
                rate = st.session_state.db["history"].get(d_key, -1)
                color, txt = "gray", "ー"
                if rate != -1:
                    r = float(rate)
                    if r >= 0.8: color, txt = "#FF4B4B", "🔥"
                    elif r >= 0.6: color, txt = "#007BFF", f"{int(r*100)}%"
                    elif r >= 0.3: color, txt = "#FFD700", f"{int(r*100)}%"
                    else: color, txt = "#FF0000", f"{int(r*100)}%"
                cols[i].markdown(f'<div style="border:1px solid #ddd;padding:5px;text-align:center;min-height:60px;"><span style="font-size:0.75rem;color:gray;">{day}</span><br><span style="font-weight:bold;color:{color};">{txt}</span></div>', unsafe_allow_html=True)

# --- Tab 2: メニュー ＆ 達成率 ＆ 報告 ---
with tabs[1]:
    with st.chat_message("assistant"):
        st.write(f"**【コーチからの伝言】**")
        st.write(st.session_state.db["daily_message"])
    
    if st.button("メニュー更新・生成"):
        res = model.generate_content("タスク4つと熱い伝言を [MESSAGE]...[/MESSAGE] で出力して。")
        st.session_state.db["daily_message"] = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", res.text, re.DOTALL).group(1).strip()
        tasks_found = [l.strip('- *12345.') for l in res.text.split('\n') if l.strip().startswith(('-', '*', '1.', '2.'))]
        st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks_found if t]
        st.rerun()

    col_t, col_m = st.columns([2, 1])
    with col_t:
        for i, t in enumerate(st.session_state.db["tasks"]):
            st.session_state.db["tasks"][i]["done"] = st.checkbox(t["task"], value=t["done"], key=f"t_{i}")

        done_count = sum(1 for t in st.session_state.db["tasks"] if t["done"])
        total_count = len(st.session_state.db["tasks"])
        current_rate = done_count / total_count if total_count > 0 else 0
        st.divider()
        st.metric(label="現在の達成率", value=f"{int(current_rate * 100)}%")
        st.progress(current_rate)
        
        free_report = st.text_area("今日頑張ったこと（自由報告欄）", placeholder="例：3ポイントシュートのフォームが安定してきた！")

    with col_m:
        st.subheader("数値の記録")
        today_metrics = {m: st.number_input(f"{m}", value=0.0, key=f"in_{m}") for m in st.session_state.db["metrics_defs"]}

    if st.button("今日の成果を保存 ＆ LINE報告送信"):
        # 1. カレンダー履歴保存 (Historyシート)
        h_df = pd.DataFrame([{"user_id": login_id, "date": today_str, "rate": current_rate}])
        save_to_gs("History", h_df)
        
        # 2. 数値データ保存 (Metricsシート)
        m_rows = []
        for m, v in today_metrics.items():
            m_rows.append({"user_id": login_id, "date": today_str, "metric_name": m, "value": v})
        if m_rows:
            save_to_gs("Metrics", pd.DataFrame(m_rows), key_cols=['user_id', 'date', 'metric_name'])
        
        # 3. LINE報告送信
        if st.session_state.db["line_config"]["enabled"]:
            with st.spinner("LINE送信中..."):
                prompt = f"達成率{int(current_rate*100)}%。自由報告：『{free_report}』。保護者向けの報告文を作成して。"
                rep_text = model.generate_content(prompt).text
                msg = f"\n【報告: {login_id}】\n達成率: {int(current_rate*100)}%\n頑張り: {free_report}\n\nコーチより:\n{rep_text}"
                requests.post("https://api.line.me/v2/bot/message/push", 
                              headers={"Content-Type": "application/json", "Authorization": f"Bearer {st.session_state.db['line_config']['access_token']}"},
                              json={"to": st.session_state.db['line_config']['user_id'], "messages": [{"type": "text", "text": msg}]})
        
        st.success("スプレッドシートへ保存しました！")
        st.balloons()
        st.rerun()

# --- Tab 3: グラフ ---
with tabs[2]:
    st.header("📈 成長グラフ")
    m_df = st.session_state.db["metrics_data"]
    if not m_df.empty:
        sel = st.selectbox("表示する項目", st.session_state.db["metrics_defs"])
        plot_df = m_df[m_df['metric_name'] == sel].sort_values('date')
        if not plot_df.empty:
            st.line_chart(plot_df.set_index('date')['value'])
        else: st.info("表示するデータがありません")
    else: st.info("まずは数値を記録して保存してください。")

# --- Tab 4: 称号 ---
with tabs[3]:
    st.header("🏆 アチーブメント")
    full_days = sum(1 for v in st.session_state.db["history"].values() if float(v) == 1.0)
    if full_days >= 1: st.success("🔥 闘魂の火種: 最初のパーフェクト達成！")
    if full_days >= 7: st.success("🌟 努力の天才: 7日間の継続達成！")

# --- Tab 5: ロードマップ ---
with tabs[4]:
    st.header("🚀 成功へのロードマップ")
    if st.button("最新ロードマップを生成"):
        res = model.generate_content("目標達成へのmindmapをMermaid形式で。```mermaid ... ```で囲んで。")
        match = re.search(r"```mermaid\s*(.*?)\s*```", res.text, re.DOTALL)
        if match:
            st.session_state.db["roadmap"] = match.group(1)
            # 本来はロードマップもDB保存すべきですが、一旦セッション内で保持
    if st.session_state.db["roadmap"]:
        st.components.v1.html(f'<div class="mermaid">{st.session_state.db["roadmap"]}</div><script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";mermaid.initialize({{startOnLoad:true}});</script>', height=600)

# --- Tab 6: 相談チャット (画像分析) ---
with tabs[5]:
    if "messages" not in st.session_state: st.session_state.messages = []
    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])
    
    if p := st.chat_input("コーチに相談しよう！写真分析もできるぞ"):
        st.session_state.messages.append({"role": "user", "content": p})
        with st.chat_message("user"): st.markdown(p)
        
        inputs = [p, Image.open(uploaded_file)] if uploaded_file else [p]
        with st.spinner("AIが考え中..."):
            res = model.generate_content(inputs)
            st.session_state.messages.append({"role": "assistant", "content": res.text})
            with st.chat_message("assistant"): st.markdown(res.text)