import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="產線數據查找工具", layout="wide")
st.title("🔍 產線 Retest & Fail 數據庫系統")

# --- 設定 Google Sheets 連線 ---
# 這是讀取 Streamlit 雲端秘密金鑰的設定
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

@st.cache_resource
def init_connection():
    try:
        # 從 Streamlit Secrets 讀取您設定的 JSON 金鑰
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        return None

client = init_connection()

# 嘗試開啟您的試算表
SHEET_NAME = "Retest_Fail_Database"
try:
    if client:
        sheet = client.open(SHEET_NAME).sheet1
        db_connected = True
    else:
        db_connected = False
except Exception as e:
    db_connected = False
    st.error(f"無法連線至 Google 試算表，請確認已將機器人 Email 加入共用名單，且名稱為 {SHEET_NAME}。")

# --- 讀取雲端資料庫 ---
def load_database():
    if db_connected:
        records = sheet.get_all_records()
        if records:
            return pd.DataFrame(records)
    # 如果資料庫是空的或沒連線，回傳空表
    return pd.DataFrame(columns=["Station", "Data Type", "Item 名稱", "Rate (比例)", "Root Cause", "Corrective Action"])

db_df = load_database()

# --- 1. 產生模板供下載 ---
@st.cache_data
def get_template():
    template_df = pd.DataFrame(columns=[
        "Station (A)", "B", "Retest item / Fail item (C)", "D", "E", 
        "RR / FR (F)", "G", "Root cause (H)", "Corrective action (I)"
    ])
    return template_df.to_csv(index=False).encode('utf-8-sig')

st.sidebar.header("📥 第一步：模板下載")
st.sidebar.download_button(label="下載標準模板 (CSV)", data=get_template(), file_name="Data_Template.csv", mime="text/csv")

# --- 2. 檔案上傳與更新資料庫 ---
st.sidebar.header("📤 第二步：上傳最新數據")
uploaded_file = st.sidebar.file_uploader("上傳報表 (系統會自動更新與覆蓋舊資料)", type=["csv", "xlsx"])

if uploaded_file and db_connected:
    with st.spinner('正在分析並更新至雲端資料庫，請稍候...'):
        try:
            all_dfs = []
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
                all_dfs.append(("", df))
            else:
                sheet_dict = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
                for sheet_name, df in sheet_dict.items():
                    if "摘要" not in sheet_name and len(df.columns) >= 9:
                        all_dfs.append((sheet_name, df))

            processed_data = []
            for sheet_name, df in all_dfs:
                if len(df.columns) >= 9:
                    temp_df = pd.DataFrame()
                    temp_df["Station"] = df.iloc[:, 0]
                    temp_df["Item 名稱"] = df.iloc[:, 2]
                    temp_df["Rate (比例)"] = df.iloc[:, 5]
                    temp_df["Root Cause"] = df.iloc[:, 7]
                    temp_df["Corrective Action"] = df.iloc[:, 8]
                    
                    col_c_name = str(df.columns[2]).lower()
                    col_f_name = str(df.columns[5]).lower()
                    first_val_c = str(df.iloc[0, 2]).lower() if len(df) > 0 else ""
                    first_val_f = str(df.iloc[0, 5]).lower() if len(df) > 0 else ""
                    
                    if "fail" in col_c_name or "fr" in col_f_name or "fail" in first_val_c or "fr" in first_val_f:
                        data_type = "🛑 Fail (FR)"
                    elif "retest" in col_c_name or "rr" in col_f_name or "retest" in first_val_c or "rr" in first_val_f:
                        data_type = "⚠️ Retest (RR)"
                    else:
                        data_type = "⚠️ Retest (RR)"
                             
                    temp_df["Data Type"] = data_type
                    processed_data.append(temp_df)

            if processed_data:
                new_df = pd.concat(processed_data, ignore_index=True)
                new_df["Station"] = new_df["Station"].ffill()
                new_df = new_df.dropna(subset=["Item 名稱"])
                new_df = new_df[~new_df["Item 名稱"].astype(str).str.contains("item", case=False, na=False)]

                def format_rate(val):
                    if pd.isna(val): return val
                    if isinstance(val, str) and '%' in val: return val
                    try: return f"{float(val) * 100:.4f}%"
                    except: return str(val)

                new_df["Rate (比例)"] = new_df["Rate (比例)"].apply(format_rate)
                new_df = new_df[["Station", "Data Type", "Item 名稱", "Rate (比例)", "Root Cause", "Corrective Action"]]

                # --- 覆蓋與更新邏輯 ---
                # 將「Station」、「Data Type」與「Item 名稱」視為唯一鍵值，進行比對與覆蓋
                if not db_df.empty:
                    # 設定索引以進行更新
                    db_df.set_index(["Station", "Data Type", "Item 名稱"], inplace=True)
                    new_df.set_index(["Station", "Data Type", "Item 名稱"], inplace=True)
                    
                    # 更新舊有資料，並加入新資料
                    db_df.update(new_df)
                    db_df = db_df.combine_first(new_df)
                    
                    # 恢復索引
                    db_df.reset_index(inplace=True)
                else:
                    db_df = new_df

                # 確保 Root Cause 欄位名稱正確
                if 'Root cause' in db_df.columns:
                    db_df.rename(columns={'Root cause': 'Root Cause'}, inplace=True)

                # 把整理好的資料寫回 Google Sheets
                # 為了避免格式錯誤，將所有資料轉為字串並處理 NaN
                upload_df = db_df.copy()
                upload_df = upload_df.fillna("N/A")
                upload_df = upload_df.astype(str)
                
                sheet.clear() # 清空原本的試算表
                sheet.update([upload_df.columns.values.tolist()] + upload_df.values.tolist()) # 寫入新資料
                
                st.sidebar.success("✅ 雲端資料庫更新成功！")
                
        except Exception as e:
            st.sidebar.error(f"資料處理或上傳失敗：{e}")

# --- 3. 搜尋與展示 ---
st.markdown("### 🔎 搜尋歷史資料庫")

if not db_connected:
    st.warning("請先設定 Streamlit Secrets 金鑰以連結資料庫。")
elif db_df.empty:
    st.info("雲端資料庫目前是空的，請從左側上傳您的第一份報表！")
else:
    search_query = st.text_input("請輸入想尋找的 Retest item 或 Fail item (例如: UnbindStateSync_3)")
    
    if search_query:
        mask = db_df["Item 名稱"].astype(str).str.contains(search_query, case=False, na=False)
        result_df = db_df[mask]
        
        if not result_df.empty:
            st.success(f"從雲端找到 {len(result_df)} 筆相符的歷史資料：")
            st.dataframe(result_df, use_container_width=True)
        else:
            st.warning("資料庫中查無符合的資料。")
    
    with st.expander("點擊展開預覽：雲端資料庫中的所有紀錄"):
        st.dataframe(db_df)