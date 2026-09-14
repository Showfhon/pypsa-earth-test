# -*- coding: utf-8 -*-
"""線性化 UC 探測：10n/3H 前 240 小時。
用法: python probe_uc.py [lp|uc]
  lp = 純 LP 基準（不開 committable）
  uc = 線性化 UC（committable=True + linearized_unit_commitment=True）
不寫入任何 config 或既有 .nc。
"""
import sys
import time
import warnings

import numpy as np
import pandas as pd
import pypsa

warnings.filterwarnings("ignore")

MODE = sys.argv[1] if len(sys.argv) > 1 else "uc"
HOURS = int(sys.argv[2]) if len(sys.argv) > 2 else 240
PRE = "networks/KR2036_opus/elec_s_10_ec_lcopt_Co2L-CCL-3H.nc"
REF = "results/KR2036_ramp/networks/elec_s_10_ec_lcopt_Co2L-CCL-3H.nc"

# CCL 目標容量（BPLE）
CCL = {"nuclear": 31700.0, "CCGT": 64600.0, "biomass": 1620.0}

# Lyden 的 p_min_pu 與每小時 ramp（使用者給定）
LYDEN = {
    "nuclear": dict(p_min_pu=0.45, ramp=0.03),
    "coal": dict(p_min_pu=0.357, ramp=2.38),
    "CCGT": dict(p_min_pu=0.40, ramp=3.47),
    "biomass": dict(p_min_pu=0.357, ramp=2.38),
}
# !!! 以下三項未取得 Lyden 數值，暫用文獻常見值，待替換 !!!
UC_ASSUMED = {
    "nuclear": dict(min_up_h=24, min_down_h=24, start_up_eur_per_mw=500.0),
    "coal": dict(min_up_h=6, min_down_h=6, start_up_eur_per_mw=100.0),
    "CCGT": dict(min_up_h=3, min_down_h=3, start_up_eur_per_mw=40.0),
    "biomass": dict(min_up_h=6, min_down_h=6, start_up_eur_per_mw=100.0),
}

n = pypsa.Network(PRE)
ref = pypsa.Network(REF)

# --- 截取前 240 小時 ---
step = float(n.snapshot_weightings.objective.iloc[0])  # 3.0
nsnap = int(HOURS / step)
n.set_snapshots(n.snapshots[:nsnap])
print(f"快照 {len(n.snapshots)} 個 × {step}h = {len(n.snapshots)*step:.0f} h "
      f"({n.snapshots[0]} → {n.snapshots[-1]})")

# --- 容量全部固定：熱機組用 CCL，其餘用 ramp 情境的解 ---
g = n.generators
for c in CCL:
    idx = g.index[g.carrier == c]
    cur = g.loc[idx, "p_nom"].sum()
    scale = CCL[c] / cur if cur > 0 else 0.0
    g.loc[idx, "p_nom"] = g.loc[idx, "p_nom"] * scale
for c in g.carrier.unique():
    if c in CCL:
        continue
    idx = g.index[g.carrier == c]
    common = idx.intersection(ref.generators.index)
    g.loc[common, "p_nom"] = ref.generators.loc[common, "p_nom_opt"]
g["p_nom_extendable"] = False

su = n.storage_units
common = su.index.intersection(ref.storage_units.index)
su.loc[common, "p_nom"] = ref.storage_units.loc[common, "p_nom_opt"]
su["p_nom_extendable"] = False
n.lines["s_nom"] = ref.lines.loc[n.lines.index, "s_nom_opt"]
n.lines["s_nom_extendable"] = False

# --- 套 Lyden 的 p_min_pu / ramp ---
for c, v in LYDEN.items():
    idx = g.index[g.carrier == c]
    if not len(idx):
        continue
    g.loc[idx, "p_min_pu"] = v["p_min_pu"]
    r = min(v["ramp"] * step, 1.0)
    g.loc[idx, "ramp_limit_up"] = r
    g.loc[idx, "ramp_limit_down"] = r

