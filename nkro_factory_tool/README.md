# NKRO Ghost Key 工廠測試工具

依 Acer/Infinity NKRO Ghost Key Test 規格製作的產線工具（不依賴原廠 `Darfon_HID.dll`）。

## 功能

- 外接（操作員）鍵盤按 **SPACE** 開始測試
- 5 秒內擷取待測鍵盤（DUT）按鍵
- 對照 jig 預期約 30 鍵：無 **missing**、無 **ghost** → **PASS**，否則 **FAIL/NG**
- 畫面顯示鍵盤示意、計時、Detect Key Count、P/N / SN
- 結果寫入 `logs/nkro_YYYYMMDD.csv`

## 環境

- Windows 10/11
- Python 3.10+（開發／直接執行）
- 建議兩把鍵盤：一把操作員、一把 DUT（或筆電內建 KB 當 DUT）

## 直接執行

```bat
cd nkro_factory_tool
python main.py
```

首次請在畫面下方選擇：

1. **Operator KB**：按 SPACE 開始用的外接鍵盤  
2. **DUT KB**：jig / 待測鍵盤  
3. 可按 **Save Devices** 寫入 `config/devices.json`，下次自動套用

## Profile

| ID | 說明 |
|----|------|
| `infinity16_cherry_us` | Infinity16 Cherry（預設） |
| `scorpio16_perkey_us` | Scorpio16 PerKey |

預期鍵位來自規格 ghost-key jig（F1/1/Q/A/Z … 等約 30 鍵），可在 `config/profiles/*.json` 調整。

## 產線操作

1. 接上操作員鍵盤與待測 KB，選擇裝置與 Profile  
2. （可選）刷入 P/N、SN  
3. 按操作員鍵盤 **SPACE**  
4. 用 jig 壓住規格對應鍵並維持約 **5 秒**  
5. 看 **PASS** / **FAIL**；FAIL 時下方會列 Missing / Ghost  
6. **Next Test** 清空 SN 進入下一台；**Clear Test** 重測同一台

## 無 jig 驗收

1. 兩把 USB 鍵盤分別設為 Operator / DUT  
2. SPACE 後，在 DUT 上於 5 秒內按齊 profile 的 `expected_keys` → 應 PASS  
3. 少按或故意多按其他鍵 → 應 FAIL  

單鍵盤實驗室模式（Operator = DUT）也可測；啟動鍵 SPACE 的連發不會算 ghost。

## 打包 exe

```bat
scripts\build_exe.bat
```

輸出目錄：`dist\NKRO_GhostKey_Test\`（內含 `NKRO_GhostKey_Test.exe` 與 `config`）。

請把整個資料夾拷到產線 PC；`logs` 會寫在 exe 同層。

## 自檢

```bat
python scripts\selfcheck.py
```

## 本階段不做

- Country Code / FW_ID 更新  
- Color / Effect / Version / 讀韌體（需原廠 DLL）  
- KSI/KSO 波形 Excel 判定  
