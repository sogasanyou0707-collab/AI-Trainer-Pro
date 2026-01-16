import streamlit as st
import google.generativeai as genai
import re
from PIL import Image
import datetime
import calendar
import pandas as pd
import requests
from streamlit_gsheets import GSheetsConnection

# --- 1. ページ基本設定 & Secrets読み込み ---
st.set_page_config(page_title="AI Trainer Pro: Ultimate", layout="wide")

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    SPREADSHEET_URL = st.secrets.connections.gsheets.spreadsheet
    genai.configure(api_key=API_KEY)
    # Gemini 3 指定
    model = genai.GenerativeModel("gemini-3-flash-preview")
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"初期設定エラー: {e}")
    st.stop()

# --- 2. データ読み書き関数 ---
def load_full_data_gs(user_id):
    default_data = {
        "profile": {"height": 170.0, "weight": 65.0, "goal": "健康維持"},
        "history": {}, "metrics_data": pd.DataFrame(), "metrics_defs": ["体重"],
        "line": {"token": "", "uid": "", "en": False},
        "daily_message": "準備はいいか！", "tasks": [], "roadmap": ""
    }
    try:
        p_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Profiles", ttl=0)
        h_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="History", ttl=0)
        m_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Metrics", ttl=0)
        s_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="Settings", ttl=0)

        u_id = str(user_id)
        prof = p_df[p_df['user_id'].astype(str) == u_id].to_dict('records')
        if prof:
            p = prof[0]
            default_data["profile"] = {"height": p.get('height', 170), "weight": p.get('weight', 65), "goal": p.get('goal', "未設定")}
            default_data["line"] = {"token": p.get('line_token', ""), "uid": p.get('line_user_id', ""), "en": p.get('line_enabled', False)}
            default_data["daily_message"] = p.get('daily_message', "準備はいいか！")

        if not h_df.empty:
            default_data["history"] = h_df[h_df['user_id'].astype(str) == u_id].set_index('date')['rate'].to_dict()
        if not m_df.empty:
            default_data["metrics_data"] = m_df[m_df['user_id'].astype(str) == u_id]
        if not s_df.empty:
            raw_defs = s_df[s_df['user_id'].astype(str) == u_id]['metric_defs'].dropna().tolist()
            default_data["metrics_defs"] = sorted(list(set(raw_defs)))
        
        if not default_data["metrics_defs"]: default_data["metrics_defs"] = ["体重"]
        return default_data
    except:
        return default_data

def save_to_gs(worksheet_name, new_df, key_cols=['user_id', 'date']):
    try:
        existing_df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, ttl=0)
        combined = pd.concat([existing_df, new_df], ignore_index=True).drop_duplicates(subset=key_cols, keep='last')
        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=worksheet_name, data=combined)
        return True
    except Exception as e:
        st.error(f"保存失敗: {e}")
        return False

# --- 3. セッション管理 & ログイン ---
st.sidebar.title("🔑 ログイン")
login_id = st.sidebar.text_input("ユーザーIDを入力", value="User1").strip()

if "current_user" not in st.session_state or st.session_state.current_user != login_id:
    st.session_state.db = load_full_data_gs(login_id)
    st.session_state.current_user = login_id

# --- 4. サイドバー機能 (プロフィール・項目管理・LINE・画像) ---
with st.sidebar.expander("👤 プロフィール設定"):
    p_data = st.session_state.db["profile"]
    h_val = st.number_input("身長 (cm)", value=float(p_data["height"]))
    w_val = st.number_input("体重 (kg)", value=float(p_data["weight"]))
    g_val = st.text_area("目標", value=p_data["goal"])
    if st.button("プロフィールの保存"):
        df_p = pd.DataFrame([{"user_id": login_id, "height": h_val, "weight": w_val, "goal": g_val, 
                              "line_token": st.session_state.db["line"]["token"],
                              "line_user_id": st.session_state.db["line"]["uid"],
                              "line_enabled": st.session_state.db["line"]["en"],
                              "daily_message": st.session_state.db["daily_message"]}])
        save_to_gs("Profiles", df_p, key_cols=['user_id'])
        st.session_state.db["profile"] = {"height": h_val, "weight": w_val, "goal": g_val}
        st.success("保存しました！")

