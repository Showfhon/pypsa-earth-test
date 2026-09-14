# Operational reserve makes must-run generators infeasible when load shedding is enabled

Draft text for a PyPSA-Earth GitHub issue. Not yet submitted.

---

## Summary

`update_capacity_constraint()` in `scripts/solve_network.py` builds the right-hand
side of `gen_updated_capacity_constraint` in a different generator order than the
left-hand side expression. Because linopy aligns by position rather than by label,
the right-hand side values land on the wrong generators: non-extendable generators
receive the extendable generators' `fill_value=0`. Any non-extendable generator with
`p_min_pu > 0` then gets the contradictory pair `p >= p_min_pu * p_nom` and
`p + r <= 0`, and the model is reported infeasible during presolve.

This only surfaces when `electricity: operational_reserve: activate: true` **and**
`solving: options: load_shedding` are both set. Adding the load shedding generators
is what makes the two orderings diverge; without them the orders happen to coincide
and the bug is invisible.

## Affected code

`scripts/solve_network.py`, `update_capacity_constraint()`:

```python
lhs = dispatch + reserve
if not ext_i.empty:
    capacity_variable = n.model["Generator-p_nom"].rename({"Generator-ext": "Generator"})
    lhs = dispatch + reserve - capacity_variable * xr.DataArray(p_max_pu[ext_i])

rhs = (p_max_pu[fix_i] * capacity_fixed).reindex(columns=gen_i, fill_value=0)

n.model.add_constraints(lhs <= rhs, name="gen_updated_capacity_constraint")
```

`rhs` is ordered like `n.generators.index`, while `lhs` carries its own `Generator`
coordinate whose order differs once the generator set changes.

Interestingly, `add_CCL_constraints()` in the same file already documents this exact
hazard in its docstring ("the grouper is built from the model's 'Generator-ext'
coordinate because linopy >= 0.3.9 aligns groupers by position and refuses to
reindex"), so the pitfall is known — `update_capacity_constraint()` was just not
covered.

## How to reproduce

Any network with a non-extendable generator carrying `p_min_pu > 0`, solved with:

```yaml
electricity:
  operational_reserve:
    activate: true
    epsilon_load: 0.02
    epsilon_vres: 0.01
    contingency: 0
solving:
  options:
    load_shedding: 10
```

In our case (Korea, 10 clusters, 3-hourly, 2920 snapshots) the coal fleet is
non-extendable with `p_min_pu = 0.357`. HiGHS reports:

```
Presolving model
Problem status detected on presolve: Infeasible
```

## Evidence

Gurobi's IIS on a reduced two-snapshot instance returns exactly two constraints
and one bound:

```
Generator-fix-p-lower            (2018-01-01 00:00, KR0 1 coal)
gen_updated_capacity_constraint  (2018-01-01 00:00, KR0 1 coal)
```

Inspecting that generator and the constraint row that was built for it:

| quantity | value |
| --- | --- |
| `p_nom` / `p_min_pu` / `p_max_pu` | 120.073 MW / 0.357 / 1.0 |
| `Generator-fix-p-lower` requires | `p >= 42.866` |
| `gen_updated_capacity_constraint` as built | `p + r <= -0.0` |
| correct rhs (`p_max_pu * p_nom`) | `120.073` |

Across the whole instance, 23 of 24 non-extendable generators received a wrong
right-hand side; 5 of them (the coal units, which are the ones with `p_min_pu > 0`)
became outright contradictory. Removing the load shedding generators drops this to
0 of 14 and the model solves.

Isolation, on an 8-snapshot instance:

| configuration | result |
| --- | --- |
| reserve + load shedding | infeasible |
| reserve disabled | optimal |
| load shedding disabled | optimal |
| `clip_p_max_pu` disabled | still infeasible |
| CCL constraints disabled | still infeasible |

## Proposed fix

Reindex the right-hand side onto the left-hand side's own generator order before
adding the constraint:

```diff
     rhs = (p_max_pu[fix_i] * capacity_fixed).reindex(columns=gen_i, fill_value=0)
+    # linopy aligns by position, not by label, so the rhs has to carry the same
+    # generator order as the lhs expression. Without this the fixed generators
+    # receive the extendable generators' zero rhs and a must-run unit whose
+    # p_min_pu is positive becomes infeasible.
+    rhs = rhs.reindex(columns=lhs.indexes["Generator"], fill_value=0)
 
     n.model.add_constraints(lhs <= rhs, name="gen_updated_capacity_constraint")
```

After the change, the misaligned right-hand sides drop from 23/24 to 0/24 and the
same instance solves to optimality. A regression check is included at
`scripts/non_workflow/test_reserve_alignment.py`.

Because the constraint is only created when `operational_reserve` is active, the fix
cannot change results for any run that had the reserve disabled.

## Environment

| component | version |
| --- | --- |
| PyPSA-Earth | 0.9.0 (`scripts/solve_network.py` at upstream commit `aab8892`) |
| PyPSA | 0.30.3 |
| linopy | 0.5.8 |
| xarray | 2025.1.2 |
| pandas | 2.3.3 |
| Snakemake | 7.32.4 |
| HiGHS | 1.15.1 |
