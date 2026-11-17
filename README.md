# Supply Chain Inventory Risk & Decision Support Dashboard

以公開的 Kaggle 供應鏈資料集（50 SKU × 5 倉庫 × 365 天）建立的庫存風險分析流程與互動式儀表板。
目標是把「庫存覆蓋天數 vs. 供應商交期」的分析，轉成可以排序、篩選、做情境比較的決策輔助工具。

**Live demo：** `https://<你的帳號>.github.io/<repo 名稱>/`（啟用 GitHub Pages 後填入，見下方）

## 分析內容

| 模組 | 說明 |
|---|---|
| 資料驗證 | 欄位檢查、SKU × 日期 × 倉庫 不可重複 |
| KPI | SKU / 供應商 / 倉庫層級的庫存、覆蓋天數、低於 ROP 比例、預測準確度 |
| ABC 分析 | 依年消耗價值（年需求 × 平均單位成本），累積 80% / 95% 為 A / B / C |
| 風險分析 | 在 **SKU × 倉庫** 層級，計算「庫存覆蓋天數 < 供應商交期」的觀測日比例 |
| 行動優先級 | A 類且 High → P1；其他 High 或 A 類 Medium → P2；其餘 P3 |
| 一致性檢查 | 各風險級別的 `stockout_flag` 比例是否不同 |
| 情境分析 | 需求 +0/10/20% × 交期 +0/10/20% 的壓力測試（9 種組合） |

## 快速開始

```bash
git clone https://github.com/<你的帳號>/<repo 名稱>.git
cd <repo 名稱>
pip install -r requirements.txt

# 1. 建立 data/raw/ 資料夾，把 Kaggle CSV 放到 data/raw/supply_chain_dataset1.csv（見 data/README.md）
# 2. 執行分析，產生 outputs/*.csv 與 docs/data.js
python run_pipeline.py --input data/raw/supply_chain_dataset1.csv

# 3. 開啟儀表板：直接雙擊 docs/index.html，或
python -m http.server -d docs 8000   # 再開 http://localhost:8000
```

### 部署到 GitHub Pages

1. 先在本機執行 `python run_pipeline.py`，確認 `docs/data.js` 已更新並一起 commit。
2. Repo → Settings → Pages → Source 選 `Deploy from a branch`，Branch 選 `main`，資料夾選 `/docs`。
3. 儀表板是純 HTML/CSS/JS，沒有外部依賴；`docs/data.js` 只包含**彙總後的結果**，不含原始 CSV。

## 專案結構

```
├── run_pipeline.py          # 一鍵執行入口
├── scm_risk/
│   ├── pipeline.py          # 清理、特徵、KPI、ABC、風險、情境分析
│   └── export.py            # 輸出 CSV 與 docs/data.js
├── docs/
│   ├── index.html           # 儀表板（GitHub Pages）
│   └── data.js              # 由 run_pipeline.py 產生
├── notebooks/               # 原始探索用 notebook（保留輸出）
└── data/                    # 原始資料放這裡（不提交）
```

## 方法重點與限制

- `days_supply_below_lead_time_rate` 是**風險代理指標，不是實際缺貨機率**。
- 庫存覆蓋天數 = 當日庫存 ÷ 7 日滾動平均需求（每個 SKU × 倉庫各自計算）；前 6 筆沒有值，不納入比例計算。
- ABC 的 80% / 95% 分界與風險的 P50 / P80 分位數門檻，是本專案採用的**分析規則，不是通用標準**；風險級別只代表資料內的相對排序。
- ABC 以 SKU 跨倉庫彙總，因此同一 SKU 在各倉庫的 ABC 類別相同。
- **風險分級尚未被驗證**：此資料集的 `stockout_flag` 全部為 0，沒有變異，無法檢驗風險級別是否對應較高的缺貨率。儀表板會在這種情況下自動顯示警示。
- 情境分析是壓力測試，不是需求預測。
- 資料為公開資料集，本專案是方法示範，不代表任何真實企業的營運狀況。

## 與原 notebook 的差異

- 風險級別修正：原本 Medium 的條件是 `>= P50`，但此資料的 P50 為 0%，導致指標為 0 的組合也被歸為 Medium、Low 永遠不會出現（原輸出的 ABC × 風險表只有 High / Medium）。
  現在 High / Medium 都要求指標 > 0，指標為 0 的組合為 Low。**High 與 P1 的組合不受影響**，P2 / P3 的數量會和原 notebook 不同。
- ABC 分類的 bins 上限加了極小的容差，避免浮點誤差讓最後一個 SKU 被分成 NaN。
- 流程拆成函式，並新增 CSV 輸出與儀表板。

## 主要結果（91,250 筆觀測；2024-01-01 ~ 2024-12-30）

- A 類 37 個 SKU，占年消耗價值 79.2%；B 類 9 個、C 類 4 個。
- 250 個 SKU × 倉庫組合中：High 52、Medium 57、Low 141；P1（A 類且 High）37 個、P2 58 個、P3 155 個。
- 基準情境下，平均覆蓋不足比例 3.79%；需求 +20% 且交期 +20% 時升至 12.72%。
- 風險分級無法用 `stockout_flag` 驗證（全部為 0）。

## License

MIT（見 `LICENSE`）。資料集授權請以 Kaggle 原頁面為準。
