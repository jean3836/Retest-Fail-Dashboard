import pandas as pd

def process_and_categorize_data(df):
    """
    嚴格依照「表頭欄位」來判定該 DataFrame 是 Retest 還是 Fail 數據，
    完全不依賴 Item 內容字串。
    """
    # 取得所有欄位名稱，並統一轉小寫、去空白，確保判斷 100% 精準不受格式影響
    cleaned_columns = [str(col).strip().lower() for col in df.columns]
    
    # 【嚴格判斷 1】：只要表頭存在 'retest item'，整張表強制歸類為 RR (Retest)
    if 'retest item' in cleaned_columns:
        df['Data_Type'] = 'Retest'
        
        # 為了方便後續彙整，將名稱統一為通用的 'Item_Name', 'Qty', 'Rate'
        df = df.rename(columns={
            'Retest item': 'Item_Name',
            'Retest Qty': 'Qty',
            'RR': 'Rate'
        })
        
    # 【嚴格判斷 2】：只要表頭存在 'fail item' (或之前發現的筆誤 'fail tem')，強制歸類為 FR (Fail)
    elif 'fail item' in cleaned_columns or 'fail tem' in cleaned_columns or 'failure item' in cleaned_columns:
        df['Data_Type'] = 'Fail'
        
        # 統一欄位名稱 (使用 dict.get 避免 KeyError)
        rename_mapping = {}
        for col in df.columns:
            col_lower = str(col).strip().lower()
            if col_lower in ['fail item', 'fail tem', 'failure item']:
                rename_mapping[col] = 'Item_Name'
            elif col_lower == 'fail qty':
                rename_mapping[col] = 'Qty'
            elif col_lower == 'fr':
                rename_mapping[col] = 'Rate'
                
        df = df.rename(columns=rename_mapping)
        
    else:
        # 如果都不是，標記為未定義或跳過
        df['Data_Type'] = 'Undefined'

    return df

# --- 使用範例 ---
# 假設你用 pd.read_excel(sheet_name=None) 讀取了整份檔案的所有 sheet
# all_sheets_dict = pd.read_excel("你的檔案.xlsx", sheet_name=None)
# processed_dfs = []
# for sheet_name, df in all_sheets_dict.items():
#     processed_df = process_and_categorize_data(df)
#     processed_dfs.append(processed_df)
# 
# # 最後再把所有資料合併，就不會發生 Retest 和 Fail 互相覆蓋的問題
# final_master_df = pd.concat(processed_dfs, ignore_index=True)