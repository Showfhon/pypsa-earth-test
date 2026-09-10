# 2026-09-09 夜間執行摘要

> 最後更新 2026-09-10 00:25。基準線（10 節點/3H/無 CCL）執行中，CCL 版已排入自動鏈。
> 但過程中找到並修正了三個實質的資料/設定錯誤，並把求解失敗的原因縮小到一個具體嫌疑。

## 一句話
CCL 的「infeasible」已查明是**需求未校準**的後果，不是 CCL 的問題 —— 校準後 CCL 完全可用。
過程中修正了**核能被設計壽命誤殺**、**biomass 標籤漏映射**、**需求量未校準（2.25 倍）** 三個問題。
但無 CCL 版本在 30 節點 / 3H 下，IPM 與 dual simplex 都無法收斂 —— 已確認**不是時間不夠**，
而是數值條件問題，最新嫌疑是 `objective_constant`（見第五節）。

---

## 一、程式碼改動（2 處）

### 1. `scripts/add_electricity.py` — `load_powerplants` 的 `carrier_dict`
```python
"solid biomass": "biomass",   # 新增
```
ppm 對韓國產出的標籤是 `solid biomass`，原本只映射 `bioenergy`，導致 21 筆 / 1,073 MW
生質能完全消失，CCL 的 biomass 列永遠匹配不到。修正後 log 出現
`Added extendable {'nuclear','biomass','CCGT'}`。

**未修正（依你指示只回報）**：`wind` 43 筆 1,915 MW、`waste` 5 筆 69 MW、`biogas` 2 筆 51 MW
仍未映射。其中 `wind` 因 `attach_wind_and_solar` 之後的 IRENA gap-filling 會補回容量，
但 `p_nom_min` 下限對風力是 0（solar 因標籤相符是真實的 10,401 MW）。

### 2. `scripts/solve_network.py` — `add_CCL_constraints` 加入 include_existing 常數項
非擴建機組的 `p_nom` 依 (country, carrier-group) 加總後從 RHS 扣除，
`include_existing: false` 時跳過。既有的 grouper 對齊修正未動。

**實測發現**：`cluster_network` 的 `aggregation_strategies`（`p_nom: sum` / `p_nom_min: sum`）
會把非擴建機組併進擴建機組，所以在 clustered 網路上五個 CCL group 的常數項**全是 0**。
你原本的「方案 3」直覺是對的，只是原因在 clustering 而非 add_electricity。
這段程式仍有價值：若某 CCL carrier 不在 `extendable_carriers`，常數項會正確捕捉它。

---

## 二、config.yaml 改動

### 遷移（0.8.0 → 0.9.0 schema）
七處區塊改名，舊區塊已刪除。`# >>> KR` 註解 **57 條全程保持 57 條**，值零改動：

| 舊（0.8.0） | 新（0.9.0） |
|---|---|
| `cluster_options:` | `clustering:` |
| `clean_osm_data_options:` | `osm.clean_osm_data` |
| `build_osm_network:` | `osm.build_osm_network` |
| `custom_busmap:` | `enable.custom_busmap` |
| `path_custom_shapes:` / `path_custom_offshore:` / `tolerance:` | `subregion.*` |

另補 `storage_techs`、`electricity.max_hours.{li-ion,lfp,vanadium,lair,pair,iron-air}`、
`demand_data.scenario`；`custom_powerplants` 改 dict；`lines.ac_types`/`dc_types` 改巢狀
（你的 154/345/765 進 `default:`，`AU:`/`US:` 照抄，`use_country_specific_types: false`）。
未補 `sector.*` 71 個 key（Snakefile 會自動 fallback，且該情境全關）。

**你問的規則 4**：0.9.0 的 `get_linetype_by_voltage_and_country`（`scripts/_helpers.py:2452`）
已改成 `min(mapping, key=|candidate - v_nom|)` **自動取最近值**，全 repo 無 symmetric_difference 檢查，
`electricity.voltages` 與 `ac_types.default` 不需一致。
（附註：Snakemake 遞迴合併會把 default 的 `275.`/`330.` 併進生效的 `ac_types.default`，對韓國無影響。）

### 值的改動

