"""把 PipelineResult 輸出成 CSV 與前端 dashboard 使用的 data.js。"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .pipeline import PipelineResult, RISK_METRIC


def _clean(value):
    """NaN / numpy 型別 -> JSON 可序列化的 Python 型別。"""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        v = float(value)
        return None if math.isnan(v) or math.isinf(v) else round(v, 6)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if value is pd.NA or value is None:
        return None
    return value


def _records(df: pd.DataFrame, cols=None) -> list[dict]:
    if cols:
        df = df[cols]
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def write_csvs(res: PipelineResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    res.sku_kpi.to_csv(out_dir / "sku_kpi.csv", index=False)
    res.supplier_kpi.to_csv(out_dir / "supplier_kpi.csv", index=False)
    res.warehouse_kpi.to_csv(out_dir / "warehouse_kpi.csv", index=False)
    res.sku_abc.to_csv(out_dir / "sku_abc.csv", index=False)
    res.sku_wh_risk.to_csv(out_dir / "sku_warehouse_risk_priority.csv", index=False)
    res.scenario_summary.to_csv(out_dir / "scenario_summary.csv", index=False)
    res.scenario_detail.to_csv(out_dir / "scenario_detail.csv", index=False)


def build_payload(res: PipelineResult) -> dict:
    risk = res.sku_wh_risk
    scen_detail = {}
    for (dg, lg), g in res.scenario_detail.groupby(["demand_growth", "lead_time_growth"]):
        scen_detail[f"{dg:.2f}|{lg:.2f}"] = [
            [r.sku, r.warehouse, _clean(r.scenario_shortfall_rate)] for r in g.itertuples()
        ]

    return {
        "meta": {
            **{k: _clean(v) for k, v in res.meta.items()},
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "p50": _clean(res.thresholds["p50"]),
            "p80": _clean(res.thresholds["p80"]),
        },
        "abc_summary": _records(res.abc_summary),
        "abc_curve": _records(res.sku_abc, ["sku", "annual_consumption_value", "cumulative_value_pct", "abc_class"]),
        "risk": _records(risk, [
            "sku", "warehouse", "abc_class", "risk_level", "action_priority",
            RISK_METRIC, "below_rop_rate", "avg_days_of_supply", "avg_lead_time",
            "days_supply_gap", "avg_forecast_accuracy", "stockout_observations",
            "annual_consumption_value", "avg_inventory_value",
        ]),
        "stockout_by_risk": _records(res.stockout_by_risk),
        "scenario_summary": _records(res.scenario_summary),
        "scenario_detail": scen_detail,
        "supplier_kpi": _records(res.supplier_kpi),
        "warehouse_kpi": _records(res.warehouse_kpi),
    }


def write_dashboard_data(res: PipelineResult, docs_dir: Path) -> Path:
    docs_dir.mkdir(parents=True, exist_ok=True)
    payload = build_payload(res)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    path = docs_dir / "data.js"
    # 用 .js 而非 .json：雙擊 index.html（file://）時瀏覽器不允許 fetch 本機 JSON
    path.write_text(f"window.DASHBOARD_DATA = {text};\n", encoding="utf-8")
    return path
