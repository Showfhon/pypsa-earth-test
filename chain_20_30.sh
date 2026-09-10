#!/usr/bin/env bash
# 20 節點 + CCL -> 檢查存檔 -> 30 節點 + CCL -> 檢查存檔
# 用 PID 等待，避免 pgrep 字串自我匹配
cd /home/showfhon/pypsa-earth

run_one () {
  local N=$1 TMO=$2
  local NC=results/KR2036_opus/networks/elec_s_${N}_ec_lcopt_Co2L-CCL-3H.nc
  local SLOG=logs/KR2036_opus/solve_network/elec_s_${N}_ec_lcopt_Co2L-CCL-3H_solver.log
  local RLOG=solve_${N}_3h_CCL.log

  echo "=========================================================="
  echo "${N} 節點 + CCL 啟動 $(date '+%m-%d %H:%M:%S')  timeout ${TMO}"
  echo "=========================================================="
  python - <<PY
from ruamel.yaml import YAML
y=YAML(); y.preserve_quotes=True; y.width=4096
c=y.load(open('config.yaml'))
c['scenario']['clusters']=[${N}]
y.dump(c, open('config.yaml','w'))
print("clusters ->", list(c['scenario']['clusters']))
PY
  snakemake --unlock >/dev/null 2>&1
  timeout "$TMO" snakemake "$NC" -j12 --resources mem_mb=60000 > "$RLOG" 2>&1 &
  local PID=$!
  wait $PID
  echo "${N} 節點結束 $(date '+%H:%M:%S')"

  echo "--- LP 規模 ---"; grep -m1 "has .* rows" "$SLOG" 2>/dev/null
  echo "--- IPX 末 8 個 iteration ---"
  grep -E "^ +[0-9]+ +-?[0-9.]+e" "$SLOG" 2>/dev/null | tail -8
  echo "--- factorization 總數: $(grep -cE 'Start  fact' "$SLOG" 2>/dev/null) ---"
  echo "--- Summary ---"; tail -8 "$SLOG" 2>/dev/null

  if [ -f "$NC" ]; then
    echo "--- 四項檢查 ---"
    python report_results.py "$NC" 2>&1 | grep -vE "^INFO:pypsa|FutureWarning"
    local D=results/KR2036_opus/archive_${N}n_3h_CCL_solved
    mkdir -p "$D"; cp "$NC" "$SLOG" "$RLOG" config.yaml "$D"/ 2>/dev/null
    python report_results.py "$NC" > "$D"/report.txt 2>&1
    echo ">>> 已存檔 $D"
    return 0
  else
    echo ">>> ${N} 節點沒有產出 .nc"
    return 1
  fi
}

run_one 20 6h
echo
echo "記憶體狀況：$(free -g | awk 'NR==2{print "used "$3"G / total "$2"G"}')"
run_one 30 8h
echo "全部結束 $(date '+%m-%d %H:%M:%S')"