with st.sidebar.expander("📊 記録項目の追加・削除"):
    new_m = st.text_input("新規項目名").strip()
    if st.button("追加") and new_m:
        if new_m not in st.session_state.db["metrics_defs"]:
            st.session_state.db["metrics_defs"].append(new_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df_s)
            st.rerun()
    
    if len(st.session_state.db["metrics_defs"]) > 0:
        st.divider()
        del_m = st.selectbox("削除する項目", st.session_state.db["metrics_defs"])
        if st.button("選択項目を削除"):
            st.session_state.db["metrics_defs"].remove(del_m)
            df_s = pd.DataFrame({"user_id": [login_id]*len(st.session_state.db["metrics_defs"]), "metric_defs": st.session_state.db["metrics_defs"]})
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="Settings", data=df_s)
            st.rerun()

with st.sidebar.expander("💬 LINE報告設定"):
    l_en = st.checkbox("LINE報告を有効にする", value=st.session_state.db["line"]["en"])
    l_at = st.text_input("アクセストークン", value=st.session_state.db["line"]["token"], type="password")
    l_ui = st.text_input("宛先ユーザーID", value=st.session_state.db["line"]["uid"])
    if st.button("LINE設定を保存"):
        st.session_state.db["line"] = {"token": l_at, "uid": l_ui, "en": l_en}
        st.info("プロフィールの「保存」ボタンで確定してください")

st.sidebar.divider()
st.sidebar.subheader("📸 写真分析")
uploaded_file = st.sidebar.file_uploader("写真をアップロード (食事やフォーム)", type=["jpg", "jpeg", "png"])

# --- 5. メイン画面 ---
st.title(f"🔥 AI Trainer Pro: {login_id}")
tabs = st.tabs(["📅 カレンダー", "📋 今日のメニュー", "📈 グラフ", "🚀 ロードマップ", "💬 相談"])
today = datetime.date.today()

# --- Tab 1: カレンダー ---
with tabs[0]:
    st.header(f"🗓️ {today.strftime('%Y年 %m月')}")
    cal = calendar.monthcalendar(today.year, today.month)
    cols_h = st.columns(7)
    for i, d in enumerate(["月", "火", "水", "木", "金", "土", "日"]): cols_h[i].markdown(f"<div style='text-align:center;'><b>{d}</b></div>", unsafe_allow_html=True)
    for week in cal:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day != 0:
                d_str = f"{today.year}-{today.month:02d}-{day:02d}"
                rate = st.session_state.db["history"].get(d_str, -1)
                color = "#FF4B4B" if float(rate) >= 0.8 else "gray" if rate == -1 else "#007BFF"
                cols[i].markdown(f'<div style="border:1px solid #ddd;border-radius:5px;padding:10px;text-align:center;background-color:{color};color:white;min-height:50px;">{day}</div>', unsafe_allow_html=True)

