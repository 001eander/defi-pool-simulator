"""极端值校验、单因素灵敏度实验与响应图输出。"""

from __future__ import annotations

import argparse
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .amm import Direction, LiquidityPool, impermanent_loss_pct
from .metrics import MetricsRecorder
from .model import execute_trade, run_once
from .parameters import SimulationParameters, TradeType, default_trade_types
from .runner import run_replications, scalar_metrics


@dataclass(frozen=True)
class CheckRecord:
    scenario: str
    variable: str
    expected: str
    actual: str
    passed: bool


@dataclass(frozen=True)
class SensitivityScenario:
    factor: str
    level: float
    parameters: SimulationParameters


@dataclass(frozen=True, eq=False)
class SensitivityResult:
    runs: pd.DataFrame = field(repr=False, compare=False)
    summary: pd.DataFrame = field(repr=False, compare=False)


SENSITIVITY_METRICS = (
    "total_volume_a",
    "total_fee_b",
    "avg_slippage_all",
    "avg_slippage_large",
    "failure_rate",
    "final_impermanent_loss_pct",
    "final_impermanent_loss_b",
    "final_lp_net_income_b",
)


def _pool(fee_rate: float = 0.003) -> LiquidityPool:
    return LiquidityPool(1_000_000.0, 2_000_000.0, fee_rate, 100.0)


