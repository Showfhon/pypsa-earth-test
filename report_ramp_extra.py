# -*- coding: utf-8 -*-
"""ramp 情境附加指標。用法: python report_ramp_extra.py <solved.nc>"""
import sys
import warnings

import pandas as pd
import pypsa

warnings.filterwarnings("ignore")

n = pypsa.Network(sys.argv[1])
w = n.snapshot_weightings.objective

print(f"=== 附加指標 {sys.argv[1]} ===")

print("\n--- 熱機組發電量 ---")
p = n.generators_t.p.mul(w, axis=0).sum().groupby(n.generators.carrier).sum() / 1e6
for c in ["nuclear", "coal", "CCGT", "biomass", "oil"]:
    if c in p.index:
        cap = n.generators.loc[n.generators.carrier == c, "p_nom_opt"].sum()
        cf = p[c] * 1e6 / (cap * 8760) if cap else float("nan")
        print(f"{c:<9} {p[c]:8.1f} TWh | p_nom_opt {cap:9,.0f} MW | 容量因數 {cf:.3f}")

print("\n--- 太陽能棄電 ---")
idx = n.generators.index[n.generators.carrier == "solar"]
cols = idx.intersection(n.generators_t.p_max_pu.columns)
avail = (n.generators_t.p_max_pu[cols] * n.generators.loc[cols, "p_nom_opt"]).mul(w, axis=0).sum().sum() / 1e6
disp = n.generators_t.p[cols].mul(w, axis=0).sum().sum() / 1e6
print(f"可發 {avail:.1f} TWh | 實發 {disp:.1f} TWh | 棄電 {avail-disp:.2f} TWh | 棄電率 {(avail-disp)/avail*100:.2f}%")

print("\n--- 儲能充放電 ---")
su = n.storage_units
dis = n.storage_units_t.p_dispatch.mul(w, axis=0).sum()
sto = n.storage_units_t.p_store.mul(w, axis=0).sum()
tab = pd.DataFrame(
    {
        "p_nom_opt_MW": su.groupby("carrier").p_nom_opt.sum(),
        "放電_TWh": dis.groupby(su.carrier).sum() / 1e6,
        "充電_TWh": sto.groupby(su.carrier).sum() / 1e6,
    }
).round(3)
tab["循環效率損失_TWh"] = (tab["充電_TWh"] - tab["放電_TWh"]).round(3)
print(tab.to_string())

print("\n--- 代表節點 marginal_price 日均曲線 ---")
bus = n.loads_t.p_set.sum().idxmax()
mp = n.buses_t.marginal_price[bus]
prof = mp.groupby(mp.index.hour).mean()
print(f"節點 {bus}（全年負載最大）")
print("  " + "  ".join(f"{h:02d}h:{v:6.2f}" for h, v in prof.items()))
print(f"最高 {prof.max():.2f} | 最低 {prof.min():.2f} | 日內價差 {prof.max()-prof.min():.2f} EUR/MWh")