# --- UC 設定 ---
if MODE == "uc":
    rows = []
    for c, v in UC_ASSUMED.items():
        idx = g.index[g.carrier == c]
        if not len(idx):
            continue
        g.loc[idx, "committable"] = True
        # PyPSA 的 min_up_time/min_down_time 單位是「快照數」，不是小時
        mu = int(np.ceil(v["min_up_h"] / step))
        md = int(np.ceil(v["min_down_h"] / step))
        g.loc[idx, "min_up_time"] = mu
        g.loc[idx, "min_down_time"] = md
        # PyPSA 的 start_up_cost 單位是「每次啟動的總成本」，需乘上 p_nom
        g.loc[idx, "start_up_cost"] = v["start_up_eur_per_mw"] * g.loc[idx, "p_nom"]
        rows.append(dict(carrier=c, 機組=len(idx), p_nom合計=round(g.loc[idx, "p_nom"].sum()),
                         p_min_pu=g.loc[idx, "p_min_pu"].iloc[0],
                         ramp=round(g.loc[idx, "ramp_limit_up"].iloc[0], 3),
                         min_up_時段=mu, min_down_時段=md,
                         啟動成本_EUR每次=f"{g.loc[idx,'start_up_cost'].mean():,.0f}"))
    print("\n--- UC 參數（min_up/min_down/start_up 為假設值）---")
    print(pd.DataFrame(rows).to_string(index=False))

# --- CO2 上限按時段比例縮放 ---
share = len(n.snapshots) * step / 8760
if len(n.global_constraints):
    old = n.global_constraints.constant.iloc[0]
    n.global_constraints["constant"] = old * share
    print(f"\nCO2 上限依時段比例縮放：{old/1e6:.1f} Mt → {old*share/1e6:.3f} Mt（{share*100:.2f}%）")

print(f"\n=== 開始求解 (MODE={MODE}) ===")
t0 = time.time()
kw = dict(solver_name="highs", solver_options={"threads": 1})
if MODE == "uc":
    kw["linearized_unit_commitment"] = True
status, cond = n.optimize(**kw)
el = time.time() - t0
print(f"\n=== 結果 ===")
print(f"status={status} condition={cond} | 求解 {el:.1f} s")
print(f"LP 規模: 變數 {n.model.nvars:,} | 約束 {n.model.ncons:,}")
if status == "ok":
    print(f"目標函數 {n.objective:.6e}")
    if MODE == "uc" and hasattr(n.generators_t, "status") and len(n.generators_t.status.columns):
        st = n.generators_t.status
        print(f"\n--- status 變數分佈（共 {st.size:,} 個）---")
        for c in UC_ASSUMED:
            cols = st.columns.intersection(g.index[g.carrier == c])
            if not len(cols):
                continue
            v = st[cols].values.ravel()
            frac = ((v > 1e-4) & (v < 1 - 1e-4)).mean()
            print(f"{c:<8} =0: {(v<=1e-4).mean()*100:5.1f}%  =1: {(v>=1-1e-4).mean()*100:5.1f}%  "
                  f"分數值: {frac*100:5.1f}%  | 平均 {v.mean():.3f} 最小 {v.min():.3f}")
        allv = st.values.ravel()
        nf = ((allv > 1e-4) & (allv < 1 - 1e-4)).sum()
        print(f"\n全體: 分數值 {nf:,}/{len(allv):,} ({nf/len(allv)*100:.1f}%) | 全部為 1? "
              f"{'是（UC 無作用）' if (allv >= 1-1e-4).all() else '否（有機組真的停機/部分啟動）'}")
    w = n.snapshot_weightings.objective
    p = n.generators_t.p.mul(w, axis=0).sum().groupby(g.carrier).sum() / 1e3
    print(f"\n--- 發電量 GWh（{HOURS}h）---")
    print(p[p.abs() > 1e-6].round(1).sort_values(ascending=False).to_string())
