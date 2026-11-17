"""一鍵執行：讀取 CSV -> 分析 -> 輸出 outputs/*.csv 與 docs/data.js。

用法：
    python run_pipeline.py --input data/raw/supply_chain_dataset1.csv
"""
import argparse
from pathlib import Path

from scm_risk import run_all
from scm_risk.export import write_csvs, write_dashboard_data


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default="data/raw/supply_chain_dataset1.csv", type=Path)
    ap.add_argument("--outputs", default="outputs", type=Path, help="CSV 輸出資料夾")
    ap.add_argument("--docs", default="docs", type=Path, help="dashboard 資料夾（會寫入 data.js）")
    args = ap.parse_args()

    if not args.input.exists():
        raise SystemExit(
            f"找不到 {args.input}。請先從 Kaggle 下載資料集，放到該路徑（見 data/README.md）。"
        )

    res = run_all(args.input)
    write_csvs(res, args.outputs)
    data_path = write_dashboard_data(res, args.docs)

    m = res.meta
    print(f"資料：{m['rows']:,} 列，{m['date_min']} ~ {m['date_max']}，"
          f"{m['n_sku']} SKU × {m['n_warehouse']} 倉庫")
    print(res.abc_summary.round(2).to_string(index=False))
    print(res.sku_wh_risk["action_priority"].value_counts().to_string())
    print(f"已輸出：{args.outputs}/ 與 {data_path}")


if __name__ == "__main__":
    main()
