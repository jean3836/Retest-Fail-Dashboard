import streamlit as st
import pandas as pd

st.set_page_config(page_title="產線數據查找工具", layout="wide")
st.title("🔍 產線 Retest & Fail 數據查找工具")

# --- 1. 產生模板供下載 ---
@st.cache_data
def get_template():
    # 建立與您要求完全一致的模板欄位
    template_df = pd.DataFrame(columns=[
        "Station (A)", "B", "Retest item / Fail item (C)", "D", "E", 
        "RR / FR (F)", "G", "Root cause (H)", "Corrective action (I)"
    ])
    return template_df.to_csv(index=False).encode('utf-8-sig')

st.sidebar.header("📥 第一步：模板下載")
st.sidebar.download_button(
    label="下載標準模板 (CSV)",
    data=get_template(),
    file_name="Data_Template.csv",
    mime="text/csv"
)

# --- 2. 檔案上傳 ---
st.sidebar.header("📤 第二步：上傳最新數據")
uploaded_file = st.sidebar.file_uploader("請上傳填寫好的 CSV 或 Excel 檔案", type=["csv", "xlsx"])

if uploaded_file:
    try:
        all_dfs = []
        
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
            all_dfs.append(("", df)) # CSV 沒分頁名稱，給個空字串
        else:
            # 讀取 Excel 中所有的 Sheet
            sheet_dict = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
            
            # 排除「導出摘要」等不符合格式的 sheet
            for sheet_name, df in sheet_dict.items():
                if "摘要" not in sheet_name and len(df.columns) >= 9:
                    all_dfs.append((sheet_name, df))

        processed_data = []
        
        # 嚴格依照您指示的 A(0), C(2), F(5), H(7), I(8) 欄位抓取
        for sheet_name, df in all_dfs:
            if len(df.columns) >= 9:
                temp_df = pd.DataFrame()
                temp_df["Station"] = df.iloc[:, 0]
                temp_df["Item"] = df.iloc[:, 2]
                temp_df["Rate_Value"] = df.iloc[:, 5]
                temp_df["Root Cause"] = df.iloc[:, 7]
                temp_df["Corrective Action"] = df.iloc[:, 8]
                
                # --- 核心邏輯：自動判斷是 Retest 還是 Fail ---
                # 抓取 C 欄和 F 欄的「標題列」轉成小寫來判斷
                col_c_name = str(df.columns[2]).lower()
                col_f_name = str(df.columns[5]).lower()
                
                # 抓取第一筆資料來當備用判斷
                first_val_c = str(df.iloc[0, 2]).lower() if len(df) > 0 else ""
                first_val_f = str(df.iloc[0, 5]).lower() if len(df) > 0 else ""
                
                if "fail" in col_c_name or "fr" in col_f_name or "fail" in first_val_c or "fr" in first_val_f:
                    data_type = "🛑 Fail (FR)"
                elif "retest" in col_c_name or "rr" in col_f_name or "retest" in first_val_c or "rr" in first_val_f:
                    data_type = "⚠️ Retest (RR)"
                else:
                    data_type = "⚠️ Retest (RR)" # 若無法辨識，預設為 Retest
                         
                temp_df["Data Type"] = data_type
                processed_data.append(temp_df)

        if processed_data:
            final_df = pd.concat(processed_data, ignore_index=True)
            
            # 填補 Station 的空白
            final_df["Station"] = final_df["Station"].ffill()
            # 去除 Item 是空值的行
            final_df = final_df.dropna(subset=["Item"])
            # 去除把「標題」當成資料讀進來的行
            final_df = final_df[~final_df["Item"].astype(str).str.contains("item", case=False, na=False)]

            # 格式化 Rate 為百分比
            def format_rate(val):
                if pd.isna(val):
                    return val
                if isinstance(val, str) and '%' in val:
                    return val
                try:
                    num = float(val)
                    return f"{num * 100:.4f}%"
                except:
                    return str(val)

            final_df["Rate_Value"] = final_df["Rate_Value"].apply(format_rate)
            
            # 重新排列欄位順序，把「Data Type」插到前面，讓使用者一眼看出這是 RR 還是 FR
            final_df = final_df[["Station", "Data Type", "Item", "Rate_Value", "Root Cause", "Corrective Action"]]
            # 幫欄位改個好懂的名字
            final_df.rename(columns={"Item": "Item 名稱", "Rate_Value": "Rate (比例)"}, inplace=True)

            # --- 3. 關鍵字搜尋 ---
            st.markdown("### 🔎 搜尋 Item 資訊")
            search_query = st.text_input("請輸入想尋找的 Retest item 或 Fail item (例如: UnbindStateSync_3)")
            
            if search_query:
                mask = final_df["Item 名稱"].astype(str).str.contains(search_query, case=False, na=False)
                result_df = final_df[mask]
                
                if not result_df.empty:
                    st.success(f"找到 {len(result_df)} 筆相符的資料：")
                    st.dataframe(result_df, use_container_width=True)
                else:
                    st.warning("查無符合的資料，請嘗試其他關鍵字。")
            else:
                st.info("請在上方輸入框鍵入 Item 名稱以開始搜尋。")
                
            with st.expander("點擊展開預覽：已讀取的所有分頁數據總覽"):
                st.dataframe(final_df)
                
        else:
            st.error("找不到符合 A, C, F, H, I 欄位格式的分頁。")
            
    except Exception as e:
        st.error(f"檔案解析失敗：{e}")
else:
    st.info("👈 請先從左側面板上傳數據以啟用搜尋功能！")