def run_extreme_checks() -> pd.DataFrame:
    """执行有明确解析预期的极端值检查，返回逐项实际结果。"""
    records: list[CheckRecord] = []

    pool = _pool(fee_rate=0.0)
    product_before = pool.reserve_a * pool.reserve_b
    quote = pool.quote(Direction.A_TO_B, 1e-9)
    pool.settle(quote)
    near_zero_ok = (
        math.isclose(quote.execution_price, quote.spot_price_before, rel_tol=1e-12)
        and math.isclose(quote.slippage, 0.0, abs_tol=1e-12)
        and math.isclose(pool.reserve_a * pool.reserve_b, product_before, rel_tol=1e-12)
    )
    records.append(
        CheckRecord(
            "趋近零交易、零手续费",
            "输入量=1e-9 A，fee=0",
            "成交价趋近即时价，滑点趋近0，乘积不变",
            f"滑点={quote.slippage:.3e}；乘积={pool.reserve_a * pool.reserve_b:.6f}",
            near_zero_ok,
        )
    )

    pool = _pool()
    product_before = pool.reserve_a * pool.reserve_b
    pool.settle(pool.quote(Direction.A_TO_B, 10_000.0))
    product_after = pool.reserve_a * pool.reserve_b
    records.append(
        CheckRecord(
            "正手续费响应",
            "fee=0.003，输入量=10000 A",
            "手续费回流后恒定乘积增加",
            f"交易前={product_before:.2f}；交易后={product_after:.2f}",
            product_after > product_before,
        )
    )

    pool = _pool()
    quote = pool.quote(Direction.A_TO_B, 5_000_000.0)
    large_quote_ok = quote.amount_in > pool.reserve_a and 0.0 < quote.amount_out < pool.reserve_b
    records.append(
        CheckRecord(
            "输入大于输入储备",
            "输入量=5000000 A，当前储备A=1000000",
            "允许报价，输出严格小于输出储备",
            f"输出={quote.amount_out:.6f} B；输出储备={pool.reserve_b:.1f} B",
            large_quote_ok,
        )
    )

    pool = _pool()
    recorder = MetricsRecorder()
    huge = TradeType("huge", "巨额", 1.0, 5_000_000.0, 5_000_000.0, 0.05)
    execute_trade(pool, recorder, huge, Direction.A_TO_B, 5_000_000.0)
    huge_failure_ok = (
        recorder.failed_reserves == 0
        and recorder.failed_slippage == 1
        and pool.reserve_a == 1_000_000.0
        and pool.reserve_b == 2_000_000.0
    )
    records.append(
        CheckRecord(
            "巨额订单滑点放弃",
            "输入量=5000000 A，容忍度=5%",
            "因滑点超限放弃，不误判储备不足，池状态不变",
            f"储备不可用={recorder.failed_reserves}；滑点超限={recorder.failed_slippage}",
            huge_failure_ok,
        )
    )

    pool = _pool()
    quoted = pool.quote(Direction.A_TO_B, 50_000.0)
    expected_max_slippage = 1.0 - 0.997 * 1_000_000.0 / (1_000_000.0 + 0.997 * 50_000.0)
    records.append(
        CheckRecord(
            "案例最大大额交易",
            "输入量=50000 A，fee=0.003",
            "含手续费滑点约5.034%，超过5%容忍度",
            f"滑点={quoted.slippage:.9%}",
            math.isclose(quoted.slippage, expected_max_slippage, rel_tol=1e-12)
            and quoted.slippage > 0.05,
        )
    )

    pool = _pool()
    quoted = pool.quote(Direction.A_TO_B, 1_000.0)
    recorder = MetricsRecorder()
    boundary = TradeType("boundary", "边界", 1.0, 1_000.0, 1_000.0, quoted.slippage)
    execute_trade(pool, recorder, boundary, Direction.A_TO_B, 1_000.0)
    records.append(
        CheckRecord(
            "滑点等于容忍度",
            f"容忍度={quoted.slippage:.9%}",
            "等于阈值时成交",
            f"成交={recorder.filled_orders}；放弃={recorder.failed_reserves + recorder.failed_slippage}",
            recorder.filled_orders == 1
            and recorder.failed_reserves + recorder.failed_slippage == 0,
        )
    )

    zero_sigma = run_once(SimulationParameters(duration_hours=24.0, price_sigma=0.0), seed=5)
    zero_sigma_ok = bool(
        zero_sigma.snapshots["external_price"].eq(2.0).all()
        and zero_sigma.snapshots["impermanent_loss_pct"].eq(0.0).all()
    )
    records.append(
        CheckRecord(
            "零价格波动率",
            "sigma=0，运行24 h",
            "外部参照价格保持2 B/A，无常损失为0",
            f"期末价格={zero_sigma.final_external_price:.2f}；期末无常损失={zero_sigma.final_impermanent_loss_pct:.2%}",
            zero_sigma_ok,
        )
    )

    loss_values = {ratio: impermanent_loss_pct(ratio) for ratio in (1.0, 4.0, 0.25, 1e-12, 1e12)}
    loss_ok = (
        math.isclose(loss_values[1.0], 0.0, abs_tol=1e-15)
        and math.isclose(loss_values[4.0], 0.2, rel_tol=1e-12)
        and math.isclose(loss_values[0.25], 0.2, rel_tol=1e-12)
        and 0.999_998 <= loss_values[1e-12] < 1.0
        and 0.999_998 <= loss_values[1e12] < 1.0
    )
    records.append(
        CheckRecord(
            "无常损失价格极值",
            "价格比=1、4、1/4、1e-12、1e12",
            "损失依次为0、20%、20%，极端价格比趋近100%但不超过",
            "；".join(f"k={ratio:g}: {loss:.6%}" for ratio, loss in loss_values.items()),
            loss_ok,
        )
    )

    pool = _pool()
    removed = pool.remove_liquidity(5_000_000.0)
    add_after_drain = pool.add_liquidity(10_000.0)
    remove_after_drain = pool.remove_liquidity(10_000.0)
    recorder = MetricsRecorder()
    unit = TradeType("unit", "单位", 1.0, 100.0, 100.0, 0.01)
    execute_trade(pool, recorder, unit, Direction.A_TO_B, 100.0)
    drain_ok = (
        removed.amount_a == 1_000_000.0
        and removed.amount_b == 2_000_000.0
        and removed.shortfall_a == 4_000_000.0
        and pool.reserve_a == pool.reserve_b == pool.total_shares == 0.0
        and add_after_drain.skipped
        and remove_after_drain.skipped
        and recorder.failed_reserves == 1
    )
    records.append(
        CheckRecord(
            "超额撤出与空池",
            "申请撤出=5000000 A，当前储备A=1000000",
            "按可用量撤出并记录缺口；后续LP操作跳过，交易记储备不可用",
            f"实际撤出={removed.amount_a:.0f}；缺口={removed.shortfall_a:.0f}；储备不可用={recorder.failed_reserves}",
            drain_ok,
        )
    )

    params = SimulationParameters(duration_hours=24.0)
    first = run_once(params, seed=123)
    second = run_once(params, seed=123)
    outcome_ok = (
        first.filled_orders + first.failed_orders == first.total_orders
        and len(first.snapshots) == 25
        and first.snapshots.equals(second.snapshots)
    )
    records.append(
        CheckRecord(
            "整体守恒与复现",
            "24 h，同种子重复2次",
            "订单去向守恒，25个小时快照，同种子结果一致",
            f"订单={first.total_orders}；成交={first.filled_orders}；放弃={first.failed_orders}；快照={len(first.snapshots)}",
            outcome_ok,
        )
    )

    return pd.DataFrame([asdict(record) for record in records])


