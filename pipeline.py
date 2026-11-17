"""Supply chain inventory risk pipeline.

把 notebook 的分析流程整理成可重複執行的函式。
粒度：一列 = 一個日期 × SKU × 倉庫。庫存覆蓋天數與風險指標在 SKU × Warehouse 層級計算。

解讀限制：
- `days_supply_below_lead_time_rate` 是風險代理指標，不是實際缺貨機率。
- ABC 80/95% 分界與風險分位數門檻是本專案採用的分析規則，並非通用標準。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# 標準名稱 -> 原始 CSV 欄位名稱（snake_case 之後）
FIELD_MAP = {
    "date": "date",
    "sku": "sku_id",
    "warehouse": "warehouse_id",
    "supplier": "supplier_id",
    "region": "region",
    "inventory": "inventory_level",
    "demand": "units_sold",
    "forecast": "demand_forecast",
    "reorder_point": "reorder_point",
    "order_quantity": "order_quantity",
    "lead_time": "supplier_lead_time_days",
    "unit_cost": "unit_cost",
    "unit_price": "unit_price",
    "promotion": "promotion_flag",
    "stockout": "stockout_flag",
}

NUMERIC_COLS = [
    "inventory", "demand", "forecast", "reorder_point", "order_quantity",
    "lead_time", "unit_cost", "unit_price", "stockout", "promotion",
]

DEMAND_GROWTH = (0.00, 0.10, 0.20)
LEAD_TIME_GROWTH = (0.00, 0.10, 0.20)
ROLLING_WINDOW = 7

PRIORITY_ORDER = {
    "P1 - Immediate Review": 1,
    "P2 - Review": 2,
    "P3 - Monitor": 3,
}


@dataclass
class PipelineResult:
    daily: pd.DataFrame
    sku_kpi: pd.DataFrame
    supplier_kpi: pd.DataFrame
    warehouse_kpi: pd.DataFrame
    sku_abc: pd.DataFrame
    abc_summary: pd.DataFrame
    sku_wh_risk: pd.DataFrame
    stockout_by_risk: pd.DataFrame
    scenario_detail: pd.DataFrame
    scenario_summary: pd.DataFrame
    thresholds: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# 1. 載入與清理
# --------------------------------------------------------------------------- #
def to_snake_case(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9]+", "_", str(name).strip().lower())
    return name.strip("_")


def load_raw(path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [to_snake_case(c) for c in df.columns]
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].astype("string").str.strip().replace("", pd.NA)
    return df.drop_duplicates().copy()


# --------------------------------------------------------------------------- #
# 2. 標準化欄位與驗證
# --------------------------------------------------------------------------- #
def standardize(df: pd.DataFrame) -> pd.DataFrame:
    missing = {std: src for std, src in FIELD_MAP.items() if src not in df.columns}
    if missing:
        raise KeyError(f"缺少必要欄位：{missing}")

    out = df.rename(columns={src: std for std, src in FIELD_MAP.items()}).copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for col in NUMERIC_COLS:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    dup = out.duplicated(subset=["sku", "date", "warehouse"]).sum()
    if dup:
        raise ValueError(f"發現 {dup:,} 筆重複的 SKU × 日期 × Warehouse 紀錄，請先查明原因。")
    return out


# --------------------------------------------------------------------------- #
# 3. Feature engineering
# --------------------------------------------------------------------------- #
def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["inventory_value"] = df["inventory"] * df["unit_cost"]
    df["inventory_vs_rop"] = df["inventory"] - df["reorder_point"]
    df["below_rop"] = df["inventory"] < df["reorder_point"]

    df["forecast_error"] = df["demand"] - df["forecast"]
    df["absolute_forecast_error"] = df["forecast_error"].abs()
    # 簡化準確度：1 - |誤差| / 實際需求，下限 0；需求為 0 時不計算
    df["forecast_accuracy"] = (
        1 - df["absolute_forecast_error"] / df["demand"].replace(0, np.nan)
    ).clip(lower=0)

    df["unit_margin"] = df["unit_price"] - df["unit_cost"]
    df["margin_pct"] = df["unit_margin"] / df["unit_price"].replace(0, np.nan)

    df = df.sort_values(["sku", "warehouse", "date"]).copy()
    df["avg_daily_demand_7d"] = df.groupby(["sku", "warehouse"])["demand"].transform(
        lambda s: s.rolling(window=ROLLING_WINDOW, min_periods=ROLLING_WINDOW).mean()
    )
    df["days_of_supply"] = df["inventory"] / df["avg_daily_demand_7d"].replace(0, np.nan)

    valid = df["days_of_supply"].notna() & df["lead_time"].notna()
    df["supply_coverage_shortfall"] = np.where(
        valid, df["days_of_supply"] < df["lead_time"], np.nan
    )
    return df


# --------------------------------------------------------------------------- #
# 4. KPI
# --------------------------------------------------------------------------- #
def build_kpis(df: pd.DataFrame):
    sku_kpi = (
        df.groupby("sku")
        .agg(
            annual_demand=("demand", "sum"),
            avg_daily_demand=("demand", "mean"),
            avg_inventory=("inventory", "mean"),
            avg_inventory_value=("inventory_value", "mean"),
            avg_days_of_supply=("days_of_supply", "mean"),
            avg_lead_time=("lead_time", "mean"),
            below_rop_rate=("below_rop", "mean"),
            avg_absolute_forecast_error=("absolute_forecast_error", "mean"),
            avg_forecast_accuracy=("forecast_accuracy", "mean"),
            avg_unit_cost=("unit_cost", "mean"),
            avg_unit_price=("unit_price", "mean"),
            avg_margin_pct=("margin_pct", "mean"),
        )
        .reset_index()
    )
    supplier_kpi = (
        df.groupby("supplier")
        .agg(
            avg_lead_time=("lead_time", "mean"),
            total_demand=("demand", "sum"),
            avg_inventory=("inventory", "mean"),
            avg_inventory_value=("inventory_value", "mean"),
            total_order_quantity=("order_quantity", "sum"),
            below_rop_rate=("below_rop", "mean"),
            stockout_observations=("stockout", "sum"),
        )
        .reset_index()
    )
    warehouse_kpi = (
        df.groupby("warehouse")
        .agg(
            total_demand=("demand", "sum"),
            avg_inventory=("inventory", "mean"),
            avg_inventory_value=("inventory_value", "mean"),
            avg_days_of_supply=("days_of_supply", "mean"),
            below_rop_rate=("below_rop", "mean"),
            stockout_observations=("stockout", "sum"),
        )
        .reset_index()
    )
    return sku_kpi, supplier_kpi, warehouse_kpi


# --------------------------------------------------------------------------- #
# 5. ABC analysis
# --------------------------------------------------------------------------- #
def abc_analysis(df: pd.DataFrame, cuts=(80, 95)):
    sku_abc = (
        df.groupby("sku")
        .agg(annual_demand=("demand", "sum"), unit_cost=("unit_cost", "mean"))
        .reset_index()
    )
    sku_abc["annual_consumption_value"] = sku_abc["annual_demand"] * sku_abc["unit_cost"]
    sku_abc = sku_abc.sort_values("annual_consumption_value", ascending=False).reset_index(drop=True)

    total = sku_abc["annual_consumption_value"].sum()
    sku_abc["cumulative_value_pct"] = sku_abc["annual_consumption_value"].cumsum() / total * 100
    sku_abc["abc_class"] = pd.cut(
        sku_abc["cumulative_value_pct"],
        bins=[0, cuts[0], cuts[1], 100.0000001],
        labels=["A", "B", "C"],
        include_lowest=True,
    ).astype(str)

    summary = (
        sku_abc.groupby("abc_class")
        .agg(sku_count=("sku", "count"), total_consumption_value=("annual_consumption_value", "sum"))
        .reset_index()
    )
    summary["value_share_pct"] = summary["total_consumption_value"] / total * 100
    return sku_abc, summary


# --------------------------------------------------------------------------- #
# 6-7. 風險分析、分級與行動優先順序
# --------------------------------------------------------------------------- #
RISK_METRIC = "days_supply_below_lead_time_rate"


def risk_analysis(df: pd.DataFrame, sku_abc: pd.DataFrame):
    risk = (
        df.groupby(["sku", "warehouse"])
        .agg(
            avg_inventory=("inventory", "mean"),
            avg_days_of_supply=("days_of_supply", "mean"),
            avg_lead_time=("lead_time", "mean"),
            below_rop_rate=("below_rop", "mean"),
            **{RISK_METRIC: ("supply_coverage_shortfall", "mean")},
            avg_forecast_accuracy=("forecast_accuracy", "mean"),
            stockout_observations=("stockout", "sum"),
            annual_demand=("demand", "sum"),
            avg_inventory_value=("inventory_value", "mean"),
        )
        .reset_index()
    )
    risk["days_supply_gap"] = risk["avg_days_of_supply"] - risk["avg_lead_time"]
    risk = risk.merge(
        sku_abc[["sku", "abc_class", "annual_consumption_value", "cumulative_value_pct"]],
        on="sku", how="left", validate="many_to_one",
    )

    rate = risk[RISK_METRIC]
    p50 = float(rate.quantile(0.50))
    p80 = float(rate.quantile(0.80))

    # 注意：此資料集常有大量組合的指標為 0（p50 = 0）。
    # 若直接用 `>= p50` 判斷 Medium，會讓指標為 0 的組合也變成 Medium、Low 永遠不會出現。
    # 因此 High/Medium 都要求指標 > 0。
    risk["risk_level"] = np.select(
        [(rate >= p80) & (rate > 0), (rate >= p50) & (rate > 0)],
        ["High", "Medium"],
        default="Low",
    )

    is_a = risk["abc_class"] == "A"
    high = risk["risk_level"] == "High"
    medium = risk["risk_level"] == "Medium"
    risk["action_priority"] = np.select(
        [is_a & high, high | (is_a & medium)],
        ["P1 - Immediate Review", "P2 - Review"],
        default="P3 - Monitor",
    )
    risk["priority_rank"] = risk["action_priority"].map(PRIORITY_ORDER)
    risk = risk.sort_values(["priority_rank", RISK_METRIC], ascending=[True, False]).reset_index(drop=True)
    return risk, {"p50": p50, "p80": p80}


# --------------------------------------------------------------------------- #
# 9. 風險級別 vs. 資料中的缺貨標記
# --------------------------------------------------------------------------- #
def validate_against_stockout(df: pd.DataFrame, risk: pd.DataFrame) -> pd.DataFrame:
    merged = df.merge(
        risk[["sku", "warehouse", "risk_level"]],
        on=["sku", "warehouse"], how="left", validate="many_to_one",
    )
    return (
        merged.groupby("risk_level")
        .agg(
            observations=("stockout", "count"),
            stockout_observations=("stockout", "sum"),
            stockout_rate=("stockout", "mean"),
            avg_coverage_shortfall_rate=("supply_coverage_shortfall", "mean"),
        )
        .reset_index()
    )


# --------------------------------------------------------------------------- #
# 10. 情境分析
# --------------------------------------------------------------------------- #
def scenario_analysis(df: pd.DataFrame, demand_growth=DEMAND_GROWTH, lead_time_growth=LEAD_TIME_GROWTH):
    base = df[["sku", "warehouse", "inventory", "avg_daily_demand_7d", "lead_time"]]
    rows = []
    for dg in demand_growth:
        for lg in lead_time_growth:
            temp = base.copy()
            scen_demand = temp["avg_daily_demand_7d"] * (1 + dg)
            temp["scenario_dos"] = temp["inventory"] / scen_demand.replace(0, np.nan)
            temp["scenario_lt"] = temp["lead_time"] * (1 + lg)
            valid = temp["scenario_dos"].notna() & temp["scenario_lt"].notna()
            temp["scenario_shortfall"] = np.where(valid, temp["scenario_dos"] < temp["scenario_lt"], np.nan)

            by_pair = (
                temp.groupby(["sku", "warehouse"])
                .agg(
                    scenario_shortfall_rate=("scenario_shortfall", "mean"),
                    valid_observations=("scenario_shortfall", "count"),
                )
                .reset_index()
            )
            by_pair["demand_growth"] = dg
            by_pair["lead_time_growth"] = lg
            rows.append(by_pair)

    detail = pd.concat(rows, ignore_index=True)
    summary = (
        detail.groupby(["demand_growth", "lead_time_growth"])
        .agg(
            sku_warehouse_pairs=("scenario_shortfall_rate", "count"),
            avg_shortfall_rate=("scenario_shortfall_rate", "mean"),
            median_shortfall_rate=("scenario_shortfall_rate", "median"),
            max_shortfall_rate=("scenario_shortfall_rate", "max"),
        )
        .reset_index()
    )
    return detail, summary


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def run_all(csv_path) -> PipelineResult:
    raw = load_raw(csv_path)
    df = engineer_features(standardize(raw))
    sku_kpi, supplier_kpi, warehouse_kpi = build_kpis(df)
    sku_abc, abc_summary = abc_analysis(df)
    risk, thresholds = risk_analysis(df, sku_abc)
    stockout_by_risk = validate_against_stockout(df, risk)
    scen_detail, scen_summary = scenario_analysis(df)

    meta = {
        "rows": int(len(df)),
        "date_min": str(df["date"].min().date()),
        "date_max": str(df["date"].max().date()),
        "n_sku": int(df["sku"].nunique()),
        "n_warehouse": int(df["warehouse"].nunique()),
        "n_supplier": int(df["supplier"].nunique()),
        "n_pairs": int(len(risk)),
        "stockout_unique_values": int(df["stockout"].nunique(dropna=True)),
        "overall_stockout_rate": float(df["stockout"].mean()),
        "overall_below_rop_rate": float(df["below_rop"].mean()),
        "avg_inventory_value_per_obs": float(df["inventory_value"].mean()),
        "source_file": str(getattr(csv_path, "name", csv_path)).split("/")[-1],
    }
    return PipelineResult(
        daily=df, sku_kpi=sku_kpi, supplier_kpi=supplier_kpi, warehouse_kpi=warehouse_kpi,
        sku_abc=sku_abc, abc_summary=abc_summary, sku_wh_risk=risk,
        stockout_by_risk=stockout_by_risk, scenario_detail=scen_detail,
        scenario_summary=scen_summary, thresholds=thresholds, meta=meta,
    )
