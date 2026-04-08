import streamlit as st
import pandas as pd
import gspread
import json
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="產線數據查找工具", layout="wide")
st.title("🔍 產線 Retest & Fail 數據庫系統")

# --- 設定 Google Sheets 連線 ---
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

@st.cache_resource
def init_connection():
    try:
        secret_data = st.secrets["gcp_service_account"]
        if isinstance(secret_data, str):
            secret_data = json.loads(secret_data)
            
        creds = Credentials.from_service_account_info(secret_data, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.sidebar.error(f"連線設定失敗，請檢查金鑰格式：{e}")
        return None

client = init_connection()

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
        try:
            records = sheet.get_all_records()
            if records:
                return pd.DataFrame(records)
        except:
            pass
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
    if st.sidebar.button("🚀 確認上傳並更新雲端"):
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
                        # ==========================================
                        # 🌟 核心修正區：嚴格只判斷表頭 (Column 2)
                        # ==========================================
                        col_c_name = str(df.columns[2]).strip().lower()
                        
                        # 嚴格依照表頭判定，完全不看 Item 內容
                        if "retest" in col_c_name:
                            data_type = "⚠️ Retest (RR)"
                        elif "fail" in col_c_name or "failure" in col_c_name:
                            data_type = "🛑 Fail (FR)"
                        else:
                            # 為了保險起見，如果 C 欄沒抓到，掃描整列的表頭
                            all_cols_str = " ".join([str(c).lower() for c in df.columns])
                            if "retest" in all_cols_str:
                                data_type = "⚠️ Retest (RR)"
                            elif "fail" in all_cols_str or "failure" in all_cols_str:
                                data_type = "🛑 Fail (FR)"
                            else:
                                # 如果表頭完全沒有這兩個關鍵字，代表這不是標準報表，跳過處理
                                continue
                        # ==========================================

                        temp_df = pd.DataFrame()
                        temp_df["Station"] = df.iloc[:, 0]
                        temp_df["Item 名稱"] = df.iloc[:, 2]
                        temp_df["Rate (比例)"] = df.iloc[:, 5]
                        temp_df["Root Cause"] = df.iloc[:, 7]
                        temp_df["Corrective Action"] = df.iloc[:, 8]
                        temp_df["Data Type"] = data_type
                        
                        processed_data.append(temp_df)

                if processed_data:
                    new_df = pd.concat(processed_data, ignore_index=True)
                    new_df["Station"] = new_df["Station"].ffill()
                    new_df = new_df.dropna(subset=["Item 名稱"])
                    
                    new_df["Station"] = new_df["Station"].astype(str).str.strip()
                    new_df["Item 名稱"] = new_df["Item 名稱"].astype(str).str.strip()
                    
                    # 預處理 Root Cause，將空值填上 N/A，方便後續當作判斷依據
                    new_df["Root Cause"] = new_df["Root Cause"].fillna("N/A").astype(str).str.strip()
                    
                    # 排除表頭不小心被當成數據讀進來的狀況
                    new_df = new_df[~new_df["Item 名稱"].str.contains("item", case=False, na=False)]

                    def format_rate(val):
                        if pd.isna(val) or str(val).strip() == "": return ""
                        if isinstance(val, str) and '%' in val: return val
                        try: return f"{float(val) * 100:.4f}%"
                        except: return str(val)

                    new_df["Rate (比例)"] = new_df["Rate (比例)"].apply(format_rate)
                    new_df = new_df[["Station", "Data Type", "Item 名稱", "Rate (比例)", "Root Cause", "Corrective Action"]]

                    # 🌟 關鍵升級：把 Root Cause 加進來當作獨立資料的判斷依據
                    new_df = new_df.drop_duplicates(subset=["Station", "Data Type", "Item 名稱", "Root Cause"], keep='last')

                    required_cols = ["Station", "Data Type", "Item 名稱", "Rate (比例)", "Root Cause", "Corrective Action"]
                    
                    if 'Root cause' in db_df.columns:
                        db_df.rename(columns={'Root cause': 'Root Cause'}, inplace=True)

                    if not db_df.empty and all(col in db_df.columns for col in ["Station", "Data Type", "Item 名稱", "Root Cause"]):
                        db_df["Station"] = db_df["Station"].astype(str).str.strip()
                        db_df["Item 名稱"] = db_df["Item 名稱"].astype(str).str.strip()
                        db_df["Root Cause"] = db_df["Root Cause"].fillna("N/A").astype(str).str.strip()
                        
                        db_df = db_df.drop_duplicates(subset=["Station", "Data Type", "Item 名稱", "Root Cause"], keep='last')
                        
                        # 🌟 雲端資料庫更新時，也根據這 4 個條件進行精準配對
                        db_df = db_df.set_index(["Station", "Data Type", "Item 名稱", "Root Cause"])
                        new_df = new_df.set_index(["Station", "Data Type", "Item 名稱", "Root Cause"])
                        
                        db_df.update(new_df) 
                        db_df = db_df.combine_first(new_df) 
                        db_df = db_df.reset_index()
                    else:
                        db_df = new_df

                    db_df = db_df[required_cols]

                    upload_df = db_df.copy()
                    upload_df = upload_df.fillna("N/A").astype(str)
                    
                    sheet.clear()
                    sheet.update([upload_df.columns.values.tolist()] + upload_df.values.tolist())
                    
                    st.sidebar.success("✅ 雲端資料庫更新成功！")
                    st.rerun() 
                    
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