| 項目 | 原 | 新 | 原因 |
|---|---|---|---|
| `version` | 0.8.0 | 0.9.0 | schema 已遷移，否則每次跑跳版本警告 |
| `enable.retrieve_cutout` | true | false | cutout 已存在，snakemake 拒絕覆寫並中止 |
| `existing_capacities.grouping_years_power` | …2030 | 追加 2035, 2040 | **上游 bug**（見三之3） |
| `electricity.powerplants_filter` | `(DateOut>=2036 or NaN) and (DateIn<=2036 or NaN)` | 第一組加 `or Fueltype=='Nuclear'` | 見三之1 |
| `co2.limit` | 3.0e+8 | **1.499e+8** | 你中途指定 |
| `scenario.opts` | [Co2L-CCL-3H] | **[Co2L-3H, Co2L-1H]** | CCL infeasible，依你指示移除 |
| `load_options.scale` | 1.7 | **0.7541** | 見三之2 |
| `electricity.operational_reserve.activate` | true | **false** | 你的升級階梯第二項 |
| `solving.solver.options` | highs-default | **highs-simplex** | 見第四節 |

⚠️ 兩處 `# >>> KR` 註解因值變動而過時，我沒有動它們，你可能要改文字：
- `co2:` 上方「依使用者指定，2036 上限 3 億噸」（現在是 1.499e+8）
- `load_options.scale` 上方的校準說明（現在已校準完成）

---

## 三、三個實質發現（都已修正）

### 1. 核能被 ppm 的設計壽命誤殺
`DateOut >= 2036` 篩掉 4 部機組，合計 4,868 MW：

| 機組 | MW | DateIn | DateOut | 差 |
|---|---:|---:|---:|---:|
| Shin Wolsong 1 | 1,048 | 1982 | 2032 | 50 |
| Kori 2 | 1,728 | 1983 | 2033 | 50 |
| Kori 4 | 1,046 | 1985 | 2035 | 50 |
| Kori 3 | 1,046 | 1985 | 2035 | 50 |

`DateOut` 一律 = `DateIn + 50`，是 ppm 填的**假設設計壽命**，不是真實除役決定。
這四部正是第10次電기본規劃 **계속운전** 的機組。加 `or Fueltype=='Nuclear'` 後
核能 **25,003 → 31,161 MW**（24 部），對 BPLE 目標 31,700 只差 539 MW。

**三階段對帳結論**：powerplants.csv → elec.nc → elec_s.nc → elec_s_30.nc **零損失**，
所有容量落差 100% 發生在 `powerplants_filter`，不是孤立節點、也不是 clustering。

### 2. 需求未校準，是目標值的 2.25 倍
`prediction_year: 2040` + `scale: 1.7` 產生 **1,504.3 TWh / 尖峰 244 GW**，
是第10次電기본 2036 目標 667.3 TWh 的 2.25 倍。依你 config 裡寫的公式：
```
scale_new = 1.7 x 667.3 / 1504.3 = 0.7541
```
校準後 demand_profiles **667.3 TWh / 尖峰 108.2 GW**（正中目標）。

### 3. `grouping_years_power` 上游 bug
`get_grouping_year` 用 `np.digitize(build_year, grouping_years, right=True)`，
對 `build_year > max(grouping_years)=2030` 回傳越界索引 →
`IndexError: index 15 is out of bounds for axis 0 with size 15`。
韓國資料剛好有 **1 筆 DateIn=2031** 通過你的 filter。該欄與 0.9.0 default 完全一樣、
沒有 KR 標記，屬上游限制被 2036 情境觸發。已追加 2035、2040。

---

## 四、CCL「不可行」的真正原因 —— 一個模型合理性檢查

> **結論已更新（原本記為「未解」，現已查明）：CCL 本身沒問題，可以放回研究設計。**

### 這是模型的正確行為，不是 bug

需求灌到官方目標的 2.25 倍（1,504 TWh、尖峰 244 GW）時，第10次電力供需基本計畫的
2036 容量規劃**根本供不起**：CCL 把 solar ≤72.3、wind ≤37.5、CCGT =64.6、
nuclear =31.7、biomass =1.62 GW 全部鎖死，加上既有燃煤 31.2 GW，
可調度容量上限約 **238 GW < 尖峰 244 GW**。模型正確地判定不可行。

**這反過來是一個很好的模型合理性驗證**：官方容量規劃是配著官方需求預測做的，
把需求灌大 2.25 倍後容量規劃就撐不住 —— 模型如實反映了這個物理事實。

### 歸因證據

同樣的程式、同樣的 csv、同樣的求解器設定，只換網路：

| 網路 | 需求尖峰 | 結果 |
|---|---:|---|
| 10 節點（scale 1.7，未校準） | 243.9 GW | **infeasible** |
| 30 節點（scale 0.7541，已校準） | 108.2 GW | **optimal** |

逐項累加（30 節點、240h、無 CO2、無 reserve）：

