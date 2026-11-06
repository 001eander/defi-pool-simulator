"""AMM 极端值、储备边界与确定性响应测试。"""

import pytest

from defi_pool_simulator.amm import Direction, LiquidityPool, impermanent_loss_pct
from defi_pool_simulator.metrics import MetricsRecorder
from defi_pool_simulator.model import execute_trade, run_once
from defi_pool_simulator.parameters import SimulationParameters, TradeType


def make_pool(fee_rate: float = 0.003) -> LiquidityPool:
    return LiquidityPool(1_000_000.0, 2_000_000.0, fee_rate, 100.0)


def test_near_zero_zero_fee_swap_preserves_spot_price_and_product() -> None:
    pool = make_pool(fee_rate=0.0)
    product_before = pool.reserve_a * pool.reserve_b

    quote = pool.quote(Direction.A_TO_B, 1e-9)
    pool.settle(quote)

    assert quote.execution_price == pytest.approx(quote.spot_price_before, rel=1e-12)
    assert quote.slippage == pytest.approx(0.0, abs=1e-12)
    assert pool.reserve_a * pool.reserve_b == pytest.approx(product_before, rel=1e-12)


def test_large_input_is_bounded_by_output_formula_not_input_reserve() -> None:
    pool = make_pool()

    quote = pool.quote(Direction.A_TO_B, 5_000_000.0)

    assert quote.amount_in > pool.reserve_a
    assert 0.0 < quote.amount_out < pool.reserve_b
    pool.settle(quote)
    assert pool.reserve_a > 1_000_000.0
    assert pool.reserve_b > 0.0


def test_maximum_case_large_trade_exceeds_five_percent_tolerance() -> None:
    pool = make_pool()
    recorder = MetricsRecorder()
    trade_type = TradeType("large", "大额", 1.0, 50_000.0, 50_000.0, 0.05)

    execute_trade(pool, recorder, trade_type, Direction.A_TO_B, 50_000.0)

    expected_slippage = 1.0 - 0.997 * 1_000_000.0 / (1_000_000.0 + 0.997 * 50_000.0)
    assert recorder.slippage_sum_by_type["large"] == pytest.approx(expected_slippage)
    assert recorder.failed_slippage == 1
    assert recorder.failed_reserves == 0
    assert recorder.filled_orders == 0


def test_slippage_equal_to_tolerance_is_accepted() -> None:
    pool = make_pool()
    quoted = pool.quote(Direction.A_TO_B, 1_000.0)
    recorder = MetricsRecorder()
    trade_type = TradeType(
        "boundary",
        "边界",
        1.0,
        1_000.0,
        1_000.0,
        quoted.slippage,
    )

    execute_trade(pool, recorder, trade_type, Direction.A_TO_B, 1_000.0)

    assert quoted.slippage == pytest.approx(trade_type.slippage_tolerance)
    assert recorder.filled_orders == 1
    assert recorder.failed_reserves + recorder.failed_slippage == 0


def test_drained_pool_records_reserve_failure_without_changing_state() -> None:
    pool = make_pool()
    pool.remove_liquidity(5_000_000.0)
    recorder = MetricsRecorder()
    trade_type = TradeType("unit", "单位", 1.0, 100.0, 100.0, 0.01)

    execute_trade(pool, recorder, trade_type, Direction.A_TO_B, 100.0)

    assert recorder.failed_reserves == 1
    assert recorder.failed_slippage == 0
    assert recorder.filled_orders == 0
    assert pool.reserve_a == 0.0
    assert pool.reserve_b == 0.0


def test_zero_price_sigma_keeps_external_price_and_loss_unchanged() -> None:
    result = run_once(SimulationParameters(duration_hours=24.0, price_sigma=0.0), seed=5)

    assert result.snapshots["external_price"].eq(2.0).all()
    assert result.snapshots["price_ratio"].eq(1.0).all()
    assert result.snapshots["impermanent_loss_pct"].eq(0.0).all()
    assert result.final_impermanent_loss_b == 0.0


def test_impermanent_loss_approaches_one_at_price_extremes() -> None:
    assert impermanent_loss_pct(1e-12) >= 0.999_998
    assert impermanent_loss_pct(1e12) >= 0.999_998
    assert impermanent_loss_pct(1e-12) < 1.0
    assert impermanent_loss_pct(1e12) < 1.0


def test_trade_sizes_are_discrete_and_average_slippage_is_weighted() -> None:
    result = run_once(SimulationParameters(duration_hours=24.0), seed=5)

    assert result.total_volume_a == pytest.approx(round(result.total_volume_a))
    quoted_count = result.total_orders - result.failed_reserves
    expected = (
        sum(
            result.avg_slippage_by_type[code]
            * (result.orders_by_type[code] - result.failed_reserves_by_type[code])
            for code in result.orders_by_type
        )
        / quoted_count
    )
    assert result.avg_slippage == pytest.approx(expected)
