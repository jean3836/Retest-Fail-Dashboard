if processed_data:
                new_df = pd.concat(processed_data, ignore_index=True)
                new_df["Station"] = new_df["Station"].ffill()
                new_df = new_df.dropna(subset=["Item 名稱"])
                
                # --- 新增：自動清洗機（去除換行與前後空白） ---
                new_df["Station"] = new_df["Station"].astype(str).str.strip()
                new_df["Item 名稱"] = new_df["Item 名稱"].astype(str).str.strip()
                
                # 去除把「標題」當成資料讀進來的行
                new_df = new_df[~new_df["Item 名稱"].str.contains("item", case=False, na=False)]

                # 百分比格式化
                def format_rate(val):
                    if pd.isna(val): return val
                    if isinstance(val, str) and '%' in val: return val
                    try: return f"{float(val) * 100:.4f}%"
                    except: return str(val)

                new_df["Rate (比例)"] = new_df["Rate (比例)"].apply(format_rate)
                new_df = new_df[["Station", "Data Type", "Item 名稱", "Rate (比例)", "Root Cause", "Corrective Action"]]

                # --- 新增：處理 Excel 內部的重複項，保留最後一筆有資料的 ---
                new_df = new_df.drop_duplicates(subset=["Station", "Data Type", "Item 名稱"], keep='last')

                # --- 覆蓋與更新邏輯 ---
                if not db_df.empty:
                    # 先清洗雲端資料庫的舊資料空白，並去除可能存在的重複項
                    db_df["Station"] = db_df["Station"].astype(str).str.strip()
                    db_df["Item 名稱"] = db_df["Item 名稱"].astype(str).str.strip()
                    db_df = db_df.drop_duplicates(subset=["Station", "Data Type", "Item 名稱"], keep='last')
                    
                    # 設置唯一索引
                    db_df = db_df.set_index(["Station", "Data Type", "Item 名稱"])
                    new_df = new_df.set_index(["Station", "Data Type", "Item 名稱"])
                    
                    # 執行覆蓋與合併
                    db_df.update(new_df)
                    db_df = db_df.combine_first(new_df)
                    db_df = db_df.reset_index()
                else:
                    db_df = new_df

                # 確保 Root Cause 大小寫一致
                if 'Root cause' in db_df.columns:
                    db_df.rename(columns={'Root cause': 'Root Cause'}, inplace=True)

                # 準備上傳到 Google Sheets 的資料
                upload_df = db_df.copy()
                upload_df = upload_df.fillna("N/A").astype(str)
                
                # 清空並寫入
                sheet.clear()
                sheet.update([upload_df.columns.values.tolist()] + upload_df.values.tolist())
                
                st.sidebar.success("✅ 雲端資料庫更新成功！")
                st.rerun()
                
        except Exception as e:
            st.sidebar.error(f"資料處理或上傳失敗：{e}")