| 加到第幾項 | 結果 |
|---|---|
| solar | optimal |
| + onwind+offwind-ac+offwind-dc | optimal |
| + CCGT | optimal |
| + nuclear | optimal |
| + biomass（全部五項） | **optimal** |
| 字母序全部五項 | optimal |

### 排除的假說：約束對齊錯位

曾懷疑 `lhs`（依 group 內部順序）與 `rhs`（依 csv 順序）錯位。實測：

```
csv 順序      : solar, onwind+offwind-ac+offwind-dc, CCGT, nuclear, biomass
lhs group 順序: nuclear, CCGT, solar, biomass, onwind+offwind-ac+offwind-dc   ← 確實不同
sel 後 lhs    : solar, onwind+offwind-ac+offwind-dc, CCGT, nuclear, biomass
rhs           : solar, onwind+offwind-ac+offwind-dc, CCGT, nuclear, biomass
rhs 值        : [59130, 30680, 64600, 31700, 1620]
>>> 一一對應
```
`lhs` 內部順序確實與 csv 不同，但 `.sel(group=index)` 與 `.loc[index]` 都**按標籤**重排，
最終對齊正確。不是對齊 bug。

## 四之二、（歷史記錄）當初的排除過程

用 30 節點網路的前 240 小時逐項排除（每個組合幾秒）：

| 組合 | 結果 |
|---|---|
| 完整（CCL + Co2L + reserve） | infeasible |
| 關 reserve | infeasible |
| 移除 CO2 | infeasible |
| 關 reserve + 移除 CO2 | infeasible |
| **無 CCL（只 Co2L + reserve）** | **optimal** |

再逐一測單個 group（無 CO2、無 reserve）：

| 只有 | 結果 |
|---|---|
| solar / wind / CCGT / nuclear / biomass | **五個單獨都 optimal** |
| **五個一起** | **infeasible** |
| 五個一起 + `include_existing=False` | infeasible |

**所以：不是 CCL 上下界不可達**（p_nom_min/p_nom_max 全部有解空間）、
**不是 include_existing**、**不是 CO2**、**不是 reserve**。是五個約束的交互作用，尚未查明。
IPM + `user_bound_scale=-15` 也判 infeasible。
精確定位需要 IIS，但 linopy 的 `compute_infeasibilities` 只支援 Gurobi/Xpress。

### 三段式 `+` 語法（已驗證可用）
csv 的 `KR,wind,...` 改成 `KR,onwind+offwind-ac+offwind-dc,...` 後，
現行 `add_CCL_constraints` 的 `carrier_map` 會把三個 carrier 對到同一個 group，
`groupby().sum()` 合併成**一條**加總約束（26 台機組），不是三條。
`split("+")` 無段數上限。→ 原本規劃的 `CARRIER_GROUPS` 程式改動整個取消。

---

## 五、求解器

> ⚠️ **重要但書：下表所有 30 節點的嘗試，除了最後兩列，都是在需求 2.25 倍的狀態下跑的。**
> 那些「卡住」的結論**不能當成純粹的求解器極限**，必須在校準後的需求下重測才算數。
> 20 / 30 節點的可解性目前是未知數，不是已知的失敗。

所有嘗試（30 節點 / 3H / 無 CCL）：

| 嘗試 | 時長 | 結果 |
|---|---|---|
| IPM 原設定（scale 1.7） | 87 分 | gap 停在 2.67 |
| IPM（scale 0.7541） | 35 分 | gap 反而升到 14.7 |
| IPM + `user_bound_scale=-15` | 19 分 | Bound 3e+10→9e+05，但換來 "excessively small bounds"；iter 5 卡住 9 次 factorization |
| IPM + `operational_reserve: false` | 19 分 | LP 從 304萬→253萬列、Matrix range 1e-04→1e-02（reserve 正是 1e-04 係數來源），iter 5 仍卡住 |
| **dual simplex + reserve off** | **4 小時（timeout）** | 63.5 萬次迭代，目標收斂到 ~1.659e10，但 **Pr 不收斂** |

**我跳過了你階梯的第三項 `highs-fallback`**：它只把容差從 1e-6 放寬到 1e-4，
但實測 gap 停在 2.79，比 1e-4 差 4 個數量級，數學上不可能通過。直接用你 config 裡
標為「最後手段」的 `highs-simplex`。

### 為什麼確定不是時間問題

dual simplex 跑滿 4 小時的資料：

目標函數**確實在收斂**（增幅逐次減半，漸近 ~1.66e10）：
```
22:06  1.6465e10
22:16  1.6507e10   +0.0042
22:26  1.6535e10   +0.0028
22:36  1.6568e10   +0.0033
22:46  1.6584e10   +0.0016
22:58  1.6594e10   +0.0010
```

