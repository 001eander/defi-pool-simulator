"""恒定乘积池的定价、滑点、手续费与份额记账测试。"""

import math

import pytest

from defi_pool_simulator.amm import (
    Direction,
    LiquidityPool,
    Token,
    impermanent_loss_pct,
)


def make_pool() -> LiquidityPool:
    return LiquidityPool(
        reserve_a=1_000_000.0,
        reserve_b=2_000_000.0,
        fee_rate=0.003,
        initial_shares=100.0,
    )


def test_swap_follows_constant_product_with_fee() -> None:
    pool = make_pool()
    quote = pool.quote(Direction.A_TO_B, 10_000.0)
    fee = 10_000.0 * 0.003
    expected_out = 2_000_000.0 * (10_000.0 - fee) / (1_000_000.0 + 10_000.0 - fee)

    assert quote.fee == pytest.approx(fee)
    assert quote.amount_out == pytest.approx(expected_out)
    assert quote.spot_price_before == pytest.approx(2.0)
    assert quote.execution_price == pytest.approx(expected_out / 10_000.0)
    assert quote.slippage == pytest.approx(1.0 - quote.execution_price / 2.0)

    invariant_before = pool.reserve_a * pool.reserve_b
    pool.settle(quote)

    assert pool.reserve_a == pytest.approx(1_010_000.0)
    assert pool.reserve_b == pytest.approx(2_000_000.0 - expected_out)
    assert pool.reserve_a * pool.reserve_b > invariant_before
    assert pool.cumulative_fee_b == pytest.approx(fee * 2.0)


def test_same_reserve_fraction_has_similar_slippage_in_both_directions() -> None:
    pool = make_pool()
    a_to_b = pool.quote(Direction.A_TO_B, 10_000.0)
    b_to_a = pool.quote(Direction.B_TO_A, 20_000.0)

    assert a_to_b.slippage == pytest.approx(b_to_a.slippage, abs=1e-3)
    assert a_to_b.slippage > 0.0
    assert b_to_a.slippage > 0.0
    assert a_to_b.execution_price < a_to_b.spot_price_before
    assert b_to_a.execution_price > b_to_a.spot_price_before


def test_slippage_increases_with_order_size() -> None:
    pool = make_pool()
    sizes = (100.0, 1_000.0, 10_000.0, 50_000.0)
    slippages = [pool.quote(Direction.A_TO_B, size).slippage for size in sizes]

    assert slippages == sorted(slippages)
    assert len(set(slippages)) == len(slippages)


def test_inventory_check_uses_input_token_balance() -> None:
    pool = make_pool()

    assert pool.can_fill(Direction.A_TO_B, 1_000_000.0)
    assert not pool.can_fill(Direction.A_TO_B, 1_000_001.0)
    assert pool.can_fill(Direction.B_TO_A, 2_000_000.0)
    assert not pool.can_fill(Direction.B_TO_A, 2_000_001.0)
    assert pool.available(Token.A) == pytest.approx(1_000_000.0)


def test_quote_does_not_change_pool_state() -> None:
    pool = make_pool()
    before = (pool.reserve_a, pool.reserve_b, pool.total_shares, pool.cumulative_fee_b)

    pool.quote(Direction.B_TO_A, 50_000.0)

    assert (pool.reserve_a, pool.reserve_b, pool.total_shares, pool.cumulative_fee_b) == before


def test_add_liquidity_preserves_price_and_mints_proportional_shares() -> None:
    pool = make_pool()

    result = pool.add_liquidity(100_000.0)

    assert result.amount_a == pytest.approx(100_000.0)
    assert result.amount_b == pytest.approx(200_000.0)
    assert result.shares_minted == pytest.approx(10.0)
    assert pool.reserve_a == pytest.approx(1_100_000.0)
    assert pool.reserve_b == pytest.approx(2_200_000.0)
    assert pool.total_shares == pytest.approx(110.0)
    assert pool.spot_price == pytest.approx(2.0)


def test_remove_liquidity_burns_shares_at_pool_ratio() -> None:
    pool = make_pool()

    result = pool.remove_liquidity(50_000.0)

    assert result.amount_a == pytest.approx(50_000.0)
    assert result.amount_b == pytest.approx(100_000.0)
    assert result.shares_burned == pytest.approx(5.0)
    assert result.shortfall_a == pytest.approx(0.0)
    assert pool.total_shares == pytest.approx(95.0)
    assert pool.spot_price == pytest.approx(2.0)


def test_remove_liquidity_executes_partially_when_reserve_is_insufficient() -> None:
    pool = make_pool()

    result = pool.remove_liquidity(5_000_000.0)

    assert result.amount_a == pytest.approx(1_000_000.0)
    assert result.amount_b == pytest.approx(2_000_000.0)
    assert result.shares_burned == pytest.approx(100.0)
    assert result.shortfall_a == pytest.approx(4_000_000.0)
    assert pool.reserve_a == 0.0
    assert pool.reserve_b == 0.0
    assert pool.total_shares == 0.0

    again = pool.remove_liquidity(10_000.0)
    assert again.skipped
    assert again.shortfall_a == pytest.approx(10_000.0)


def test_add_liquidity_is_skipped_after_pool_is_drained() -> None:
    pool = make_pool()
    pool.remove_liquidity(5_000_000.0)

    result = pool.add_liquidity(10_000.0)

    assert result.skipped
    assert pool.reserve_a == 0.0


def test_fee_is_accumulated_in_token_b() -> None:
    pool = make_pool()
    pool.settle(pool.quote(Direction.A_TO_B, 10_000.0))
    fee_after_first = pool.cumulative_fee_b

    pool.settle(pool.quote(Direction.B_TO_A, 20_000.0))

    assert fee_after_first == pytest.approx(60.0)
    assert pool.cumulative_fee_b == pytest.approx(120.0)


def test_impermanent_loss_is_zero_at_parity_and_symmetric() -> None:
    assert impermanent_loss_pct(1.0) == pytest.approx(0.0)
    assert impermanent_loss_pct(4.0) == pytest.approx(0.2)
    assert impermanent_loss_pct(0.25) == pytest.approx(0.2)
    assert impermanent_loss_pct(2.0) == pytest.approx(1.0 - 2.0 * math.sqrt(2.0) / 3.0)


def test_pool_value_and_depth_follow_external_price() -> None:
    pool = make_pool()

    assert pool.total_value_b(3.0) == pytest.approx(5_000_000.0)
    assert pool.depth_a(4.0) == pytest.approx(1_500_000.0)
