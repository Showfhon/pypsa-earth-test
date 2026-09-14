# -*- coding: utf-8 -*-
"""Regression test for the operational-reserve capacity constraint alignment.

``update_capacity_constraint`` builds its right-hand side as a pandas DataFrame
ordered like ``n.generators.index`` while linopy aligns by position against the
left-hand side expression's own ``Generator`` coordinate. When those orders
differ the fixed generators receive the extendable generators' zero rhs, and any
must-run unit (``p_min_pu`` > 0) becomes infeasible.

Adding load shedding generators is what makes the two orders diverge, so the
test only bites with ``load_shedding`` and ``operational_reserve`` both active.

Usage (from the repo root):
    python scripts/non_workflow/test_reserve_alignment.py \
        networks/KR2036_kwak_full_10n3h/elec_s_10_ec_lcopt_Co2L-CCL-3H.nc \
        config.KR2036_kwak_full_10n3h.yaml

Exits non-zero if the rhs is misaligned or the small instance is infeasible.
"""
import sys
import types
import warnings
from pathlib import Path

import pandas as pd
import pypsa
import yaml

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import solve_network as sn
from pypsa.descriptors import get_switchable_as_dense as get_as_dense

N_SNAPSHOTS = 8


def build(network_path, config):
    n = pypsa.Network(network_path)
    n.set_snapshots(n.snapshots[:N_SNAPSHOTS])
    n.snapshot_weightings.loc[:, :] = 3.0
    # an annual CO2 cap is meaningless on a few snapshots
    n.global_constraints = n.global_constraints.iloc[0:0]
    return sn.prepare_network(n, dict(config["solving"]["options"]), config)


def main(network_path, config_path):
    config = yaml.safe_load(open(config_path))
    config["electricity"]["operational_reserve"]["activate"] = True
    if not config["solving"]["options"].get("load_shedding"):
        config["solving"]["options"]["load_shedding"] = 10
    sn.snakemake = types.SimpleNamespace(config=config)

    failures = []

    n = build(network_path, config)
    n_shed = int((n.generators.carrier == "load shedding").sum())
    if n_shed == 0:
        failures.append("no load shedding generators were added; test is not meaningful")

    n.optimize.create_model()
    sn.add_operational_reserve_margin(n, n.snapshots, config)

    constraint = n.model.constraints["gen_updated_capacity_constraint"]
    snapshot = n.snapshots[0]
    p_max_pu = get_as_dense(n, "Generator", "p_max_pu")
    fix_i = n.generators.query("not p_nom_extendable").index
    expected = p_max_pu.loc[snapshot, fix_i] * n.generators.p_nom[fix_i]
    actual = pd.Series(
        {
            name: float(constraint.sel(snapshot=snapshot, Generator=name).rhs.values)
            for name in fix_i
        }
    )
    wrong = (actual - expected).abs() > 1e-6
    print(f"load shedding generators : {n_shed}")
    print(f"fixed generators         : {len(fix_i)}")
    print(f"misaligned rhs           : {int(wrong.sum())}")
    if wrong.any():
        failures.append(f"{int(wrong.sum())}/{len(fix_i)} fixed generators have a misaligned rhs")
        for name in expected.index[wrong][:5]:
            print(f"  {name}: rhs={actual[name]:.3f} expected={expected[name]:.3f}")

    n2 = build(network_path, config)

    def extra(network, snapshots):
        sn.add_CCL_constraints(network, config)
        sn.add_operational_reserve_margin(network, snapshots, config)

    _, condition = n2.optimize(
        solver_name="highs",
        extra_functionality=extra,
        solver_options={"solver": "ipm", "threads": 1, "output_flag": False},
    )
    print(f"{N_SNAPSHOTS}-snapshot solve    : {condition}")
    if condition != "optimal":
        failures.append(f"small instance did not solve to optimality: {condition}")

    if failures:
        print("\nFAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
