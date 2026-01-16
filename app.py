import streamlit as st
from streamlit_gsheets import GSheetsConnection

# 1. 接続の確立（明示的にクラスを指定）
# secrets.toml 内に JSONキーの全項目が [connections.gsheets] の下にある前提です
conn = st.connection("gsheets", type=GSheetsConnection)

# 2. データの読み込み関数
def load_data():
    # Profilesシートを読み込む例
    profiles_df = conn.read(worksheet="Profiles", ttl="10m")
    # Metricsシートを読み込む例
    metrics_df = conn.read(worksheet="Metrics", ttl="0") # リアルタイム更新のためTTLを0に
    return profiles_df, metrics_df

# 実行
try:
    profiles_df, metrics_df = load_data()
    st.success("スプレッドシートへの接続に成功しました！")
except Exception as e:
    st.error(f"接続エラーが発生しました。設定を確認してください。")
    # 詳細なエラーを確認したい場合は st.exception(e) を使用