但 dual simplex 要終止必須 `Pr → 0`，而 **Pr 完全沒有下降趨勢**：
```
19:36  Pr: 173,374 (9.26e11)
20:36  Pr: 192,922 (5.64e10)
21:36  Pr: 208,030 (4.57e12)
22:36  Pr: 224,902 (1.38e13)   ← 不可行個數還在往上
22:58  Pr: 182,053 (1.66e11)
```
3 小時內不可行個數從 15.2 萬升到 18~22 萬，總量在 1e10~2e13 間震盪。再給 12 小時大概率同一張圖。

IPM 是反過來的症狀：可行性極好（pinf 1e-8、dinf 1e-13）但對偶間隙卡在 2~15。
**兩種方法各卡在不同的一半，都不是「快到了」。**

### 最新嫌疑：`objective_constant`

把模型建起來後逐一檢查所有變數的界限：

```
變數                  n      lower          upper
objective_constant    1      3.076724e+10   3.076724e+10   ← 上下界都釘死
StorageUnit-spill  9600      0              3.43e+01
其餘全部（p_nom / p / s / SOC…）              -inf 或 0     +inf
```

HiGHS 一直警告的 `Bound [4e-01, 3e+10]` **不是任何決策變數**，
而是 linopy 把目標函數常數項（非擴建機組的固定資本成本）做成的一個固定變數，目標係數 1。

一個係數 1、值 3e10 的固定變數，它的對偶乘子只要有 1e-3 誤差，對偶目標就偏掉 3e7；
誤差再大一點就能解釋我們看到的 dual obj = −2e13。

**對照實驗進行中**（30 節點 720 小時，比較「原樣」vs「非擴建 capital_cost 歸零使常數=0」的收斂行為），
結果尚未出爐。

---

## 六、產出位置

```
results/KR2036_opus/
  networks/                                  (空 — 尚無成功結果)
  archive_10n_3h_CCL_infeasible/             10 節點 CCL（infeasible）
  archive_30n_3h_scale1.7_nonconv/           30 節點 IPM scale1.7
  archive_30n_3h_scale0.7541_nonconv/        30 節點 IPM 校準後
  archive_30n_3h_ubs15_nonconv/              30 節點 IPM + user_bound_scale
  archive_30n_3h_noreserve_ipm_nonconv/      30 節點 IPM + reserve off
```
每個 archive 內含當時的 config、solver log、snakemake log。

根目錄：`solve_10.log`、`solve_30_3h*.log`、`report_results.py`（解出來後直接
`python report_results.py <solved.nc>` 產出容量/發電/碳排/成本摘要）。

環境：conda env 的 linopy 已由 **0.9.1 降到 0.5.8**（`pixi.lock` 鎖定的版本），
這是 `cluster_network` 能通過的前提（0.9.1 會在 `distribute_clusters` 拋 MultiIndex TypeError）。

---

## 七、目前的執行計畫（已排定）

1. **10 節點 / 3H / 無 CCL / reserve off / IPM 全年** —— 執行中（00:21 啟動，timeout 10h）
   建立基準線，記錄 Iter 數與時間
2. **10 節點 / 3H / + CCL** —— 已串成自動鏈（`chain_after_baseline.sh`），基準線一結束就接著跑
   預期 CCL 反而幫助收斂：nuclear/CCGT/biomass 被 min=max 釘死、solar/wind 有上下限，
   自由度大減，IPM 的 gap 通常收得更快
3. 兩者跑完都自動做四項檢查（碳排是否貼在 1.499e8 / load shedding 總量 /
   各 carrier p_nom_opt 對照官方 2036 容量表 / 棄電率，論文是 2.9%）並存檔

### 已調整

- `ipm_optimality_tolerance: 1e-6 → 1e-4`。容量規劃問題相對 gap 到 1e-4 即足夠
  （總成本 1.6e10 上約 1.6e6 EUR 的誤差），照每步 ×0.85 的速率可省約 1/3 時間

### 仍待決定

1. **20 / 30 節點的真實極限** —— 必須在校準後需求下重測（見第五節但書）
2. **Gurobi 學術授權** —— 會一次解決求解器與 IIS 兩個問題。目前只有 pip 試用授權（2000 變數上限）
3. **`operational_reserve` 要不要放回去** —— 目前為收斂關掉了，但你 config 註解說論文有開
4. **兩處過時的 `# >>> KR` 註解**（co2.limit、scale）
5. **`wind` / `waste` / `biogas` 標籤映射** 要不要補
