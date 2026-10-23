"""单次仿真的结果记录与汇总。"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import pandas as pd

from .amm import AddLiquidityResult, LiquidityPool, RemoveLiquidityResult, impermanent_loss_pct
from .parameters import SimulationParameters, TradeType


@dataclass(frozen=True, eq=False)
class SimulationResult:
    """一次重复仿真的标量结果与小时快照。"""

    seed: int
    total_orders: int
    filled_orders: int
    failed_inventory: int
    failed_slippage: int
    orders_by_type: dict[str, int]
    filled_by_type: dict[str, int]
    failed_inventory_by_type: dict[str, int]
    failed_slippage_by_type: dict[str, int]
    avg_slippage_by_type: dict[str, float]
    total_volume_a: float
    total_fee_b: float
    lp_add_count: int
    lp_remove_count: int
    lp_skipped_count: int
    lp_remove_shortfall_a: float
    final_reserve_a: float
    final_reserve_b: float
    final_pool_price: float
    final_external_price: float
    final_lp_shares: float
    final_pool_value_b: float
    final_impermanent_loss_pct: float
    final_impermanent_loss_b: float
    final_lp_net_income_b: float
    snapshots: pd.DataFrame = field(repr=False, compare=False)

    @property
    def failed_orders(self) -> int:
        return self.failed_inventory + self.failed_slippage

    @property
    def failure_rate(self) -> float:
        return self.failed_orders / self.total_orders if self.total_orders else 0.0


class MetricsRecorder:
    """按事件累计交易、LP 操作与小时快照。"""

    def __init__(self) -> None:
        self.total_orders = 0
        self.filled_orders = 0
        self.failed_inventory = 0
        self.failed_slippage = 0
        self.orders_by_type: Counter[str] = Counter()
        self.filled_by_type: Counter[str] = Counter()
        self.failed_inventory_by_type: Counter[str] = Counter()
        self.failed_slippage_by_type: Counter[str] = Counter()
        self.slippage_sum_by_type: defaultdict[str, float] = defaultdict(float)
        self.slippage_count_by_type: Counter[str] = Counter()
        self.total_volume_a = 0.0
        self.lp_add_count = 0
        self.lp_remove_count = 0
        self.lp_skipped_count = 0
        self.lp_remove_shortfall_a = 0.0
        self.snapshots: list[dict[str, float]] = []

    def record_order(self, trade_type: TradeType) -> None:
        self.total_orders += 1
        self.orders_by_type[trade_type.code] += 1

    def record_fill(self, trade_type: TradeType, volume_a: float) -> None:
        self.filled_orders += 1
        self.filled_by_type[trade_type.code] += 1
        self.total_volume_a += volume_a

    def record_inventory_failure(self, trade_type: TradeType) -> None:
        self.failed_inventory += 1
        self.failed_inventory_by_type[trade_type.code] += 1

    def record_slippage_failure(self, trade_type: TradeType) -> None:
        self.failed_slippage += 1
        self.failed_slippage_by_type[trade_type.code] += 1

    def record_slippage(self, trade_type: TradeType, slippage: float) -> None:
        """记录所有进入定价环节的滑点，无论最终成交与否。"""
        self.slippage_sum_by_type[trade_type.code] += slippage
        self.slippage_count_by_type[trade_type.code] += 1

    def record_lp_add(self, result: AddLiquidityResult) -> None:
        if result.skipped:
            self.lp_skipped_count += 1
            return
        self.lp_add_count += 1

    def record_lp_remove(self, result: RemoveLiquidityResult) -> None:
        if result.skipped:
            self.lp_skipped_count += 1
        else:
            self.lp_remove_count += 1
        self.lp_remove_shortfall_a += result.shortfall_a

    def record_snapshot(
        self,
        time_h: float,
        pool: LiquidityPool,
        external_price: float,
        initial_external_price: float,
    ) -> None:
        price_ratio = external_price / initial_external_price
        loss_pct = impermanent_loss_pct(price_ratio)
        pool_value_b = pool.total_value_b(external_price)
        loss_b = loss_pct * pool_value_b
        self.snapshots.append(
            {
                "time_h": time_h,
                "reserve_a": pool.reserve_a,
                "reserve_b": pool.reserve_b,
                "pool_price": pool.spot_price,
                "external_price": external_price,
                "price_ratio": price_ratio,
                "lp_shares": pool.total_shares,
                "cumulative_fee_b": pool.cumulative_fee_b,
                "cumulative_volume_a": self.total_volume_a,
                "impermanent_loss_pct": loss_pct,
                "impermanent_loss_b": loss_b,
                "lp_net_income_b": pool.cumulative_fee_b - loss_b,
                "depth_a": pool.depth_a(external_price),
                "total_orders": float(self.total_orders),
                "filled_orders": float(self.filled_orders),
                "failed_orders": float(self.failed_inventory + self.failed_slippage),
            }
        )

    def build_result(
        self, seed: int, pool: LiquidityPool, params: SimulationParameters
    ) -> SimulationResult:
        coded_types = [t.code for t in params.trade_types]
        avg_slippage: dict[str, float] = {}
        for code in coded_types:
            count = self.slippage_count_by_type[code]
            avg_slippage[code] = self.slippage_sum_by_type[code] / count if count else math.nan
        last = self.snapshots[-1]
        return SimulationResult(
            seed=seed,
            total_orders=self.total_orders,
            filled_orders=self.filled_orders,
            failed_inventory=self.failed_inventory,
            failed_slippage=self.failed_slippage,
            orders_by_type={code: self.orders_by_type[code] for code in coded_types},
            filled_by_type={code: self.filled_by_type[code] for code in coded_types},
            failed_inventory_by_type={
                code: self.failed_inventory_by_type[code] for code in coded_types
            },
            failed_slippage_by_type={
                code: self.failed_slippage_by_type[code] for code in coded_types
            },
            avg_slippage_by_type=avg_slippage,
            total_volume_a=self.total_volume_a,
            total_fee_b=pool.cumulative_fee_b,
            lp_add_count=self.lp_add_count,
            lp_remove_count=self.lp_remove_count,
            lp_skipped_count=self.lp_skipped_count,
            lp_remove_shortfall_a=self.lp_remove_shortfall_a,
            final_reserve_a=pool.reserve_a,
            final_reserve_b=pool.reserve_b,
            final_pool_price=pool.spot_price,
            final_external_price=last["external_price"],
            final_lp_shares=pool.total_shares,
            final_pool_value_b=last["reserve_a"] * last["external_price"] + last["reserve_b"],
            final_impermanent_loss_pct=last["impermanent_loss_pct"],
            final_impermanent_loss_b=last["impermanent_loss_b"],
            final_lp_net_income_b=last["lp_net_income_b"],
            snapshots=pd.DataFrame(self.snapshots),
        )
