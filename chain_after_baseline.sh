#!/usr/bin/env bash
# 基準線跑完 -> 四項檢查 -> 自動接 10 節點 + CCL
cd /home/showfhon/pypsa-earth

BASE_NC=results/KR2036_opus/networks/elec_s_10_ec_lcopt_Co2L-3H.nc
CCL_NC=results/KR2036_opus/networks/elec_s_10_ec_lcopt_Co2L-CCL-3H.nc
SLOG=logs/KR2036_opus/solve_network/elec_s_10_ec_lcopt_Co2L-3H_solver.log

# 1) 等基準線結束
while pgrep -f "timeout 10h snakemake" >/dev/null; do sleep 60; done
echo "=========================================================="
echo "基準線結束 $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================================="
echo "--- IPX 最後 15 個 iteration ---"
grep -E "^ +[0-9]+ +-?[0-9.]+e" "$SLOG" | tail -15
echo "--- factorization 總數: $(grep -cE 'Start  fact' "$SLOG") ---"
echo "--- HiGHS Summary ---"
tail -12 "$SLOG"

if [ ! -f "$BASE_NC" ]; then
  echo ">>> 沒有產出 .nc，基準線失敗，鏈結中止"
  exit 1
fi

# 2) 四項檢查
echo
echo "=========================================================="
echo "四項檢查"
echo "=========================================================="
python report_results.py "$BASE_NC" 2>&1 | grep -vE "^INFO:pypsa|FutureWarning"

# 3) 存檔
D=results/KR2036_opus/archive_10n_3h_noCCL_solved
mkdir -p "$D"
cp "$BASE_NC" "$D"/ 2>/dev/null
cp "$SLOG" solve_10_3h_baseline.log config.yaml "$D"/ 2>/dev/null
python report_results.py "$BASE_NC" > "$D"/report.txt 2>&1
echo ">>> 已存檔到 $D"

# 4) 接 10 節點 + CCL
echo
echo "=========================================================="
echo "接續：10 節點 + CCL  $(date '+%H:%M:%S')"
echo "=========================================================="
snakemake --unlock >/dev/null 2>&1
timeout 10h snakemake "$CCL_NC" -j12 --resources mem_mb=60000 > solve_10_3h_CCL.log 2>&1
echo "CCL run 結束 $(date '+%H:%M:%S')"
CSLOG=logs/KR2036_opus/solve_network/elec_s_10_ec_lcopt_Co2L-CCL-3H_solver.log
grep -E "^ +[0-9]+ +-?[0-9.]+e" "$CSLOG" | tail -15
tail -12 "$CSLOG"
if [ -f "$CCL_NC" ]; then
  echo "--- CCL 版四項檢查 ---"
  python report_results.py "$CCL_NC" 2>&1 | grep -vE "^INFO:pypsa|FutureWarning"
  D2=results/KR2036_opus/archive_10n_3h_CCL_solved
  mkdir -p "$D2"; cp "$CCL_NC" "$CSLOG" solve_10_3h_CCL.log config.yaml "$D2"/ 2>/dev/null
  python report_results.py "$CCL_NC" > "$D2"/report.txt 2>&1
  echo ">>> 已存檔到 $D2"
else
  echo ">>> CCL run 沒有產出 .nc"
fi
