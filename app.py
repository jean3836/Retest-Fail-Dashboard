# --- 覆蓋與更新邏輯 ---
                # 安全護城河：確保雲端資料庫 (db_df) 擁有所有正確的欄位
                required_cols = ["Station", "Data Type", "Item 名稱", "Rate (比例)", "Root Cause", "Corrective Action"]
                
                # 檢查 db_df 是否真的有這些欄位，如果沒有，就當作它是空的重新來過
                if not db_df.empty and all(col in db_df.columns for col in ["Station", "Data Type", "Item 名稱"]):
                    # 洗雲端資料庫的舊資料空白，並去除可能存在的重複項
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
                    # 如果雲端資料庫格式損壞或是全空的，直接以新資料為主
                    db_df = new_df

                # 確保 Root Cause 大小寫一致，並只保留我們需要的欄位
                if 'Root cause' in db_df.columns:
                    db_df.rename(columns={'Root cause': 'Root Cause'}, inplace=True)
                
                # 強制過濾只剩下這 6 個欄位，確保寫回 Google Sheets 時格式完美
                db_df = db_df[required_cols]

                # 準備上傳到 Google Sheets 的資料
                upload_df = db_df.copy()
                upload_df = upload_df.fillna("N/A").astype(str)
                
                # 清空並寫入
                sheet.clear()
                sheet.update([upload_df.columns.values.tolist()] + upload_df.values.tolist())
                
                st.sidebar.success("✅ 雲端資料庫更新成功！")
                st.rerun()