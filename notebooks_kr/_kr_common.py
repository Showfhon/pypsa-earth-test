"""KR2036 notebooks 共用設定。

notebooks_kr/ 下每一本 notebook 的第一個 code cell 都 import 這一份，
不要各寫各的路徑、配色與存圖邏輯。
"""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pypsa
import yaml


def _find_root(start: Path | None = None) -> Path:
    here = Path(start or Path.cwd()).resolve()
    for cand in [here, *here.parents]:
        if (cand / "config.yaml").is_file():
            return cand
    raise FileNotFoundError("往上找不到含 config.yaml 的專案根目錄")


ROOT = _find_root()

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

RUN_NAME = CONFIG["run"]["name"]
RES = ROOT / "resources" / RUN_NAME
FIG_DIR = ROOT / "results" / "compare" / "notebooks_kr"

# OSM / shapes / bus_regions / renewable_profiles 都是與情境無關的韓國地理資料，
# 兩個情境的檔案 checksum 相同，因此共用 KR2036_opus 這一份。
OSM_CLEAN_LINES = RES / "osm/clean/all_clean_lines.geojson"
OSM_CLEAN_SUBSTATIONS = RES / "osm/clean/all_clean_substations.geojson"
OSM_RAW_LINES = RES / "osm/raw/all_raw_lines.geojson"
OSM_RAW_SUBSTATIONS = RES / "osm/raw/all_raw_substations.geojson"
COUNTRY_SHAPES = RES / "shapes/country_shapes.geojson"
GADM_SHAPES = RES / "shapes/gadm_shapes.geojson"
BUS_REGIONS = RES / "bus_regions"
RENEWABLE_PROFILES = RES / "renewable_profiles"

SCENARIOS = {
    "baseline": {
        "label": "基準情境",
        "long_label": "基準情境（KR2036_opus，10 節點 / 3H / CCL）",
        "path": ROOT / "results/KR2036_opus/networks/elec_s_10_ec_lcopt_Co2L-CCL-3H.nc",
        "color": "#4c72b0",
    },
    "kwak_full": {
        "label": "kwak_full",
        "long_label": "kwak_full（KR2036_kwak_full，10 節點 / 3H）",
        "path": ROOT / "solved/10n_3H_kwak_full.nc",
        "color": "#dd8452",
    },
}

# 含濟州；地圖投影用 PlateCarree，需要等面積時（算密度）用 EPSG:5179 Korea 2000
KR_EXTENT = [125.0, 130.2, 33.0, 38.8]
KR_EQUAL_AREA_CRS = "EPSG:5179"

# 韓國輸電電壓等級 [V]。其餘 OSM 值歸「其他」。
KR_VOLTAGE_LEVELS = [154000, 345000, 765000]
KR_VOLTAGE_COLORS = {
    "154 kV": "#2b8cbe",
    "345 kV": "#e6550d",
    "765 kV": "#756bb1",
    "其他": "#bdbdbd",
}

# 配色一律取 config.yaml 的 plotting.tech_colors，與 results/compare/kwak_full_vs_paper/
# 既有圖表同源（scripts/plot_network.py、scenario_vs_paper_extra.py 也是吃這一份）。
CARRIER_COLORS = dict(CONFIG["plotting"]["tech_colors"])

CARRIER_LABELS = {
    "nuclear": "核能",
    "coal": "燃煤",
    "CCGT": "燃氣（複循環）",
    "OCGT": "燃氣（單循環）",
    "oil": "燃油",
    "biomass": "生質能",
    "solar": "太陽光電",
    "onwind": "陸域風電",
    "offwind-ac": "離岸風電（AC）",
    "offwind-dc": "離岸風電（DC）",
    "ror": "川流式水力",
    "hydro": "水庫水力",
    "PHS": "抽蓄水力",
    "battery": "電池儲能",
    "load shedding": "缺電量（虛擬機組）",
    "AC": "交流線路",
    "DC": "直流線路",
}

# n.statistics 回傳的 carrier 是 nice_name（如 "Combined-Cycle Gas"），
# 需要反查回原始 carrier key 才能對到配色與中文標籤。
# config 的 nice_names 不完整（缺 nuclear / coal / biomass / oil），
# 因此 load_network() 會再用網路自身的 n.carriers.nice_name 補齊這份對照。
NICE_NAME_TO_CARRIER = {
    v: k for k, v in (CONFIG["plotting"].get("nice_names") or {}).items()
}


def carrier_key(name: str) -> str:
    """把 nice_name 或原始 carrier 名稱正規化成 config 的 carrier key。"""
    # CARRIER_LABELS 的 key 才是真正的 carrier；tech_colors 另含 "Nuclear" 這類
    # 大寫別名，若先比對它會讓 nice_name 提早回傳而查不到中文標籤。
    if name in CARRIER_LABELS:
        return name
    if name in NICE_NAME_TO_CARRIER:
        return NICE_NAME_TO_CARRIER[name]
    lowered = {k.lower(): v for k, v in NICE_NAME_TO_CARRIER.items()}
    if name.lower() in lowered:
        return lowered[name.lower()]
    if name in CARRIER_COLORS:
        return name
    return name


def carrier_color(name: str, default: str = "#9e9e9e") -> str:
    return CARRIER_COLORS.get(carrier_key(name), default)


def carrier_label(name: str) -> str:
    key = carrier_key(name)
    return CARRIER_LABELS.get(key, key)


def setup_matplotlib() -> None:
    """統一字體與樣式；Noto Sans CJK 才能正常顯示中文標籤。"""
    plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 110
    plt.rcParams["savefig.bbox"] = "tight"
    plt.rcParams["axes.grid"] = True
    plt.rcParams["grid.alpha"] = 0.3


def savefig(name: str, fig=None, dpi: int = 300) -> None:
    """同時輸出 300 dpi PNG 與同名 PDF 到 results/compare/notebooks_kr/。"""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig = fig or plt.gcf()
    for ext in ("png", "pdf"):
        fig.savefig(FIG_DIR / f"{name}.{ext}", dpi=dpi, bbox_inches="tight")
    print(f"已存檔：{FIG_DIR / name}.png / .pdf")


def load_network(key: str, drop_load_shedding: bool = True) -> pypsa.Network:
    """讀情境網路；預設排除 carrier 含 "load" 的 load shedding 虛擬機組。"""
    n = pypsa.Network(str(SCENARIOS[key]["path"]))
    NICE_NAME_TO_CARRIER.update(
        {v: k for k, v in n.carriers.nice_name.items() if v and v not in NICE_NAME_TO_CARRIER}
    )
    if drop_load_shedding:
        shedding = n.generators.index[
            n.generators.carrier.str.contains("load", case=False)
        ]
        n.mremove("Generator", shedding)
    return n


def load_regions(clusters: int = 10, kind: str = "onshore") -> gpd.GeoDataFrame:
    path = BUS_REGIONS / f"regions_{kind}_elec_s_{clusters}.geojson"
    return gpd.read_file(path).set_index("name")


def voltage_bin(voltage_v) -> str:
    """把 OSM 電壓值 [V] 分到韓國的 154 / 345 / 765 kV 三級，其餘歸「其他」。"""
    try:
        v = float(voltage_v)
    except (TypeError, ValueError):
        return "其他"
    for level in KR_VOLTAGE_LEVELS:
        if abs(v - level) < 1e-6:
            return f"{level // 1000} kV"
    return "其他"
