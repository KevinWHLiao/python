# Kings Advanced Stats

從 NBA.com 同一套 stats API 抓 **沙加緬度國王** 指定球季全隊進階數據（官網 Players → Advanced）。

預設是剛結束的上季（現在是 **2025-26** 例行賽）。

## 怎麼跑

只需要 Python 3.10+：

```bash
pip install -r requirements.txt
python fetch_kings_advanced.py
```

官網（www.nba.com/stats）能開、腳本卻連不上時，通常是因為真正的資料在 `stats.nba.com`，且有 Akamai 防機器人。這個工具會用瀏覽器 TLS 偽裝（`curl_cffi`）先開官網再抓 API。

存成 CSV / JSON：

```bash
python fetch_kings_advanced.py --csv kings-2025-26-advanced.csv --json kings-2025-26-advanced.json
```

其他球季或季後賽：

```bash
python fetch_kings_advanced.py --season 2024-25
python fetch_kings_advanced.py --season 2025-26 --playoffs
```

## 會拿到哪些數字

| 欄位 | 意義 |
| --- | --- |
| OFFRTG / DEFRTG / NETRTG | 每 100 回合攻防與淨效率 |
| AST% / AST/TO / AST RATIO | 助攻相關 |
| OREB% / DREB% / REB% | 籃板率 |
| TOV% / EFG% / TS% | 失誤與投籃效率 |
| USG% | 使用率 |
| PACE | 節奏 |
| PIE | Player Impact Estimate（NBA.com 自己的影響力指標） |

**BPM、EPM（有時被寫成 EPB）不在 NBA.com 這張進階表。** BPM 多半在 Basketball-Reference，EPM 在 Dunks & Threes。若要再加這兩個來源可以跟我說。
