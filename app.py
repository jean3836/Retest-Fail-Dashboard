import streamlit as st
import pandas as pd
import gspread
import json
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="產線數據查找工具", layout="wide")

# ==========================================
# 🌟 新增：隱藏預設的開發者工具 (僅 Admin 可見)
# ==========================================
# 只要目前的角色不是 Admin (包含尚未登入的狀態)，就注入 CSS 隱藏 Header 和 Footer
if st.session_state.get('role') != "Admin":
    hide_st_style = """
        <style>
        /* 隱藏右上角的 Header (包含三個點 Menu) */
        header {visibility: hidden;}
        /* 隱藏底部的 Made with Streamlit 浮水印 */
        footer {visibility: hidden;}
        </style>
    """
    st.markdown(hide_st_style, unsafe_allow_html=True)

# ==========================================
# 1. 使用者權限設定 (迷你資料庫)
# ==========================================
USER_DB = {
    "jean_admin": {"password": "123", "role": "Admin"},    # 管理員：擁有一切權限
    "user_editor": {"password": "456", "role": "Editor"},  # 編輯者：可上傳資料
    "user_viewer": {"password": "789", "role": "Viewer"}   # 檢視者：只能搜尋
}

# ==========================================
# 2. 初始化登入狀態
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = None

# ==========================================
# 3. 定義後台功能 (Google Sheets 連線與資料處理)
# ==========================================
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
SHEET_NAME = "Retest_Fail_Database"

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
        st.error(f"連線設定失敗，請檢查金鑰格式：{e}")
        return None

def load_database(client):
    if client:
        try:
            sheet = client.open(SHEET_NAME).sheet1
            records = sheet.get_all_records()
            if records:
                return pd.DataFrame(records), sheet, True
        except Exception as e:
            st.error(f"無法連線至 Google 試算表，請確認已將機器人 Email 加入共用名單，且名稱為 {SHEET_NAME}。錯誤：{e}")
    return pd.DataFrame(columns=["Station", "Data Type", "Item 名稱", "Rate (比例)", "Root Cause", "Corrective Action"]), None, False

@st.cache_data
def get_template():
    template_df = pd.DataFrame(columns=[
        "Station (A)", "B", "Retest item / Fail item (C)", "D", "E", 
        "RR / FR (F)", "G", "Root cause (H)", "Corrective action (I)"
    ])
    return template_df.to_csv(index=False).encode('utf-8-sig')

def display_interactive_dataframe(df, key_prefix):
    """建立可點選的 DataFrame，並在點擊後於下方顯示完整的資料卡片"""
    event = st.dataframe(
        df,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"{key_prefix}_table"
    )
    
    if event.selection.rows:
        selected_idx = event.selection.rows[0]
        row_data = df.iloc[selected_idx]
        item_index = df.index[selected_idx]
        
        st.markdown("---")
        st.markdown(f"### 📌 詳細資料卡片 (項次：{item_index})")
        
        col1, col2 = st.columns([1, 1.5])
        with col1:
            st.info(f"**📍 Station:** \n\n {row_data['Station']}")
            st.info(f"**🏷️ Data Type:** \n\n {row_data['Data Type']}")
            st.info(f"**📦 Item 名稱:** \n\n {row_data['Item 名稱']}")
            st.info(f"**📊 Rate (比例):** \n\n {row_data['Rate (比例)']}")
        with col2:
            st.warning(f"**🔍 Root Cause (根本原因):** \n\n {row_data['Root Cause']}")
            st.success(f"**🛠️ Corrective Action (改善對策):** \n\n {row_data['Corrective Action']}")
        st.markdown("---")


# ==========================================
# 4. 主畫面邏輯控制 (登入畫面 vs 主系統畫面)
# ==========================================
if not st.session_state.logged_in:
    # 【畫面 A：尚未登入，顯示登入框】
    st.title("🔒 產線數據庫系統 - 登入")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.write("請輸入您的帳號密碼以繼續：")
        username = st.text_input("帳號")
        password = st.text_input("密碼", type="password")
        
        if st.button("登入", use_container_width=True):
            if username in USER_DB and USER_DB[username]["password"] == password:
                st.session_state.logged_in = True
                st.session_state.role = USER_DB[username]["role"]
                st.session_state.username = username
                st.rerun()
            else:
                st.error("❌ 帳號或密碼錯誤，請重新輸入！")

