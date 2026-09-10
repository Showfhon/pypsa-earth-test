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

vre = ["solar", "onwind", "offwind-ac", "offwind-dc"]
rows = []
for c in vre:
    idx = n.generators.index[n.generators.carrier == c]
    cols = idx.intersection(n.generators_t.p_max_pu.columns)
    if not len(cols):
        continue
    avail = (n.generators_t.p_max_pu[cols] * n.generators.loc[cols, "p_nom_opt"]).mul(w, axis=0).sum().sum() / 1e6
    disp = n.generators_t.p[cols].mul(w, axis=0).sum().sum() / 1e6
    rows.append(
        {
            "carrier": c,
            "可發_TWh": round(avail, 1),
            "實發_TWh": round(disp, 1),
            "棄電_TWh": round(avail - disp, 2),
            "棄電率": f"{(avail - disp) / avail * 100:.2f}%" if avail > 0 else "-",
        }
    )
if rows:
    cur = pd.DataFrame(rows)
    print("\n--- VRE 棄電 ---")
    print(cur.to_string(index=False))
    a, d = cur["可發_TWh"].sum(), cur["實發_TWh"].sum()
    print(f"VRE 合計棄電率 {(a - d) / a * 100:.2f}%（論文 2.9%）| 佔總需求 {(a - d) / (n.loads_t.p.mul(w, axis=0).sum().sum() / 1e6) * 100:.2f}%")

if len(n.global_constraints):
    print("\n--- 全域約束（碳排）---")
    print(n.global_constraints[["type", "constant", "mu"]].to_string())
    co2 = n.global_constraints.filter(like="CO2", axis=0)
    if len(co2):
        emissions = 0.0
        for c in n.generators.carrier.unique():
            if c in n.carriers.index and n.carriers.at[c, "co2_emissions"] > 0:
                idx = n.generators.index[n.generators.carrier == c]
                emissions += (
                    n.generators_t.p[idx].mul(w, axis=0).sum() / n.generators.loc[idx, "efficiency"]
                ).sum() * n.carriers.at[c, "co2_emissions"]
        cap = co2.constant.iloc[0]
        print(f"\n實際碳排 {emissions/1e6:.1f} Mt | 上限 {cap/1e6:.1f} Mt | 用掉 {emissions/cap*100:.1f}%")
        print(f"影子價格 {co2.mu.iloc[0]:.2f} EUR/tCO2（mu != 0 代表碳約束有綁定）")

print(f"\n--- 輸電 ---")
print(f"AC 線路 s_nom_opt 合計 {n.lines.s_nom_opt.sum()/1e3:.1f} GW（原 {n.lines.s_nom.sum()/1e3:.1f} GW）")
if len(n.links):
    print(f"Link p_nom_opt 合計 {n.links.p_nom_opt.sum()/1e3:.1f} GW")

ls = n.generators[n.generators.carrier == "load shedding"]
if len(ls):
    shed = n.generators_t.p[ls.index].mul(w, axis=0).sum().sum() / 1e6
    print(f"\n卸載量 {shed:.2f} TWh（佔需求 {shed/(n.loads_t.p.mul(w,axis=0).sum().sum()/1e6)*100:.2f}%）")
