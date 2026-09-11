KR2036_ramp_lyden 首次求解：Infeasible（HiGHS IPM 21 迭代 / 2754 s / primal infeasible）

根因：CCGT p_min_pu 0.40 搭配 CCL 釘死的 64,600 MW，強制燃氣全年發 226.4 TWh
      -> 76.6 Mt CO2；加上 coal p_min_pu 0.357 的 92.2 Mt，強制碳排下限 168.8 Mt，
      超出 co2.limit 149.9 Mt 達 18.9 Mt。

事前做的「必發 MW (51,832) vs 最低需求 MW (55,605)」檢查通過（餘裕 3,773 MW），
但功率可行不等於碳排可行 —— 該檢查不足以判定可行性，日後須一併驗算
「各 carrier p_nom x p_min_pu x 8760 / efficiency x co2_emissions 的加總 vs co2.limit」。

可行區間：coal 的 92.2 Mt 為硬底，燃氣剩餘預算 57.7 Mt = 170.7 TWh = CF 0.302，
          故 CCGT p_min_pu 須 < 0.30，留調度空間建議 0.20-0.25。
