import streamlit as st
import pandas as pd
from pulp import *

# 1. ページの設定
st.set_page_config(page_title="らくらくシフト作成くん", layout="wide")

# 2. ポップなデザインの適用
st.markdown("""
    <style>
    .main { background-color: #fffaf0; }
    .stButton>button { 
        background-color: #ff9800; color: white; border-radius: 30px; 
        font-size: 22px; height: 3.5em; width: 100%; border: none;
        font-weight: bold; box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    }
    .stButton>button:hover { background-color: #f57c00; transform: scale(1.02); }
    h1 { color: #e65100; font-family: 'Hiragino Maru Gothic Pro', sans-serif; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

st.title("☀️ らくらくシフト作成くん 🌙")
st.write("<p style='text-align: center; color: #666;'>100人規模対応 / 5連勤禁止 / 週休2日ルール適用済み</p>", unsafe_allow_html=True)

# --- サイドバー：設定 ---
with st.sidebar:
    st.header("⚙️ 基本ルール")
    v_staff = st.number_input("従業員数 (人)", value=50, min_value=1)
    v_days = st.number_input("作成日数 (日)", value=30, min_value=1)
    
    st.subheader("💼 各シフトの必要人数")
    v_early = st.number_input("早番☀️", value=2)
    v_day = st.number_input("日勤☕", value=16)
    v_night = st.number_input("夜勤🌙", value=4)
    
    st.subheader("👤 個人の制限")
    v_max_night = st.number_input("夜勤の上限", value=4)
    v_off = st.number_input("休みの回数", value=10)

    st.header("📅 お休み希望")
    st.caption("例: 1,5 （スタッフ1が5日に休み）")
    holiday_input = st.text_area("1行に1件ずつ入力")

# --- メインエリア ---
if st.button("🚀 この条件でシフトを自動作成する！"):
    prob = LpProblem("ShiftSolver", LpMinimize)
    S = range(v_staff)
    D = range(v_days)
    # 0:早, 1:日, 2:夜, 3:明, 4:休
    x = LpVariable.dicts("x", (S, D, range(5)), 0, 1, LpBinary)

    # 希望休
    if holiday_input:
        for line in holiday_input.split('\n'):
            if ',' in line:
                try:
                    s_val, d_val = map(int, line.split(','))
                    if s_val <= v_staff and d_val <= v_days:
                        prob += x[s_val-1][d_val-1][4] == 1
                except: pass

    # ルール適用
    for i in S:
        for d in D:
            prob += lpSum([x[i][d][j] for j in range(5)]) == 1
            if d < v_days - 1:
                prob += x[i][d][2] <= x[i][d+1][3] # 夜→明
            if d < v_days - 2:
                prob += x[i][d+1][3] <= x[i][d+2][4] # 明→休
        
        prob += lpSum([x[i][d][4] for d in D]) == v_off # 休み固定
        prob += lpSum([x[i][d][2] for d in D]) <= v_max_night # 夜勤上限

        # 5連勤禁止（6日間で1日は休み）
        for d in range(v_days - 5):
            prob += lpSum([x[i][d+k][j] for k in range(6) for j in range(4)]) <= 5
        
        # 週休2日（7日間で2日は休み）
        for d in range(v_days - 6):
            prob += lpSum([x[i][d+k][4] for k in range(7)]) >= 2

    for d in D:
        prob += lpSum([x[i][d][0] for i in S]) == v_early # 早
        prob += lpSum([x[i][d][2] for i in S]) == v_night # 夜
        prob += lpSum([x[i][d][1] for i in S]) >= v_day   # 日
        if d > 0:
            prob += lpSum([x[i][d][3] for i in S]) == v_night # 明

    with st.spinner('計算中...'):
        status = prob.solve(PULP_CBC_CMD(msg=0, timeLimit=40))

    if status != LpStatusInfeasible:
        st.success("🎉 シフトが完成しました！")
        st.balloons()

        labels = {0:"早☀️", 1:"日☕", 2:"夜🌙", 3:"明✨", 4:"休🏖️"}
        res = []
        for i in S:
            row = [labels[j] for d in D for j in range(5) if value(x[i][d][j]) == 1]
            res.append(row)
        
        df = pd.DataFrame(res, columns=[f"{d+1}" for d in D], index=[f"スタッフ{i+1}" for i in S])
        
        # 色分け
        def style_shift(val):
            color_map = {"早☀️":"#fff3e0", "日☕":"#e1f5fe", "夜🌙":"#f3e5f5", "明✨":"#f3e5f5", "休🏖️":"#ffebee"}
            return f'background-color: {color_map.get(val, "#ffffff")}'

        st.dataframe(df.style.map(style_shift), height=600)
        
        csv = df.to_csv().encode('utf_8_sig')
        st.download_button("📥 完成したシフトを保存(CSV)", data=csv, file_name='shift.csv', mime='text/csv')
    else:
        st.error("😢 条件が厳しくてパズルが解けませんでした。")