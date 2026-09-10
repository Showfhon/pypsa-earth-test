# -*- coding: utf-8 -*-
"""求解結果摘要：容量、發電量、碳排、成本。用法: python report_results.py <solved.nc>"""
import sys
import warnings

import pandas as pd
import pypsa

warnings.filterwarnings("ignore")

n = pypsa.Network(sys.argv[1])
w = n.snapshot_weightings.objective

print(f"=== {sys.argv[1]} ===")
print(f"節點 {len(n.buses)} | 快照 {len(n.snapshots)} | 目標函數 {n.objective:.4e}")

gen = pd.DataFrame(
    {
        "p_nom_opt_MW": n.generators.groupby("carrier").p_nom_opt.sum(),
        "p_nom_MW": n.generators.groupby("carrier").p_nom.sum(),
        "發電_TWh": n.generators_t.p.mul(w, axis=0).sum().groupby(n.generators.carrier).sum() / 1e6,
    }
).round(1)
gen["容量因數"] = (gen["發電_TWh"] * 1e6 / (gen["p_nom_opt_MW"] * 8760)).round(3)
print("\n--- 發電機 ---")
print(gen.sort_values("p_nom_opt_MW", ascending=False).to_string())
print(f"\n總發電 {gen['發電_TWh'].sum():.1f} TWh | 總需求 {n.loads_t.p.mul(w, axis=0).sum().sum()/1e6:.1f} TWh")

if len(n.storage_units):
    st = n.storage_units.groupby("carrier")[["p_nom_opt", "p_nom"]].sum().round(1)
    print("\n--- 儲能 (StorageUnit) ---")
    print(st.to_string())

if len(n.global_constraints):
    print("\n--- 全域約束（碳排）---")
    print(n.global_constraints[["type", "constant", "mu"]].to_string())
    co2 = n.global_constraints.filter(like="CO2", axis=0)
    if len(co2):
        print(f"\nCO2 上限 {co2.constant.iloc[0]:.4e} tCO2 | 影子價格 {co2.mu.iloc[0]:.2f} EUR/tCO2")
        print("（mu != 0 代表碳約束有綁定）")

print(f"\n--- 輸電 ---")
print(f"AC 線路 s_nom_opt 合計 {n.lines.s_nom_opt.sum()/1e3:.1f} GW（原 {n.lines.s_nom.sum()/1e3:.1f} GW）")
if len(n.links):
    print(f"Link p_nom_opt 合計 {n.links.p_nom_opt.sum()/1e3:.1f} GW")

ls = n.generators[n.generators.carrier == "load shedding"]
if len(ls):
    shed = n.generators_t.p[ls.index].mul(w, axis=0).sum().sum() / 1e6
    print(f"\n卸載量 {shed:.2f} TWh（佔需求 {shed/(n.loads_t.p.mul(w,axis=0).sum().sum()/1e6)*100:.2f}%）")