def sensitivity_scenarios(
    baseline: SimulationParameters | None = None,
) -> tuple[SensitivityScenario, ...]:
    """返回三组单因素方案，各组均包含基准水平。"""
    base = baseline or SimulationParameters()
    large_share_types = tuple(
        replace(
            trade_type,
            probability={"small": 0.5, "medium": 0.3, "large": 0.2}[trade_type.code],
        )
        for trade_type in default_trade_types()
    )
    return (
        SensitivityScenario("fee_rate", 0.0, replace(base, fee_rate=0.0)),
        SensitivityScenario("fee_rate", 0.003, replace(base, fee_rate=0.003)),
        SensitivityScenario("fee_rate", 0.005, replace(base, fee_rate=0.005)),
        SensitivityScenario("price_sigma", 0.0, replace(base, price_sigma=0.0)),
        SensitivityScenario("price_sigma", 0.02, replace(base, price_sigma=0.02)),
        SensitivityScenario("price_sigma", 0.05, replace(base, price_sigma=0.05)),
        SensitivityScenario("large_share", 0.1, base),
        SensitivityScenario(
            "large_share",
            0.2,
            replace(base, trade_types=large_share_types),
        ),
    )


def run_sensitivity(
    replications: int = 30,
    seed: int = 20261026,
) -> SensitivityResult:
    """用共同随机数运行单因素实验，并计算相对基准的配对差值。"""
    if replications < 1:
        raise ValueError("重复次数至少为 1")
    baseline = SimulationParameters()
    baseline_aggregate = run_replications(baseline, replications=replications, seed=seed)
    baseline_frame = pd.DataFrame(
        [{"seed": run.seed, **scalar_metrics(run)} for run in baseline_aggregate.runs]
    ).set_index("seed")

    run_rows: list[dict[str, float | int | str]] = []
    summary_rows: list[dict[str, float | int | str]] = []
    for scenario in sensitivity_scenarios(baseline):
        aggregate = (
            baseline_aggregate
            if scenario.parameters == baseline
            else run_replications(scenario.parameters, replications=replications, seed=seed)
        )
        scenario_frame = pd.DataFrame(
            [{"seed": run.seed, **scalar_metrics(run)} for run in aggregate.runs]
        ).set_index("seed")
        for run in aggregate.runs:
            run_rows.append(
                {
                    "factor": scenario.factor,
                    "level": scenario.level,
                    "seed": run.seed,
                    **scalar_metrics(run),
                }
            )
        for metric in SENSITIVITY_METRICS:
            scenario_values = scenario_frame[metric].astype(float)
            baseline_values = baseline_frame[metric].astype(float)
            deltas = scenario_values - baseline_values
            count = int(scenario_values.count())
            scenario_std = float(scenario_values.std(ddof=1))
            delta_std = float(deltas.std(ddof=1))
            baseline_mean = float(baseline_values.mean())
            delta_mean = float(deltas.mean())
            summary_rows.append(
                {
                    "factor": scenario.factor,
                    "level": scenario.level,
                    "metric": metric,
                    "replications": count,
                    "baseline_mean": baseline_mean,
                    "scenario_mean": float(scenario_values.mean()),
                    "std": scenario_std,
                    "ci95": 1.96 * scenario_std / math.sqrt(count),
                    "delta_mean": delta_mean,
                    "delta_ci95": 1.96 * delta_std / math.sqrt(count),
                    "delta_pct": (
                        100.0 * delta_mean / abs(baseline_mean)
                        if not math.isclose(baseline_mean, 0.0, abs_tol=1e-15)
                        else math.nan
                    ),
                }
            )

    return SensitivityResult(pd.DataFrame(run_rows), pd.DataFrame(summary_rows))


