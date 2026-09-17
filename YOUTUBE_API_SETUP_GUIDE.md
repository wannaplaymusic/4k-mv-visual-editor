# 🔑 YouTube Data API v3 快速設定指南 (3 分鐘免費啟用)

本功能採用 Google 官方的 **YouTube Data API v3**，完全**免費**，不需要綁定信用卡。

只要依照以下步驟下載 `client_secrets.json` 並放入專案中，就能一鍵啟用全自動發布功能。

---

## 步驟 1：前往 Google Cloud Console

1. 打開瀏覽器，前往 [Google Cloud Console](https://console.cloud.google.com/)。
2. 使用您要用來上傳 YouTube 影片的 Google 帳號登入。
3. 點擊頂部的專案選單，點擊 **「新增專案 (New Project)」**。
   - 專案名稱例如：`MV-Auto-Uploader-1`
   - 點擊 **「建立 (Create)」**。

---

## 步驟 2：啟用 YouTube Data API v3

1. 在左側選單（或上方搜尋列）進入 **「API 和服務 (APIs & Services)」** > **「程式庫 (Library)」**。
2. 搜尋 `YouTube Data API v3`。
3. 點擊進入後，按 **「啟用 (Enable)」**。

---

## 步驟 3：設定 OAuth 同意畫面 (Consent Screen)

1. 在左側選單點擊 **「OAuth 同意畫面 (OAuth consent screen)」**。
2. 使用者類型 (User Type) 選擇 **「外部 (External)」**，點擊 **「建立」**。
3. 填寫基本資訊：
   - **應用程式名稱 (App name)**：`MV Uploader`
   - **使用者支援電子郵件**：選擇您的 Gmail
   - **開發人員聯絡資訊**：填寫您的 Gmail
   - 點擊「儲存並繼續」。
4. 範圍 (Scopes)：直接點擊「儲存並繼續」（使用預設即可）。
5. **測試使用者 (Test users) ★ 重要**：
   - 點擊 **「+ ADD USERS (新增使用者)」**。
   - 輸入您要上傳 YouTube 影片的 **Gmail 帳號**。
   - 點擊「儲存並繼續」。

---

## 步驟 4：建立憑證並下載 `client_secrets.json`

1. 在左側選單點擊 **「憑證 (Credentials)」**。
2. 點擊頂部的 **「+ 建立憑證 (Create Credentials)」** > 選擇 **「OAuth 用戶端 ID (OAuth client ID)」**。
3. **應用程式類型 (Application type)**：選擇 **「桌面應用程式 (Desktop App)」**。
4. 名稱：`MV Desktop Client`，點擊 **「建立」**。
5. 彈出建立成功視窗後，點擊 **「下載 JSON (Download JSON)」**。
6. 將下載下來的檔案放入專案中的 `youtube_credentials/` 目錄：
   ```
   youtube_credentials/client_secrets.json
   ```
   *(或直接命名為 `client_secrets.json` 放在專案根目錄亦可)*。

---

## 🚀 想要突破單日 6 部上限？（多憑證自動輪換池・支援單日 40+ 首）

如果您需要單日一口氣上傳 40 部以上：
- 系統已內建 **多憑證自動輪換池 (Credential Pool)**。
- 每個 Google Cloud 專案每日提供 10,000 點配額（約可上傳 6 部 4K 影片）。
- 本系統現已建立並支援 7 個專案：
  1. `client_secrets.json` (專案 1)
  2. `client_secrets_2.json` (專案 2)
  3. `client_secrets_3.json` (專案 3)
  4. `client_secrets_4.json` (專案 4)
  5. `client_secrets_5.json` (專案 5)
  6. `client_secrets_6.json` (專案 6)
  7. `client_secrets_7.json` (專案 7)
- **總承載能力**：**7 個專案 × 6 首 = 42 首 / 天**！
- 系統會在任一專案額度用罄時（回傳 `quotaExceeded` / `403`），自動無縫切換至下一個專案接力上傳，完全零中斷！

---

## 首次上傳授權說明

當您第一次點擊「開始上傳」時：
1. 瀏覽器會自動彈出 Google 登入視窗。
2. 選擇您的 YouTube 頻道帳號。
3. 點擊「繼續 (Continue)」允許上傳權限。
4. 授權成功後，系統會自動在本地保存 `token.json`，之後上傳**完全不需再手動登入**！
