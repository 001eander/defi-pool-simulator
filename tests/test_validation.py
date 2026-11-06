"""可复现校验入口与共同随机数灵敏度实验测试。"""

from pathlib import Path

import pandas as pd

from defi_pool_simulator.validation import run_extreme_checks, write_validation_outputs


def test_all_extreme_checks_pass() -> None:
    checks = run_extreme_checks()

    assert len(checks) == 10
    assert checks["passed"].all()


def test_validation_outputs_and_deterministic_sensitivity_responses(tmp_path: Path) -> None:
    checks, sensitivity = write_validation_outputs(tmp_path, replications=2, seed=11)

    assert checks["passed"].all()
    assert len(sensitivity.summary) == 8 * 8
    zero_fee = sensitivity.runs[
        (sensitivity.runs["factor"] == "fee_rate") & (sensitivity.runs["level"] == 0.0)
    ]
    zero_sigma = sensitivity.runs[
        (sensitivity.runs["factor"] == "price_sigma") & (sensitivity.runs["level"] == 0.0)
    ]
    assert zero_fee["total_fee_b"].eq(0.0).all()
    assert zero_sigma["final_impermanent_loss_pct"].eq(0.0).all()
    assert zero_sigma["final_impermanent_loss_b"].eq(0.0).all()

    for (_, _), group in sensitivity.runs.groupby(["factor", "level"]):
        assert group["seed"].tolist() == [11, 12]

    assert (tmp_path / "extreme_values.csv").exists()
    assert (tmp_path / "sensitivity_runs.csv").exists()
    assert (tmp_path / "sensitivity_summary.csv").exists()
    assert (tmp_path / "sensitivity_response.png").stat().st_size > 0
    saved = pd.read_csv(tmp_path / "sensitivity_summary.csv")
    baseline_rows = saved[(saved["factor"] == "fee_rate") & (saved["level"] == 0.003)]
    assert baseline_rows["delta_mean"].eq(0.0).all()