# --- Tab 2: 今日のメニュー (達成率復活版) ---
with tabs[1]:
    st.info(f"**コーチからの伝言:** {st.session_state.db.get('daily_message', '準備はいいか！')}")
    
    if st.button("AIメニューを生成・更新"):
        with st.spinner("AIが内容を構成中..."):
            try:
                # 安全性の設定（ブロックを最小限にする）
                safety_settings = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
                
                # 生成リクエスト（モデル名を安定版の 1.5-flash に変えてテストすることをお勧めします）
                # model_to_use = "gemini-3-flash-preview" # 現在の設定
                model_to_use = "gemini-1.5-flash"        # ← もしエラーが続くならこちらを試してください
                
                temp_model = genai.GenerativeModel(model_to_use)
                res = temp_model.generate_content(
                    f"目標:{st.session_state.db['profile']['goal']} に基づき、タスク4つと励ましを [MESSAGE]...[/MESSAGE] で出力してください。",
                    safety_settings=safety_settings
                )

                # 診断: AIの生の回答を確認
                if not res.candidates:
                    st.error("AIから回答が返ってきませんでした（モデル名が無効か、サーバーのエラーです）")
                elif res.candidates[0].finish_reason != 1: # 1以外は異常終了
                    st.warning(f"AIの回答が制限されました（理由コード: {res.candidates[0].finish_reason}）")
                
                # 正常な場合のみ処理
                full_text = res.text
                msg_match = re.search(r"\[MESSAGE\](.*?)\[/MESSAGE\]", full_text, re.DOTALL)
                
                if msg_match:
                    st.session_state.db["daily_message"] = msg_match.group(1).strip()
                else:
                    st.session_state.db["daily_message"] = full_text

                tasks_found = [l.strip("- *1234. ") for l in full_text.split("\n") if l.strip().startswith(("-", "*", "1.", "2."))]
                if tasks_found:
                    st.session_state.db["tasks"] = [{"task": t, "done": False} for t in tasks_found[:4]]
                
                st.rerun()

            except Exception as e:
                st.error(f"【診断エラー】: {e}")
                st.info("もし 'Model not found' と出る場合は、モデル名を gemini-1.5-flash に変更してください。")
            # タスクの内容をチェックボックスの横に表示
            for i, t_item in enumerate(st.session_state.db["tasks"]):
                st.session_state.db["tasks"][i]["done"] = st.checkbox(label=t_item["task"], value=t_item["done"], key=f"tk_{i}_{login_id}")
            
            # 達成率の計算
            done_n = sum(1 for t in st.session_state.db["tasks"] if t["done"])
            total_n = len(st.session_state.db["tasks"])
            current_rate = done_n / total_n if total_n > 0 else 0
            
            st.divider()
            st.metric("本日の達成率", f"{int(current_rate * 100)}%")
            st.progress(current_rate)
            
            free_report = st.text_area("今日頑張ったこと（自由報告欄）", placeholder="例：今日はハンドリング練習を30分頑張りました！")

    with col_r:
        st.subheader("📈 数値記録")
        today_metrics = {m: st.number_input(f"{m}", value=0.0, key=f"inp_{m}_{login_id}") for m in st.session_state.db["metrics_defs"]}

    if st.button("🚀 今日の成果を保存 & LINE報告送信"):
        save_to_gs("History", pd.DataFrame([{"user_id": login_id, "date": str(today), "rate": current_rate, "note": free_report}]))
        m_rows = [{"user_id": login_id, "date": str(today), "metric_name": k, "value": v} for k, v in today_metrics.items()]
        save_to_gs("Metrics", pd.DataFrame(m_rows), key_cols=['user_id', 'date', 'metric_name'])
        
        # LINE報告
        config = st.session_state.db["line"]
        if config["en"] and config["token"]:
            prompt = f"達成率{int(current_rate*100)}%、今日の感想：『{free_report}』。保護者向けのフィードバックを作成して。"
            feedback = model.generate_content(prompt).text
            msg = f"\n【{login_id} 報告】\n達成率: {int(current_rate*100)}%\n頑張り: {free_report}\n\nコーチより:\n{feedback}"
            requests.post("https://api.line.me/v2/bot/message/push", 
                          headers={"Authorization": f"Bearer {config['token']}", "Content-Type": "application/json"},
                          json={"to": config["uid"], "messages": [{"type": "text", "text": msg}]})
            st.toast("LINE送信完了！")
        
        st.session_state.db["history"][str(today)] = current_rate
        st.success("スプレッドシートに保存しました！")
        st.balloons()

# --- Tab 3: グラフ ---
with tabs[2]:
    st.header("📈 成長グラフ")
    m_df = st.session_state.db["metrics_data"]
    if not m_df.empty:
        sel_m = st.selectbox("表示する項目", st.session_state.db["metrics_defs"])
        plot_df = m_df[m_df['metric_name'] == sel_m].sort_values('date')
        st.line_chart(plot_df.set_index('date')['value'])
    else: st.info("データがありません。保存ボタンで記録を始めてください。")

# --- Tab 4: ロードマップ (Mermaid) ---
with tabs[3]:
    if st.button("ロードマップ生成"):
        res = model.generate_content("目標達成への道筋をMermaid形式のmindmapで。```mermaid...```で囲んで。")
        match = re.search(r"```mermaid\s*(.*?)\s*```", res.text, re.DOTALL)
        if match: st.session_state.db["roadmap"] = match.group(1)
        st.rerun()
    if st.session_state.db.get("roadmap"):
        st.components.v1.html(f'<div class="mermaid">{st.session_state.db["roadmap"]}</div><script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";mermaid.initialize({{startOnLoad:true}});</script>', height=500)

# --- Tab 5: 相談 ---
with tabs[4]:
    st.subheader("💬 AIコーチに相談")
    if "messages" not in st.session_state: st.session_state.messages = []
    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])
    
    if prompt := st.chat_input("相談を入力"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        inputs = [prompt, Image.open(uploaded_file)] if uploaded_file else [prompt]
        response = model.generate_content(inputs).text
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"): st.markdown(response)