else:
    # 【畫面 B：登入成功，顯示主系統】
    
    # --- 顯示右上角的登出按鈕與目前身分 ---
    col_empty, col_logout = st.columns([8, 2])
    with col_logout:
        st.write(f"👤 {st.session_state.username} ({st.session_state.role})")
        if st.button("登出", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.role = None
            st.session_state.username = None
            st.rerun()

    st.title("🔍 產線 Retest & Fail 數據庫系統")

    # --- 啟動資料庫連線 ---
    client = init_connection()
    db_df, sheet, db_connected = load_database(client)

    # ==========================================
    # 5. 側邊欄：權限管控區 (僅 Admin / Editor 可見)
    # ==========================================
    if st.session_state.role in ["Admin", "Editor"]:
        with st.sidebar:
            st.header("📥 第一步：模板下載")
            st.download_button(label="下載標準模板 (CSV)", data=get_template(), file_name="Data_Template.csv", mime="text/csv")

            st.header("📤 第二步：上傳最新數據")
            uploaded_file = st.file_uploader("上傳報表", type=["csv", "xlsx"])
            overwrite_mode = st.checkbox("⚠️ 完整覆蓋模式 (推薦)", value=True, help="勾選此項將會清除雲端所有舊資料，完全以本次上傳的檔案為準。")

            if uploaded_file and db_connected:
                if st.button("🚀 確認上傳並更新雲端"):
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
                                    col_c_name = str(df.columns[2]).strip().lower()
                                    if "retest" in col_c_name:
                                        data_type = "⚠️ Retest (RR)"
                                    elif "fail" in col_c_name or "failure" in col_c_name:
                                        data_type = "🛑 Fail (FR)"
                                    else:
                                        all_cols_str = " ".join([str(c).lower() for c in df.columns])
                                        if "retest" in all_cols_str:
                                            data_type = "⚠️ Retest (RR)"
                                        elif "fail" in all_cols_str or "failure" in all_cols_str:
                                            data_type = "🛑 Fail (FR)"
                                        else:
                                            continue

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
                                
                                for col in ["Station", "Item 名稱", "Root Cause", "Corrective Action"]:
                                    new_df[col] = new_df[col].astype(str).str.replace(r'\r+|\n+', ' ', regex=True).str.strip()
                                
                                new_df["Root Cause"] = new_df["Root Cause"].replace('nan', 'N/A').fillna("N/A")
                                new_df["Corrective Action"] = new_df["Corrective Action"].replace('nan', 'N/A').fillna("N/A")
                                
                                new_df = new_df[~new_df["Item 名稱"].str.contains("item", case=False, na=False)]
                                new_df = new_df[new_df["Item 名稱"] != "nan"]

                                def format_rate(val):
                                    if pd.isna(val) or str(val).strip() in ["", "nan"]: return ""
                                    if isinstance(val, str) and '%' in val: return val
                                    try: return f"{float(val) * 100:.4f}%"
                                    except: return str(val)

                                new_df["Rate (比例)"] = new_df["Rate (比例)"].apply(format_rate)
                                new_df = new_df[["Station", "Data Type", "Item 名稱", "Rate (比例)", "Root Cause", "Corrective Action"]]
                                new_df = new_df.drop_duplicates(subset=["Station", "Data Type", "Item 名稱", "Root Cause"], keep='last')

                                required_cols = ["Station", "Data Type", "Item 名稱", "Rate (比例)", "Root Cause", "Corrective Action"]
                                
                                if 'Root cause' in db_df.columns:
                                    db_df.rename(columns={'Root cause': 'Root Cause'}, inplace=True)

                                if overwrite_mode or db_df.empty:
                                    db_df = new_df
                                else:
                                    if all(col in db_df.columns for col in ["Station", "Data Type", "Item 名稱", "Root Cause"]):
                                        db_df["Station"] = db_df["Station"].astype(str).str.strip()
                                        db_df["Item 名稱"] = db_df["Item 名稱"].astype(str).str.strip()
                                        db_df["Root Cause"] = db_df["Root Cause"].fillna("N/A").astype(str).str.strip()
                                        db_df = db_df.drop_duplicates(subset=["Station", "Data Type", "Item 名稱", "Root Cause"], keep='last')
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
                                
                                st.sidebar.success("✅ 雲端資料庫已重新整理並更新成功！")
                                st.rerun() 
                                
                        except Exception as e:
                            st.sidebar.error(f"資料處理或上傳失敗：{e}")

    # ==========================================
    # 6. 主畫面：所有人都能看的資料搜尋區
    # ==========================================
    st.markdown("### 🔎 搜尋歷史資料庫")

    if not db_connected:
        st.warning("請先設定 Streamlit Secrets 金鑰以連結資料庫。")
    elif db_df.empty:
        st.info("雲端資料庫目前是空的，請通知管理員上傳報表！")
    else:
        db_df.index = range(1, len(db_df) + 1)
        
        search_query = st.text_input("請輸入想尋找的 Retest item 或 Fail item (例如: UnbindStateSync_3)")
        
        if search_query:
            mask = db_df["Item 名稱"].astype(str).str.contains(search_query, case=False, na=False)
            result_df = db_df[mask]
            
            if not result_df.empty:
                st.success(f"從雲端找到 {len(result_df)} 筆相符的歷史資料 (💡 點擊表格內任意一列即可查看完整內容)：")
                display_interactive_dataframe(result_df, "search")
            else:
                st.warning("資料庫中查無符合的資料。")
        
        with st.expander("點擊展開預覽：雲端資料庫中的所有紀錄 (💡 點擊表格內任意一列即可查看完整內容)"):
            display_interactive_dataframe(db_df, "full_db")