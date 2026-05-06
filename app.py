import streamlit as st
import pandas as pd
import random
from pulp import *

st.set_page_config(page_title="らくらくシフト作成くんPro", layout="wide")

# デザイン設定
st.markdown("""
    <style>
    .main { background-color: #fffaf0; }
    .stButton>button { background-color: #ff9800; color: white; border-radius: 30px; font-weight: bold; height: 3.5em; }
    .score-box { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 10px solid #ff9800; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

st.title("☀️ らくらくシフト作成くん (10回試行＆公休厳守) 🌙")
st.write("<p style='text-align: center;'>「公休日数」を絶対守りつつ、10回試行してベストな下書きを選び出します</p>", unsafe_allow_html=True)

# --- スコア計算ロジック ---
def calculate_score(df, target_off):
    score = 100
    details = []
    
    # 1. 夜勤の公平性
    night_counts = df[df.apply(lambda x: x.str.contains('夜🌙'))].count(axis=1)
    if night_counts.std() > 0.5:
        penalty = int(night_counts.std() * 15)
        score -= penalty
        details.append(f"⚠️ 夜勤回数に偏りがあります (-{penalty}点)")
    else:
        score += 5
        details.append("✅ 夜勤が公平に分配されています (+5点)")

    # 2. 公休数のチェック（手直し後の確認用）
    off_counts = df[df.apply(lambda x: x.str.contains('休🏖️'))].count(axis=1)
    if any(off_counts != target_off):
        details.append("❗ 公休数が設定と異なる人がいます（要修正）")
        score -= 20
        
    return max(0, min(100, score)), details

# --- サイドバー：設定 ---
with st.sidebar:
    st.header("👥 スタッフ設定")
    raw_names = st.text_area("スタッフ名（1行1人）", value="田中\n佐藤\n鈴木\n高橋\n伊藤\n渡辺\n山本\n中村\n小林\n加藤", height=120)
    staff_names = [n.strip() for n in raw_names.split('\n') if n.strip()]
    night_staff = st.multiselect("夜勤ができる人", options=staff_names, default=staff_names[:6])
    
    st.header("⚙️ 条件設定")
    v_days = st.number_input("日数", value=30)
    v_off = st.number_input("絶対守る公休日数", value=10)
    
    with st.expander("💼 シフト人数"):
        v_night = st.number_input("1日の夜勤人数", value=2)
        v_early = st.number_input("1日の早番人数", value=2)
        v_day_min = st.number_input("1日の日勤（目標）", value=4)

# セッション状態
if 'df' not in st.session_state: st.session_state.df = None
if 'score' not in st.session_state: st.session_state.score = 0
if 'details' not in st.session_state: st.session_state.details = []

# --- 計算実行 ---
if st.button("🚀 10回シミュレーションして最高の下書きを作成"):
    best_df = None
    max_score = -1
    
    bar = st.progress(0)
    status = st.empty()

    for k in range(10):
        status.text(f"シミュレーション 第 {k+1}/10 回目...")
        
        prob = LpProblem("Shift_Optimization", LpMinimize)
        S = range(len(staff_names)); D = range(v_days)
        x = LpVariable.dicts("x", (S, D, range(5)), 0, 1, LpBinary)
        
        # 柔軟さのためのペナルティ変数
        pen_con = LpVariable.dicts("pen_con", (S, D), 0, 1)
        
        # 目的関数：ランダム要素 ＋ ルール違反（連勤）の最小化
        prob += lpSum([random.random() * x[i][d][j] for i in S for d in D for j in range(5)]) + lpSum(pen_con) * 100

        for i, name in enumerate(staff_names):
            prob += lpSum([x[i][d][4] for d in D]) == v_off # 【絶対】公休数
            if name not in night_staff:
                for d in D: prob += x[i][d][2] == 0; prob += x[i][d][3] == 0 # 【絶対】夜勤不可
            
            for d in D:
                prob += lpSum([x[i][d][j] for j in range(5)]) == 1 # 【絶対】1日1個
                if d == 0: prob += x[i][d][3] == 0 # 【絶対】1日目明けなし
                if d < v_days - 1: prob += x[i][d][2] <= x[i][d+1][3] # 【絶対】夜→明
                if d < v_days - 2: prob += x[i][d+1][3] <= x[i][d+2][4] # 【絶対】明→休
            
            for d in range(v_days - 5): # 【柔軟】5連勤まで
                prob += lpSum([x[i][d+k][j] for k in range(6) for j in range(4)]) <= 5 + pen_con[i][d]

        for d in D:
            prob += lpSum([x[i][d][0] for i in S]) == v_early # 【絶対】早番人数
            prob += lpSum([x[i][d][2] for i in S]) == v_night # 【絶対】夜勤人数
            if d > 0: prob += lpSum([x[i][d][3] for i in S]) == v_night # 【絶対】明け人数
            prob += lpSum([x[i][d][1] for i in S]) >= v_day_min # 日勤人数（努力目標）

        # 1回あたり15秒で打ち切り
        res_status = prob.solve(PULP_CBC_CMD(msg=0, timeLimit=15))
        
        if res_status != LpStatusInfeasible:
            labels = {0:"早☀️", 1:"日☕", 2:"夜🌙", 3:"明✨", 4:"休🏖️"}
            res = [[labels[j] for d in D for j in range(5) if value(x[i][d][j]) == 1] for i in S]
            tmp_df = pd.DataFrame(res, columns=[f"{d+1}" for d in D], index=staff_names)
            sc, det = calculate_score(tmp_df, v_off)
            if sc > max_score:
                max_score = sc
                best_df = tmp_df
                st.session_state.details = det
        bar.progress((k + 1) * 10)

    if best_df is not None:
        st.session_state.df = best_df
        st.session_state.score = max_score
        st.success(f"10回の試行から最高スコア {max_score} 点のシフトを採用しました！")
    else:
        st.error("条件が厳しすぎて作成できませんでした。")

# --- 結果表示と手直し ---
if st.session_state.df is not None:
    st.markdown(f"""
        <div class="score-box">
            <h3>📊 シフトの健康度: {st.session_state.score} 点</h3>
            {'<br>'.join(st.session_state.details)}
        </div>
    """, unsafe_allow_html=True)
    
    st.subheader("📝 仕上げの手直し（直接書き換えてください）")
    edited_df = st.data_editor(st.session_state.df, use_container_width=True, height=500)
    
    # 手直し後の公休チェック
    off_counts = edited_df[edited_df == "休🏖️"].count(axis=1)
    error_staff = off_counts[off_counts != v_off]
    if not error_staff.empty:
        st.warning(f"⚠️ 公休数が {v_off}日 ではない人がいます：{list(error_staff.index)}")
    
    if st.button("🔄 手直し後のスコアを再計算"):
        sc, det = calculate_score(edited_df, v_off)
        st.session_state.score = sc
        st.session_state.details = det
        st.session_state.df = edited_df
        st.rerun()

    csv = edited_df.to_csv().encode('utf_8_sig')
    st.download_button("📥 完成版をCSV保存", data=csv, file_name='shift.csv')