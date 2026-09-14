# -*- coding: utf-8 -*-
"""Regression test for the gated ``electricity: storage_min_total`` constraint.

Checks three things on a small instance:

1. with the config key absent the constraint is not created (no-op),
2. with the key present the constraint exists and the solved total
   ``p_nom_opt`` of that carrier meets the target,
3. the constrained instance still solves.

Usage (from the repo root):
    python scripts/non_workflow/test_storage_min_total.py \
        networks/KR2036_kwak_full_10n3h/elec_s_10_ec_lcopt_Co2L-CCL-3H.nc \
        config.KR2036_kwak_full_10n3h.yaml
"""
import sys
import types
import warnings
from pathlib import Path

import pypsa
import yaml

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import solve_network as sn

N_SNAPSHOTS = 8
CARRIER = "battery"
TARGET = 30090.0


def build(network_path, config):
    n = pypsa.Network(network_path)
    n.set_snapshots(n.snapshots[:N_SNAPSHOTS])
    n.snapshot_weightings.loc[:, :] = 3.0
    n.global_constraints = n.global_constraints.iloc[0:0]
    return sn.prepare_network(n, dict(config["solving"]["options"]), config)


def main(network_path, config_path):
    base = yaml.safe_load(open(config_path))
    sn.snakemake = types.SimpleNamespace(config=base)
    failures = []

    # --- 1. key absent -> no constraint ---
    cfg_off = yaml.safe_load(open(config_path))
    cfg_off["electricity"].pop("storage_min_total", None)
    n_off = build(network_path, cfg_off)
    n_off.optimize.create_model()
    sn.add_storage_min_total_constraints(n_off, cfg_off)
    names_off = [c for c in n_off.model.constraints if c.startswith("storage_min_total")]
    print(f"key absent  -> constraints created: {names_off}")
    if names_off:
        failures.append("constraint was created even though the config key is absent")

    # --- 2 & 3. key present -> constraint exists, target met, still solves ---
    cfg_on = yaml.safe_load(open(config_path))
    cfg_on["electricity"]["storage_min_total"] = {CARRIER: TARGET}
    n_on = build(network_path, cfg_on)
    n_on.optimize.create_model()
    sn.add_storage_min_total_constraints(n_on, cfg_on)
    names_on = [c for c in n_on.model.constraints if c.startswith("storage_min_total")]
    print(f"key present -> constraints created: {names_on}")
    if f"storage_min_total_{CARRIER}" not in names_on:
        failures.append("constraint was not created although the config key is present")

    n_solve = build(network_path, cfg_on)

    def extra(network, snapshots):
        sn.add_CCL_constraints(network, cfg_on)
        sn.add_storage_min_total_constraints(network, cfg_on)

    _, condition = n_solve.optimize(
        solver_name="highs",
        extra_functionality=extra,
        solver_options={"solver": "ipm", "threads": 1, "output_flag": False},
    )
    su = n_solve.storage_units
    built = su[su.carrier == CARRIER].p_nom_opt.sum()
    print(f"{N_SNAPSHOTS}-snapshot solve : {condition}")
    print(f"{CARRIER} p_nom_opt   : {built:,.1f} MW (target {TARGET:,.1f})")
    if condition != "optimal":
        failures.append(f"constrained instance did not solve: {condition}")
    elif built < TARGET - 1.0:
        failures.append(f"target not met: {built:,.1f} < {TARGET:,.1f}")

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