def write_response_plot(summary: pd.DataFrame, target: str | Path) -> None:
    """绘制三组因素的关键指标均值及95%置信区间。"""
    plt.rcParams["font.sans-serif"] = [
        "PingFang SC",
        "Hiragino Sans GB",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    factors = ("fee_rate", "price_sigma", "large_share")
    factor_titles = ("手续费率", "外部价格波动率", "大额交易占比")
    metrics_by_factor = (
        ("total_volume_a", "total_fee_b", "final_lp_net_income_b", "failure_rate"),
        (
            "final_impermanent_loss_pct",
            "final_impermanent_loss_b",
            "final_lp_net_income_b",
            "failure_rate",
        ),
        ("avg_slippage_all", "avg_slippage_large", "failure_rate", "total_volume_a"),
    )
    metric_titles = {
        "total_volume_a": "总成交量（枚 A）",
        "total_fee_b": "总手续费（枚 B）",
        "final_lp_net_income_b": "LP 净收益（枚 B）",
        "failure_rate": "放弃率（%）",
        "final_impermanent_loss_pct": "无常损失率（%）",
        "final_impermanent_loss_b": "无常损失（枚 B）",
        "avg_slippage_all": "整体平均滑点（%）",
        "avg_slippage_large": "大额平均滑点（%）",
    }
    percentage_metrics = {
        "failure_rate",
        "final_impermanent_loss_pct",
        "avg_slippage_all",
        "avg_slippage_large",
    }

    fig, axes = plt.subplots(3, 4, figsize=(18, 12))
    for row, (factor, factor_title, metrics) in enumerate(
        zip(factors, factor_titles, metrics_by_factor, strict=True)
    ):
        factor_frame = summary[summary["factor"] == factor]
        for col, metric in enumerate(metrics):
            ax = axes[row, col]
            selected = factor_frame[factor_frame["metric"] == metric].sort_values("level")
            scale = 100.0 if metric in percentage_metrics else 1.0
            x = selected["level"].to_numpy(dtype=float) * 100.0
            y = selected["scenario_mean"].to_numpy(dtype=float) * scale
            error = selected["ci95"].to_numpy(dtype=float) * scale
            ax.errorbar(x, y, yerr=error, marker="o", capsize=3, linewidth=1.5)
            ax.set_title(metric_titles[metric])
            ax.set_xlabel(f"{factor_title}（%）")
            ax.grid(alpha=0.25)
    fig.suptitle("单因素参数灵敏度与响应（均值及95%置信区间）", fontsize=16)
    fig.tight_layout()
    fig.savefig(target, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_validation_outputs(
    output_dir: str | Path = "results/validation",
    replications: int = 30,
    seed: int = 20261026,
) -> tuple[pd.DataFrame, SensitivityResult]:
    """运行全部校验并写入 CSV 与响应图。"""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    checks = run_extreme_checks()
    checks.to_csv(target / "extreme_values.csv", index=False, encoding="utf-8-sig")
    sensitivity = run_sensitivity(replications=replications, seed=seed)
    sensitivity.runs.to_csv(target / "sensitivity_runs.csv", index=False, encoding="utf-8-sig")
    sensitivity.summary.to_csv(
        target / "sensitivity_summary.csv", index=False, encoding="utf-8-sig"
    )
    write_response_plot(sensitivity.summary, target / "sensitivity_response.png")
    return checks, sensitivity


def main() -> None:
    parser = argparse.ArgumentParser(description="DeFi 流动性池极端值与参数灵敏度校验")
    parser.add_argument("--replications", type=int, default=30, help="每个方案的重复次数")
    parser.add_argument("--seed", type=int, default=20261026, help="共同基准随机种子")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/validation"),
        help="校验结果输出目录",
    )
    args = parser.parse_args()
    checks, sensitivity = write_validation_outputs(
        output_dir=args.output_dir,
        replications=args.replications,
        seed=args.seed,
    )
    passed = int(checks["passed"].sum())
    print(f"极端值校验：{passed}/{len(checks)} 通过")
    print(f"灵敏度记录：{len(sensitivity.runs)} 行；汇总：{len(sensitivity.summary)} 行")
    print(f"结果目录：{args.output_dir}")
    if passed != len(checks):
        raise RuntimeError("存在未通过的极端值校验，请检查 extreme_values.csv")


if __name__ == "__main__":
    main()
