"""仿真事件逻辑、重复运行与结果输出测试。"""

import math
from pathlib import Path

import pandas as pd
import pytest

from defi_pool_simulator.amm import Direction, LiquidityPool
from defi_pool_simulator.metrics import MetricsRecorder
from defi_pool_simulator.model import execute_trade, run_once
from defi_pool_simulator.parameters import SimulationParameters, TradeType
from defi_pool_simulator.runner import run_replications, write_outputs


def make_pool() -> LiquidityPool:
    return LiquidityPool(1_000_000.0, 2_000_000.0, 0.003, 100.0)


def test_b_to_a_order_uses_a_equivalent_size() -> None:
    pool = make_pool()
    recorder = MetricsRecorder()
    trade_type = TradeType("unit", "单位", 1.0, 100.0, 100.0, 0.01)

    execute_trade(pool, recorder, trade_type, Direction.B_TO_A, 100.0)

    assert recorder.filled_orders == 1
    assert recorder.total_volume_a == pytest.approx(100.0)
    assert pool.reserve_a < 1_000_000.0
    assert pool.reserve_b > 2_000_000.0


def test_inventory_failure_leaves_pool_unchanged() -> None:
    pool = make_pool()
    recorder = MetricsRecorder()
    trade_type = TradeType("huge", "巨额", 1.0, 5_000_000.0, 5_000_000.0, 0.05)

    execute_trade(pool, recorder, trade_type, Direction.A_TO_B, 5_000_000.0)

    assert recorder.failed_inventory == 1
    assert recorder.failed_slippage == 0
    assert recorder.filled_orders == 0
    assert pool.reserve_a == 1_000_000.0
    assert pool.reserve_b == 2_000_000.0


def test_slippage_failure_leaves_pool_unchanged() -> None:
    pool = make_pool()
    recorder = MetricsRecorder()
    trade_type = TradeType("large", "大额", 1.0, 500_000.0, 500_000.0, 0.001)

    execute_trade(pool, recorder, trade_type, Direction.A_TO_B, 500_000.0)

    assert recorder.failed_inventory == 0
    assert recorder.failed_slippage == 1
    assert recorder.filled_orders == 0
    assert recorder.slippage_sum_by_type["large"] > 0.001
    assert pool.reserve_a == 1_000_000.0
    assert pool.reserve_b == 2_000_000.0


def test_successful_trade_updates_reserves_and_volume() -> None:
    pool = make_pool()
    recorder = MetricsRecorder()
    trade_type = TradeType("small", "小额", 1.0, 100.0, 100.0, 0.01)

    execute_trade(pool, recorder, trade_type, Direction.A_TO_B, 100.0)

    assert recorder.filled_orders == 1
    assert recorder.total_volume_a == pytest.approx(100.0)
    assert pool.reserve_a == pytest.approx(1_000_100.0)
    assert pool.reserve_b < 2_000_000.0
    assert pool.cumulative_fee_b > 0.0


def test_every_order_has_exactly_one_outcome() -> None:
    result = run_once(SimulationParameters(duration_hours=48.0), seed=7)

    assert result.filled_orders + result.failed_orders == result.total_orders
    assert sum(result.orders_by_type.values()) == result.total_orders
    assert sum(result.filled_by_type.values()) == result.filled_orders
    assert sum(result.failed_inventory_by_type.values()) == result.failed_inventory
    assert sum(result.failed_slippage_by_type.values()) == result.failed_slippage


def test_hourly_snapshots_cover_the_full_horizon() -> None:
    result = run_once(SimulationParameters(duration_hours=48.0), seed=7)

    assert result.snapshots["time_h"].tolist() == [float(i) for i in range(49)]
    assert (result.snapshots[["reserve_a", "reserve_b", "lp_shares"]] >= 0.0).all().all()
    assert (result.snapshots["impermanent_loss_pct"] >= 0.0).all()
    assert result.snapshots["external_price"].nunique() > 1


def test_snapshot_uses_external_price_for_loss_and_depth() -> None:
    pool = make_pool()
    recorder = MetricsRecorder()

    recorder.record_snapshot(1.0, pool, external_price=4.0, initial_external_price=2.0)

    row = recorder.snapshots[-1]
    expected_loss = 1.0 - 2.0 * math.sqrt(2.0) / 3.0
    assert row["impermanent_loss_pct"] == pytest.approx(expected_loss)
    assert row["impermanent_loss_b"] == pytest.approx(expected_loss * 6_000_000.0)
    assert row["lp_net_income_b"] == pytest.approx(-row["impermanent_loss_b"])
    assert row["depth_a"] == pytest.approx(1_500_000.0)


def test_same_seed_reproduces_the_run() -> None:
    params = SimulationParameters(duration_hours=24.0)
    first = run_once(params, seed=123)
    second = run_once(params, seed=123)
    other = run_once(params, seed=124)

    assert first.snapshots.equals(second.snapshots)
    assert first.total_volume_a == second.total_volume_a
    assert first.total_volume_a != other.total_volume_a


def test_lp_add_only_scenario_grows_the_pool_at_stable_price() -> None:
    params = SimulationParameters(
        duration_hours=10.0,
        trade_arrival_mean_hours=1e9,
        lp_add_mean_hours=2.0,
        lp_remove_mean_hours=1e9,
        price_sigma=0.0,
    )

    result = run_once(params, seed=5)

    assert result.total_orders == 0
    assert result.lp_add_count > 0
    assert result.final_reserve_a > params.initial_reserve_a
    assert result.final_reserve_b > params.initial_reserve_b
    assert result.final_lp_shares > params.initial_lp_shares
    assert result.final_pool_price == pytest.approx(2.0)
    assert result.total_fee_b == 0.0
    assert result.final_impermanent_loss_pct == pytest.approx(0.0)


def test_lp_remove_only_scenario_records_shortfall_and_stops_at_zero() -> None:
    params = SimulationParameters(
        duration_hours=168.0,
        trade_arrival_mean_hours=1e9,
        lp_add_mean_hours=1e9,
        lp_remove_mean_hours=3.0,
        price_sigma=0.0,
    )

    result = run_once(params, seed=5)

    assert result.lp_remove_count > 0
    assert result.lp_remove_shortfall_a > 0.0
    assert result.lp_skipped_count > 0
    assert result.final_reserve_a == 0.0
    assert result.final_reserve_b == 0.0
    assert result.final_lp_shares == 0.0
    assert (result.snapshots[["reserve_a", "reserve_b", "lp_shares"]] >= 0.0).all().all()


def test_replications_are_summarized_and_written(tmp_path: Path) -> None:
    params = SimulationParameters(duration_hours=12.0)
    aggregate = run_replications(params, replications=3, seed=11)

    assert len(aggregate.runs) == 3
    assert aggregate.summary.loc["total_orders", "count"] == 3.0
    assert "ci95" in aggregate.summary.columns

    write_outputs(aggregate, tmp_path)

    assert (tmp_path / "replications.csv").exists()
    assert (tmp_path / "summary.csv").exists()
    snapshots = tmp_path / "snapshots.csv"
    assert snapshots.exists()
    frame = pd.read_csv(snapshots)
    assert len(frame) == 3 * 13
    assert sorted(frame["replication"].unique()) == [1, 2, 3]
