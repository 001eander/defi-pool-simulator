"""多次重复仿真、结果汇总与输出。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .metrics import SimulationResult
from .model import run_once
from .parameters import SimulationParameters


@dataclass(frozen=True, eq=False)
class AggregateResult:
    parameters: SimulationParameters
    runs: tuple[SimulationResult, ...]
    summary: pd.DataFrame = field(repr=False, compare=False)


def _scalar_metrics(run: SimulationResult) -> dict[str, float]:
    metrics: dict[str, float] = {
        "total_orders": float(run.total_orders),
        "filled_orders": float(run.filled_orders),
        "failed_orders": float(run.failed_orders),
        "failure_rate": run.failure_rate,
        "failed_inventory": float(run.failed_inventory),
        "failed_slippage": float(run.failed_slippage),
        "total_volume_a": run.total_volume_a,
        "total_fee_b": run.total_fee_b,
        "lp_add_count": float(run.lp_add_count),
        "lp_remove_count": float(run.lp_remove_count),
        "lp_skipped_count": float(run.lp_skipped_count),
        "lp_remove_shortfall_a": run.lp_remove_shortfall_a,
        "final_reserve_a": run.final_reserve_a,
        "final_reserve_b": run.final_reserve_b,
        "final_pool_price": run.final_pool_price,
        "final_external_price": run.final_external_price,
        "final_lp_shares": run.final_lp_shares,
        "final_pool_value_b": run.final_pool_value_b,
        "final_impermanent_loss_pct": run.final_impermanent_loss_pct,
        "final_impermanent_loss_b": run.final_impermanent_loss_b,
        "final_lp_net_income_b": run.final_lp_net_income_b,
    }
    for code in run.orders_by_type:
        metrics[f"orders_{code}"] = float(run.orders_by_type[code])
        metrics[f"filled_{code}"] = float(run.filled_by_type[code])
        metrics[f"failed_{code}"] = float(
            run.failed_inventory_by_type[code] + run.failed_slippage_by_type[code]
        )
        metrics[f"avg_slippage_{code}"] = run.avg_slippage_by_type[code]
    return metrics


def summarize(runs: tuple[SimulationResult, ...]) -> pd.DataFrame:
    frame = pd.DataFrame([_scalar_metrics(run) for run in runs])
    count = frame.count()
    std = frame.std(ddof=1)
    summary = pd.DataFrame(
        {
            "count": count,
            "mean": frame.mean(),
            "std": std,
            "ci95": 1.96 * std / count.pow(0.5),
            "min": frame.min(),
            "max": frame.max(),
        }
    )
    return summary


def run_replications(
    params: SimulationParameters,
    replications: int = 10,
    seed: int = 20261023,
) -> AggregateResult:
    """以连续种子运行多次独立重复仿真。"""
    if replications < 1:
        raise ValueError("重复次数至少为 1")
    runs = tuple(run_once(params, seed + index) for index in range(replications))
    return AggregateResult(parameters=params, runs=runs, summary=summarize(runs))


def write_outputs(aggregate: AggregateResult, output_dir: str | Path) -> None:
    """把重复结果、小时快照与汇总统计写入 CSV。"""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    runs_frame = pd.DataFrame(
        [{"seed": run.seed, **_scalar_metrics(run)} for run in aggregate.runs]
    )
    runs_frame.to_csv(target / "replications.csv", index=False, encoding="utf-8-sig")
    aggregate.summary.to_csv(target / "summary.csv", encoding="utf-8-sig")
    snapshots = pd.concat(
        [run.snapshots.assign(replication=index + 1) for index, run in enumerate(aggregate.runs)],
        ignore_index=True,
    )
    snapshots.to_csv(target / "snapshots.csv", index=False, encoding="utf-8-sig")


def key_means(aggregate: AggregateResult) -> dict[str, float]:
    """供命令行输出的一小组均值指标。"""
    wanted = (
        "total_orders",
        "filled_orders",
        "failure_rate",
        "total_volume_a",
        "total_fee_b",
        "avg_slippage_large",
        "final_impermanent_loss_b",
        "final_lp_net_income_b",
    )
    summary = aggregate.summary
    means = summary["mean"].to_dict()
    return {
        name: float(means[name])
        for name in wanted
        if name in means and not math.isnan(float(means[name]))
    }
