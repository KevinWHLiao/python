# 流亡黯道 · 查詢工具

Path of Exile（PoE1）與 Path of Exile 2 用的 Windows 桌面查詢工具。以 Python + CustomTkinter 做成，資料主要來自 [poedb.tw](https://poedb.tw/tw)、[poe2db.tw](https://poe2db.tw/tw)、[poe.ninja](https://poe.ninja)、[Maxroll](https://maxroll.gg/poe2) 與 [官方賣場](https://www.pathofexile.com/trade)。

## 功能

| 功能 | 說明 |
|---|---|
| **詞綴查詢** | 可切換 PoE1／PoE2，依裝備部位查前綴／後綴／固定／汙染詞（階層、物等、權重、勢力來源） |
| **商店配方** | 商人交易：獎勵、材料、分類 |
| **工藝解鎖區域** | 工藝台配方解鎖地圖、消耗、適用部位 |
| **價格查詢** | 可切換 PoE1／PoE2 的 poe.ninja 估價。PoE1：通貨、傳奇、寶石、輿圖等；PoE2：通貨、碎片、精華、符文、魂核、神像、未切割寶石、探險文物、深淵之骨、族裔寶石、傳奇武器／護甲／飾品／藥劑／護符／珠寶／聖物／石板、先驅石板 |
| **官方賣場** | pathofexile.com/trade：關鍵字提示、賣家狀態、分類／物等／價格／詞綴過濾、上架預覽 |
| **流派排名** | poe.ninja 熱門流派、DPS／EHP、逐日占比 |
| **每季開荒推薦** | 可切換 PoE1／PoE2。PoE1：依類型／手感／預算篩選開荒 Build（本地目錄）；PoE2：Maxroll 開荒昇華 tier list（可線上更新） |
| **中文化 PIN** | poedb.tw 繁中／簡中 PIN 與遊戲版本 |
| **外部連結** | Craft of Exile、軍團珠寶（Timeless Jewel）查詢 |

詞綴／商店／工藝／開荒推薦可離線查（本地 JSON）；市價、賣場、流派、PIN 需連網。

## 環境需求

- Windows
- Python 3.10+（建議）
- 依賴：`customtkinter`（其餘為標準函式庫）

```bash
py -3 -m pip install -r requirements.txt
```

打包 exe 時另需 PyInstaller。

## 啟動方式

雙擊：

```text
開啟詞綴查詢.bat
```

或在專案根目錄執行：

```bash
py -3 poe_affix_gui.py
```

```bash
py -3 -m poe_affix
```

## 更新本地資料

聯盟改版或 PoEDB／PoE2DB 更新後，可在對應視窗按更新按鈕，或用指令重抓：

```bash
# 詞綴（PoE1）→ poe_affix_data/mods.json
py -3 -m poe_affix.sync

# 詞綴（PoE2）→ poe_affix_data/mods_poe2.json
py -3 -m poe_affix.sync poe2

# PoE2 開荒昇華 tier list（Maxroll）→ poe_affix_data/league_starters_poe2.json
py -3 -m poe_affix.starters_sync

# PoE2 物品中文名（poe.ninja 名稱 → poe2db 繁中）→ poe_affix_data/names_zh_poe2.json
py -3 -m poe_affix.i18n_sync
```

GUI 內也可分別更新：

- 詞綴查詢 → 切換 PoE1／PoE2 後按「更新資料」
- 商店配方 →「從 PoEDB 更新商店配方」
- 工藝解鎖 →「從 PoEDB 更新工藝資料」
- 每季開荒推薦 →「更新 PoE2 資料」（重抓 Maxroll tier list）

價格、官方賣場與流派會即時打對應 API（記憶體快取約 10～15 分鐘）。中文化 PIN 每次開啟／重新整理時從 PoEDB 抓取。

## 資料來源與抓取方式

| 資料 | 來源 | 方式 |
|---|---|---|
| 詞綴（PoE1） | poedb.tw ModsView | 下載 HTML，抽出 `new ModsView({...})` JSON，寫入 `mods.json` |
| 詞綴（PoE2） | poe2db.tw ModsView | 同上，寫入 `mods_poe2.json` |
| 商店／工藝 | poedb.tw 表格頁 | 解析 HTML `<table>`，寫入 `vendor.json` / `crafting.json` |
| 中文化 PIN | poedb.tw/tw/chinese | 下載頁面後以正則解析 |
| 價格（PoE1） | poe.ninja `/poe1/api/economy` | HTTP JSON（exchange + stash item overview），以混沌石計價 |
| 價格（PoE2） | poe.ninja `/poe2/api/economy` | HTTP JSON（僅 exchange overview），以神聖石計價 |
| 官方賣場 | pathofexile.com/api/trade | HTTP JSON（search + fetch） |
| 流派 | poe.ninja builds | HTTP（含 protobuf 解析） |
| 中文物品名（PoE1） | `names_zh.json` + `i18n.py` | 本地對照表（顯示用） |
| 中文物品名（PoE2） | poe2db.tw 物品頁 ＋ `names_zh_poe2.json` | 以 poe.ninja 回傳的英文名逐一查 poe2db 頁面標題，寫入對照表 |
| 每季開荒推薦（PoE1） | `league_starters.json` | 本地標籤目錄＋篩選推薦（可手動更新） |
| 每季開荒推薦（PoE2） | maxroll.gg 開荒昇華 tier list ＋ poe2db.tw | 解析 Maxroll 伺服器端渲染的 tier list，昇華名稱再向 poe2db 取繁中，寫入 `league_starters_poe2.json` |

本地資料目錄：`poe_affix_data/`。

## 打包成 exe（可選）

已附 `poe_affix.spec`，可用 PyInstaller：

```bash
pip install pyinstaller
pyinstaller poe_affix.spec
```

產出無主控台視窗程式 `PoE查詢工具.exe`，並會一併打包 `poe_affix_data` 內的資料檔。

## 專案結構（精簡）

```text
poe_affix_gui.py          # 啟動入口
開啟詞綴查詢.bat
poe_affix.spec            # PyInstaller 設定
poe_affix/
  menu.py                 # 主選單
  gui.py / catalog.py / sync.py   # 詞綴查詢與同步
  vendor*.py / craft*.py          # 商店、工藝
  economy*.py / builds*.py / trade*.py  # 價格、流派、官方賣場
  starters*.py                    # 每季開荒推薦（含 starters_sync.py：Maxroll PoE2 tier list）
  chinese*.py                     # 中文化 PIN
  i18n.py / i18n_sync.py          # 中文名對照（i18n_sync.py：向 poe2db 補 PoE2 名稱）
  theme.py / net.py
poe_affix_data/
  mods.json
  mods_poe2.json
  vendor.json
  crafting.json
  names_zh.json
  names_zh_poe2.json              # PoE2 物品中文名（poe2db）
  league_starters.json            # PoE1 開荒 Build 標籤目錄
  league_starters_poe2.json       # PoE2 開荒昇華 tier list（Maxroll）
```

## 改版後建議維護順序

1. 等 PoEDB／PoE2DB 更新後，同步對應遊戲的詞綴（工藝／商店仍為 PoE1）
2. 查價若出現英文／空白名稱：PoE1 補 `names_zh.json` 或 `i18n.py` 的 `EXTRA_NAMES`；
   PoE2 跑 `py -3 -m poe_affix.i18n_sync`（新聯盟物品 poe2db 可能還沒有繁中，會保留英文）
3. poe.ninja 新增經濟分類時，更新 `economy.py` 的 `EXCHANGE_TYPES`／`ITEM_TYPES`／`EXCHANGE_TYPES_POE2`
4. 新聯盟開季時更新 `league_starters.json`（標籤、梯隊、Guide／PoB 連結）；PoE2 直接按「更新 PoE2 資料」重抓 Maxroll
5. 同步或 PIN／流派整頁失敗時，再檢查 HTML／API 解析程式
6. 詞綴來源分類有疑慮時，先確認 `catalog.py` 的 `CORRUPT_SOURCE_KEYS`／`IMPLICIT_SOURCE_KEYS`
   （奉獻寶珠 `corruption_upgrade`、不穩定植入物 `graft_corrupted` 是固定詞，不算汙染詞）

## 授權與注意

- 個人／本地查詢用途；資料版權屬各來源網站與遊戲官方
- 請勿對 PoEDB／PoE2DB／poe.ninja／官方賣場過於頻繁請求；同步已內建間隔延遲
