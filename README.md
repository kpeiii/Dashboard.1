# 資料

本 repo **不包含原始資料**。請自行從 Kaggle 下載後放到：

```
data/raw/supply_chain_dataset1.csv
```
> Dataset: `<名稱>` — [https://www.kaggle.com/datasets/<owner>/<dataset>](https://www.kaggle.com/datasets/srisyra02/amazon-product-sales-data-42k-items-2025/data)

## 預期欄位（15 欄）

`date, sku_id, warehouse_id, supplier_id, region, units_sold, inventory_level,
supplier_lead_time_days, reorder_point, order_quantity, unit_cost, unit_price,
promotion_flag, stockout_flag, demand_forecast`

粒度：一列 = 一個日期 × SKU × 倉庫（不可重複）。

請先建立 `data/raw/` 資料夾再放入 CSV（已被 `.gitignore` 排除，不會被提交）。
