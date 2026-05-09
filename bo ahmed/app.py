import heapq
import math
import os
import re
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

import pandas as pd
from flask import Flask, jsonify, render_template, request

# Explicit static/template configuration helps avoid path issues.
app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates",
    static_url_path="/static",
)

DATASET_FILE = "PC_Components_Dataset_small.xlsx"
COMPONENT_ORDER = ["cpu", "motherboard", "ram", "storage", "gpu", "psu"]
PURPOSES = {
    "Gaming",
    "Office / General Use",
    "Content Creation",
    "AI / ML Workstation",
    "Budget Build",
    "High-End Build",
}
ALGORITHMS = {"BFS", "DFS", "UCS", "A*"}
MAX_RESULTS = 3
# Per-algorithm safety caps (all set to the same limit as required).
MAX_EXPLORED_STATES = {
    "BFS": 200_000,
    "DFS": 200_000,
    "UCS": 200_000,
    "A*": 200_000,
}
LOW_BUDGET_THRESHOLD = 1500.0
# Expansion cap per component step (ranked, compatibility-pruned); keeps search tractable.
EXPANSION_CAP = 12


def safe_float(value, default: float = 0.0) -> float:
    """Convert mixed numeric values to float safely."""
    if pd.isna(value):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    if not text:
        return default
    match = re.findall(r"[\d.]+", text.replace(",", ""))
    if not match:
        return default
    try:
        return float(match[0])
    except ValueError:
        return default


def safe_text(value, default: str = "") -> str:
    """Normalize text fields."""
    if pd.isna(value):
        return default
    return str(value).strip()


def to_bool(value) -> bool:
    """Handle boolean-like values from messy spreadsheets."""
    if isinstance(value, bool):
        return value
    text = safe_text(value).lower()
    if text in {"true", "yes", "1", "y", "supported", "available"}:
        return True
    # Support descriptive spreadsheet values like "Yes (M.2)" or "Supported: True".
    truthy_fragments = ["true", "yes", "supported", "available", "m.2", "nvme", "igpu", "integrated"]
    return any(fragment in text for fragment in truthy_fragments)


def first_existing(row: pd.Series, names: List[str], default=None):
    """Pick first existing column value from possible aliases."""
    lower_map = {c.lower(): c for c in row.index}
    for name in names:
        if name.lower() in lower_map:
            return row[lower_map[name.lower()]]
    return default


def load_dataset(dataset_path: str) -> Dict[str, List[Dict]]:
    """Load and normalize all required sheets from the Excel dataset."""
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(
            f"Dataset file '{dataset_path}' not found. Place it beside app.py."
        )

    sheet_names = ["CPUs", "MBs", "RAMs", "Storage", "GPUs", "PSUs"]
    excel = pd.ExcelFile(dataset_path)
    available = set(excel.sheet_names)
    missing = [s for s in sheet_names if s not in available]
    if missing:
        raise ValueError(f"Missing required sheet(s): {', '.join(missing)}")

    raw = {name: pd.read_excel(dataset_path, sheet_name=name) for name in sheet_names}
    db = {
        "cpu": [],
        "motherboard": [],
        "ram": [],
        "storage": [],
        "gpu": [],
        "psu": [],
    }

    for _, row in raw["CPUs"].iterrows():
        db["cpu"].append(
            {
                "id": safe_text(first_existing(row, ["ID", "cpu_id", "Name", "name", "Model"], "CPU")),
                "name": safe_text(first_existing(row, ["Name", "name", "Model"], "CPU")),
                "price": safe_float(first_existing(row, ["Price", "price_usd", "Cost"], 0)),
                "socket": safe_text(first_existing(row, ["Socket", "socket", "CPU Socket"], "")),
                "tdp": safe_float(first_existing(row, ["TDP", "tdp_watts", "CPU TDP", "Watt"], 65)),
                "cores": safe_float(first_existing(row, ["Cores", "cores", "Core Count"], 4)),
                "integrated_graphics": to_bool(
                    first_existing(
                        row,
                        ["Integrated Graphics", "integrated_graphics", "iGPU", "Has Integrated Graphics"],
                        False,
                    )
                ),
            }
        )

    for _, row in raw["MBs"].iterrows():
        db["motherboard"].append(
            {
                "id": safe_text(first_existing(row, ["ID", "mb_id", "Name", "name", "Model"], "MB")),
                "name": safe_text(first_existing(row, ["Name", "name", "Model"], "MB")),
                "price": safe_float(first_existing(row, ["Price", "price_usd", "Cost"], 0)),
                "socket": safe_text(first_existing(row, ["Socket", "socket", "CPU Socket"], "")),
                "ram_type": safe_text(first_existing(row, ["RAM Type", "ram_type", "Memory Type"], "")),
                "nvme_support": to_bool(
                    first_existing(row, ["NVMe Support", "nvme_support", "M.2 Support", "NVMe"], False)
                ),
                "m2_slots": safe_float(first_existing(row, ["M.2 Slots", "m2_slots", "M2 Slots"], 0)),
                "sata_ports": safe_float(first_existing(row, ["SATA Ports", "sata_ports", "SATA"], 0)),
            }
        )

    for _, row in raw["RAMs"].iterrows():
        db["ram"].append(
            {
                "id": safe_text(first_existing(row, ["ID", "ram_id", "Name", "name", "Model"], "RAM")),
                "name": safe_text(first_existing(row, ["Name", "name", "Model"], "RAM")),
                "price": safe_float(first_existing(row, ["Price", "price_usd", "Cost"], 0)),
                "ram_type": safe_text(first_existing(row, ["RAM Type", "ram_type", "type", "Memory Type"], "")),
                "capacity_gb": safe_float(
                    first_existing(row, ["Capacity (GB)", "capacity_gb", "Capacity", "GB"], 8)
                ),
            }
        )

    for _, row in raw["Storage"].iterrows():
        db["storage"].append(
            {
                "id": safe_text(first_existing(row, ["ID", "storage_id", "Name", "name", "Model"], "ST")),
                "name": safe_text(first_existing(row, ["Name", "name", "Model"], "Storage")),
                "price": safe_float(first_existing(row, ["Price", "price_usd", "Cost"], 0)),
                "type": safe_text(first_existing(row, ["Interface", "interface", "Type", "type"], "")),
                "capacity_gb": safe_float(
                    first_existing(row, ["Capacity (GB)", "capacity_gb", "Capacity", "GB"], 256)
                ),
                "speed": safe_float(
                    first_existing(row, ["Speed", "Read Speed", "Speed (MB/s)", "Read/Write Speed"], 0)
                ),
            }
        )

    for _, row in raw["GPUs"].iterrows():
        db["gpu"].append(
            {
                "id": safe_text(first_existing(row, ["ID", "gpu_id", "Name", "name", "Model"], "GPU")),
                "name": safe_text(first_existing(row, ["Name", "name", "Model"], "GPU")),
                "price": safe_float(first_existing(row, ["Price", "price_usd", "Cost"], 0)),
                "tdp": safe_float(first_existing(row, ["TDP", "tdp_watts", "GPU TDP", "Watt"], 120)),
                "vram_gb": safe_float(first_existing(row, ["VRAM (GB)", "vram_gb", "VRAM", "GB"], 4)),
                "score": safe_float(
                    first_existing(row, ["Performance Score", "Score", "Benchmark"], 0)
                ),
            }
        )

    for _, row in raw["PSUs"].iterrows():
        db["psu"].append(
            {
                "id": safe_text(first_existing(row, ["ID", "psu_id", "Name", "name", "Model"], "PSU")),
                "name": safe_text(first_existing(row, ["Name", "name", "Model"], "PSU")),
                "price": safe_float(first_existing(row, ["Price", "price_usd", "Cost"], 0)),
                "wattage": safe_float(first_existing(row, ["Wattage", "wattage", "Power (W)", "Power"], 450)),
            }
        )

    return db


def initial_state() -> Dict:
    """Create the root state in the state-space tree."""
    return {
        "cpu": None,
        "motherboard": None,
        "ram": None,
        "storage": None,
        "gpu": None,
        "psu": None,
        "total_price": 0.0,
    }


def state_depth(state: Dict) -> int:
    """Return how many component slots are already filled."""
    for idx, key in enumerate(COMPONENT_ORDER):
        if state[key] is None:
            return idx
    return len(COMPONENT_ORDER)


def next_component_key(state: Dict) -> Optional[str]:
    """Determine next component to assign based on required order."""
    depth = state_depth(state)
    if depth >= len(COMPONENT_ORDER):
        return None
    return COMPONENT_ORDER[depth]


def steps_to_goal(state: Dict) -> int:
    """Count selected actions from empty state to current/final state."""
    steps = 0
    for key in COMPONENT_ORDER:
        item = state.get(key)
        if item is None:
            continue
        # Office no-dedicated-GPU option is represented by NO_GPU and should not count as a selected hardware action.
        if key == "gpu" and safe_text(item.get("id", "")) == "NO_GPU":
            continue
        steps += 1
    return steps


def clone_state_with_component(state: Dict, key: str, item: Dict) -> Dict:
    """Create a child state by adding a component."""
    child = dict(state)
    child[key] = item
    child["total_price"] = state["total_price"] + safe_float(item.get("price", 0))
    return child


def is_storage_nvme(storage: Dict) -> bool:
    text = safe_text(storage.get("type", "")).lower()
    return "nvme" in text or "m.2" in text or "m2" in text


def is_storage_sata(storage: Dict) -> bool:
    text = safe_text(storage.get("type", "")).lower()
    return "sata" in text


def gpu_strength_label(gpu: Dict) -> str:
    """Roughly classify GPU strength for purpose constraints."""
    score = safe_float(gpu.get("score", 0))
    vram = safe_float(gpu.get("vram_gb", 0))
    price = safe_float(gpu.get("price", 0))
    if score >= 75 or vram >= 12 or price >= 450:
        return "strong"
    if score >= 35 or vram >= 6 or price >= 220:
        return "mid"
    return "weak"


def is_compatible_partial(state: Dict, budget: float, purpose: str) -> Tuple[bool, str]:
    """Check all constraints that can be validated with currently selected parts."""
    if state["total_price"] > budget:
        return False, "Total price exceeds budget."

    cpu = state["cpu"]
    mb = state["motherboard"]
    ram = state["ram"]
    storage = state["storage"]
    gpu = state["gpu"]
    psu = state["psu"]

    if cpu and mb:
        if safe_text(cpu.get("socket")).lower() != safe_text(mb.get("socket")).lower():
            return False, "CPU socket does not match motherboard socket."

    if mb and ram:
        if safe_text(mb.get("ram_type")).lower() != safe_text(ram.get("ram_type")).lower():
            return False, "RAM type does not match motherboard RAM type."

    if mb and storage:
        has_nvme_path = to_bool(mb.get("nvme_support", False)) or safe_float(mb.get("m2_slots", 0)) > 0
        if is_storage_nvme(storage) and not has_nvme_path:
            return False, "NVMe storage requires motherboard NVMe or M.2 support."
        if is_storage_sata(storage) and safe_float(mb.get("sata_ports", 0)) < 1:
            return False, "SATA storage requires motherboard SATA ports."

    if cpu and gpu and psu:
        required = safe_float(cpu.get("tdp", 0)) + safe_float(gpu.get("tdp", 0)) + 20
        if safe_float(psu.get("wattage", 0)) < required:
            return False, "PSU wattage is insufficient for CPU + GPU + safety buffer."

    # Purpose-specific checks when enough components are known.
    if purpose == "Gaming" and gpu:
        if gpu.get("id") == "NO_GPU":
            return False, "Gaming build requires a dedicated GPU."

    if purpose == "Content Creation":
        if ram and safe_float(ram.get("capacity_gb", 0)) < 32:
            return False, "Content Creation requires RAM >= 32GB."
        if storage and not is_storage_nvme(storage):
            return False, "Content Creation should use NVMe storage."

    if purpose == "AI / ML Workstation" and gpu:
        if gpu.get("id") == "NO_GPU":
            return False, "AI / ML Workstation requires a dedicated GPU."
        if gpu_strength_label(gpu) != "strong" or safe_float(gpu.get("vram_gb", 0)) < 10:
            return False, "AI / ML Workstation requires a strong GPU with high VRAM."

    return True, "Compatible so far."


def is_final_state_valid(state: Dict, budget: float, purpose: str) -> Tuple[bool, str]:
    """Check final constraints once all components are selected."""
    if not all(state.get(k) is not None for k in COMPONENT_ORDER):
        return False, "Incomplete build (missing components)."

    ok, msg = is_compatible_partial(state, budget, purpose)
    if not ok:
        return ok, msg

    cpu = state["cpu"]
    gpu = state["gpu"]
    psu = state["psu"]

    if purpose == "Office / General Use":
        if gpu and gpu.get("id") == "NO_GPU":
            if not to_bool(cpu.get("integrated_graphics", False)):
                return False, "Office build without GPU needs a CPU with integrated graphics."
    elif requires_dedicated_gpu(purpose):
        if not gpu or gpu.get("id") == "NO_GPU":
            return False, "This purpose requires a dedicated GPU."

    if cpu and gpu and psu:
        required = safe_float(cpu.get("tdp", 0)) + safe_float(gpu.get("tdp", 0)) + 20
        if safe_float(psu.get("wattage", 0)) < required:
            return False, "PSU wattage is insufficient."

    return True, "All compatibility constraints satisfied."


def no_gpu_option() -> Dict:
    return {
        "id": "NO_GPU",
        "name": "No Dedicated GPU",
        "price": 0.0,
        "tdp": 0.0,
        "vram_gb": 0.0,
        "score": 0.0,
    }


def requires_dedicated_gpu(purpose: str) -> bool:
    """Purposes that must end with a real discrete GPU (not NO_GPU)."""
    return purpose in {
        "Gaming",
        "Content Creation",
        "AI / ML Workstation",
        "Budget Build",
        "High-End Build",
    }


def performance_sort_key(component_key: str, item: Dict) -> float:
    """Higher is better for tie-breaking after price."""
    if component_key == "cpu":
        return safe_float(item.get("cores", 0))
    if component_key == "gpu":
        return safe_float(item.get("score", 0)) + 0.01 * safe_float(item.get("vram_gb", 0))
    if component_key == "ram":
        return safe_float(item.get("capacity_gb", 0))
    if component_key == "storage":
        return safe_float(item.get("capacity_gb", 0))
    if component_key == "psu":
        return safe_float(item.get("wattage", 0))
    return 0.0


def compatible_items_raw(component_key: str, db: Dict[str, List[Dict]], state: Dict, purpose: str) -> List[Dict]:
    """All DB items for this step that satisfy hardware + purpose hard filters (no ranking cap)."""
    items: List[Dict] = list(db[component_key])

    # Aggressive pruning for Budget Build
    if purpose == "Budget Build":
        if component_key == "cpu":
            items = [i for i in items if safe_float(i.get("price", 0)) <= 200]
        elif component_key == "gpu":
            items = [i for i in items if safe_float(i.get("price", 0)) <= 300]
        elif component_key == "motherboard":
            items = [i for i in items if safe_float(i.get("price", 0)) <= 150]
        elif component_key == "ram":
            items = [i for i in items if safe_float(i.get("capacity_gb", 0)) <= 16]
        else:
            items = [i for i in items if safe_float(i.get("price", 0)) <= 150]

    # High-End Build pruning
    if purpose == "High-End Build":
        if component_key == "cpu":
            items = [i for i in items if safe_float(i.get("price", 0)) >= 350]
        elif component_key == "gpu":
            items = [i for i in items if safe_float(i.get("price", 0)) >= 500]

    if component_key == "motherboard":
        cpu = state.get("cpu")
        if not cpu:
            return []
        cs = safe_text(cpu.get("socket")).lower()
        return [m for m in items if safe_text(m.get("socket")).lower() == cs]

    if component_key == "ram":
        mb = state.get("motherboard")
        if not mb:
            return []
        rt = safe_text(mb.get("ram_type")).lower()
        out = [r for r in items if safe_text(r.get("ram_type")).lower() == rt]
        if purpose in {"Content Creation", "AI / ML Workstation", "High-End Build"}:
            out = [r for r in out if safe_float(r.get("capacity_gb", 0)) >= 32]
        elif purpose == "Gaming":
            out = [r for r in out if safe_float(r.get("capacity_gb", 0)) >= 16]
        elif purpose == "Office / General Use":
            out = [r for r in out if safe_float(r.get("capacity_gb", 0)) <= 16]
        return out

    if component_key == "storage":
        mb = state.get("motherboard")
        if not mb:
            return []
        has_nvme_path = to_bool(mb.get("nvme_support", False)) or safe_float(mb.get("m2_slots", 0)) > 0
        sata_ok = safe_float(mb.get("sata_ports", 0)) >= 1
        out: List[Dict] = []
        for s in items:
            if is_storage_nvme(s) and not has_nvme_path:
                continue
            if is_storage_sata(s) and not sata_ok:
                continue
            out.append(s)
        if purpose == "Content Creation":
            out = [s for s in out if is_storage_nvme(s)]
        elif purpose == "High-End Build":
            out = [s for s in out if is_storage_nvme(s) and safe_float(s.get("capacity_gb", 0)) >= 1000]
        return out

    if component_key == "gpu":
        base = [g for g in items if safe_text(g.get("id", "")) != "NO_GPU"]
        if purpose == "AI / ML Workstation":
            base = [
                g
                for g in base
                if safe_float(g.get("vram_gb", 0)) >= 12
            ]
        elif purpose == "Gaming":
            base = [g for g in base if safe_float(g.get("price", 0)) >= 300 and safe_float(g.get("vram_gb", 0)) >= 8]
        cpu = state.get("cpu")
        if purpose in {"Office / General Use", "Budget Build"}:
            if cpu and to_bool(cpu.get("integrated_graphics", False)):
                return [no_gpu_option()]
            return [g for g in base if safe_float(g.get("price", 0)) <= 150] if purpose == "Office / General Use" else base
        if requires_dedicated_gpu(purpose):
            return base
        return base

    if component_key == "psu":
        cpu = state.get("cpu")
        gpu = state.get("gpu")
        if not cpu or not gpu:
            return []
        required = safe_float(cpu.get("tdp", 0)) + safe_float(gpu.get("tdp", 0)) + 20
        valid_psus = [p for p in items if safe_float(p.get("wattage", 0)) >= required]
        if purpose == "AI / ML Workstation":
            valid_psus = [p for p in valid_psus if safe_float(p.get("wattage", 0)) >= 750]
        elif purpose == "Office / General Use":
            valid_psus = [p for p in valid_psus if safe_float(p.get("wattage", 0)) <= 550]
        return valid_psus

    if component_key == "cpu":
        if purpose == "Gaming":
            items = [c for c in items if safe_float(c.get("cores", 0)) >= 6]
        elif purpose == "Content Creation":
            items = [c for c in items if safe_float(c.get("cores", 0)) >= 12]
        return items

    return items


def rank_expansion_candidates(
    component_key: str,
    items: List[Dict],
    purpose: str,
    budget: float,
    state: Dict,
) -> List[Dict]:
    """Purpose-aware ordering; low budgets prioritize price first, then performance."""
    ranked = list(items)

    def low_budget_tuple(item: Dict):
        return (safe_float(item.get("price", 0)), -performance_sort_key(component_key, item))

    if purpose == "Gaming":
        ranked.sort(key=lambda i: -safe_float(i.get("price", 0)))
        return ranked

    if purpose == "Office / General Use":
        if component_key == "cpu":
            ranked.sort(key=lambda i: (0 if to_bool(i.get("integrated_graphics", False)) else 1, safe_float(i.get("price", 0))))
        else:
            ranked.sort(key=lambda i: safe_float(i.get("price", 0)))
        return ranked

    if purpose == "High-End Build":
        ranked.sort(key=lambda i: -safe_float(i.get("price", 0)))
        return ranked

    if purpose == "Budget Build":
        ranked.sort(key=lambda i: safe_float(i.get("price", 0)))
        return ranked

    if purpose == "Content Creation":
        if component_key == "cpu":
            ranked.sort(key=lambda i: (-safe_float(i.get("cores", 0)), safe_float(i.get("price", 0))))
        elif component_key == "ram":
            ranked.sort(key=lambda i: (-safe_float(i.get("capacity_gb", 0)), safe_float(i.get("price", 0))))
        elif component_key == "storage":
            ranked.sort(key=lambda i: (-safe_float(i.get("speed", 0)), -safe_float(i.get("capacity_gb", 0)), safe_float(i.get("price", 0))))
        else:
            ranked.sort(key=low_budget_tuple)
        return ranked

    if purpose == "AI / ML Workstation":
        if component_key == "gpu":
            ranked.sort(
                key=lambda i: (
                    -safe_float(i.get("vram_gb", 0)),
                    -safe_float(i.get("price", 0))
                )
            )
        elif component_key == "psu":
            ranked.sort(key=lambda i: (-safe_float(i.get("wattage", 0)), -safe_float(i.get("price", 0))))
        elif component_key == "ram":
            ranked.sort(key=lambda i: (-safe_float(i.get("capacity_gb", 0)), -safe_float(i.get("price", 0))))
        else:
            ranked.sort(key=lambda i: -safe_float(i.get("price", 0)))
        return ranked

    if budget <= LOW_BUDGET_THRESHOLD:
        ranked.sort(key=low_budget_tuple)
        return ranked

    ranked.sort(key=low_budget_tuple)
    return ranked


def expansion_candidates(component_key: str, db: Dict[str, List[Dict]], state: Dict, purpose: str, budget: float) -> List[Dict]:
    """Compatibility-pruned list, purpose-ranked; top EXPANSION_CAP (at least 25 when available)."""
    raw = compatible_items_raw(component_key, db, state, purpose)
    if not raw:
        return []
    
    # Early Pruning: Exclude any item that exceeds remaining budget
    current_price = safe_float(state.get("total_price", 0))
    raw = [item for item in raw if current_price + safe_float(item.get("price", 0)) <= budget]

    if component_key == "gpu" and purpose == "Office / General Use":
        cpu = state.get("cpu")
        if cpu and to_bool(cpu.get("integrated_graphics", False)):
            return [no_gpu_option()]
    ranked = rank_expansion_candidates(component_key, raw, purpose, budget, state)
    take = min(len(ranked), EXPANSION_CAP)
    return ranked[:take]


def _partial_assignment_key(state: Dict) -> Tuple:
    return tuple((state.get(k) or {}).get("id") if state.get(k) else None for k in COMPONENT_ORDER)


def _min_gpu_plus_psu(state_up_to_gpu: Dict, db: Dict[str, List[Dict]], purpose: str) -> float:
    """Minimum (gpu price + psu price) from a state whose next slot is GPU (CPU must be set)."""
    gpu_opts = compatible_items_raw("gpu", db, state_up_to_gpu, purpose)
    if not gpu_opts:
        return float("inf")
    best = float("inf")
    for g in gpu_opts:
        st = clone_state_with_component(state_up_to_gpu, "gpu", g)
        psu_opts = compatible_items_raw("psu", db, st, purpose)
        if not psu_opts:
            continue
        min_p = min(safe_float(p.get("price", 0)) for p in psu_opts)
        best = min(best, safe_float(g.get("price", 0)) + min_p)
    return best


def min_finish_cost(
    state: Dict,
    db: Dict[str, List[Dict]],
    purpose: str,
    memo: Optional[Dict[Tuple, float]] = None,
) -> float:
    """Exact minimum spend to complete the build from this partial state (O(small) via problem structure)."""
    if memo is None:
        memo = {}
    mkey = (purpose, _partial_assignment_key(state))
    if mkey in memo:
        return memo[mkey]

    nk = next_component_key(state)
    if nk is None:
        memo[mkey] = 0.0
        return 0.0

    if nk == "psu":
        opts = compatible_items_raw("psu", db, state, purpose)
        if not opts:
            memo[mkey] = float("inf")
            return float("inf")
        v = min(safe_float(p.get("price", 0)) for p in opts)
        memo[mkey] = v
        return v

    if nk == "gpu":
        v = _min_gpu_plus_psu(state, db, purpose)
        memo[mkey] = v
        return v

    if nk == "storage":
        s_opts = compatible_items_raw("storage", db, state, purpose)
        if not s_opts:
            memo[mkey] = float("inf")
            return float("inf")
        min_s = min(safe_float(s.get("price", 0)) for s in s_opts)
        cheapest = min(s_opts, key=lambda s: safe_float(s.get("price", 0)))
        st2 = clone_state_with_component(state, "storage", cheapest)
        v = min_s + min_finish_cost(st2, db, purpose, memo)
        memo[mkey] = v
        return v

    if nk == "ram":
        r_opts = compatible_items_raw("ram", db, state, purpose)
        if not r_opts:
            memo[mkey] = float("inf")
            return float("inf")
        min_r = min(safe_float(r.get("price", 0)) for r in r_opts)
        cheapest = min(r_opts, key=lambda r: safe_float(r.get("price", 0)))
        st2 = clone_state_with_component(state, "ram", cheapest)
        v = min_r + min_finish_cost(st2, db, purpose, memo)
        memo[mkey] = v
        return v

    if nk == "motherboard":
        m_opts = compatible_items_raw("motherboard", db, state, purpose)
        if not m_opts:
            memo[mkey] = float("inf")
            return float("inf")
        best = float("inf")
        for m in m_opts:
            st2 = clone_state_with_component(state, "motherboard", m)
            rest = min_finish_cost(st2, db, purpose, memo)
            if rest == float("inf"):
                continue
            best = min(best, safe_float(m.get("price", 0)) + rest)
        memo[mkey] = best
        return best

    if nk == "cpu":
        c_opts = compatible_items_raw("cpu", db, state, purpose)
        if not c_opts:
            memo[mkey] = float("inf")
            return float("inf")
        best = float("inf")
        for c in c_opts:
            st2 = clone_state_with_component(state, "cpu", c)
            rest = min_finish_cost(st2, db, purpose, memo)
            if rest == float("inf"):
                continue
            best = min(best, safe_float(c.get("price", 0)) + rest)
        memo[mkey] = best
        return best

    memo[mkey] = float("inf")
    return float("inf")


def cheapest_possible_remaining(
    state: Dict,
    db: Dict[str, List[Dict]],
    purpose: str,
    memo: Optional[Dict[Tuple, float]] = None,
) -> float:
    """Minimum spend still required to finish from this state (for debugging)."""
    return min_finish_cost(state, db, purpose, memo)


def optimistic_completion_lower_bound(
    child: Dict,
    db: Dict[str, List[Dict]],
    purpose: str,
    memo: Optional[Dict[Tuple, float]] = None,
) -> float:
    """Lower bound on any full build that extends `child` (current total + cheapest legal completion)."""
    if memo is None:
        memo = {}
    return safe_float(child.get("total_price", 0)) + min_finish_cost(child, db, purpose, memo)


def serialize_component(item: Optional[Dict]) -> Optional[Dict]:
    """Return lightweight component data for API responses."""
    if item is None:
        return None
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "price": round(safe_float(item.get("price", 0)), 2),
    }


def serialize_state(state: Dict) -> Dict:
    """Convert state to required response format."""
    return {
        "cpu": serialize_component(state["cpu"]),
        "motherboard": serialize_component(state["motherboard"]),
        "ram": serialize_component(state["ram"]),
        "storage": serialize_component(state["storage"]),
        "gpu": serialize_component(state["gpu"]),
        "psu": serialize_component(state["psu"]),
        "total_price": round(safe_float(state["total_price"]), 2),
    }


def _finite_or_none(value: float):
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), 2)


def search_build(db: Dict[str, List[Dict]], budget: float, purpose: str, algorithm: str) -> Dict:
    """Run the requested algorithm on the build state-space; no cross-algorithm fallback."""
    start = initial_state()
    explored = 0
    found_states: List[Dict] = []
    counter = 0
    mfc_memo: Dict[Tuple, float] = {}

    started = time.perf_counter()
    stop_reason = ""
    max_cap = int(MAX_EXPLORED_STATES.get(algorithm, 200_000))

    if algorithm == "BFS":
        frontier = deque([start])
        visited = set()
        while frontier:
            state = frontier.popleft()
            state_key = _partial_assignment_key(state)
            if state_key in visited:
                continue
            visited.add(state_key)
            
            if explored >= max_cap:
                stop_reason = f"Safety stop: reached max_explored_states={max_cap}."
                break
            explored += 1
            key = next_component_key(state)
            if key is None:
                ok, _ = is_final_state_valid(state, budget, purpose)
                if ok:
                    found_states.append(state)
                    if len(found_states) >= MAX_RESULTS:
                        stop_reason = f"Stopped after finding {MAX_RESULTS} valid builds."
                        break
                continue

            for item in expansion_candidates(key, db, state, purpose, budget):
                child = clone_state_with_component(state, key, item)
                if child["total_price"] > budget:
                    continue
                if optimistic_completion_lower_bound(child, db, purpose, mfc_memo) > budget:
                    continue
                ok, _ = is_compatible_partial(child, budget, purpose)
                if ok:
                    frontier.append(child)

    elif algorithm == "DFS":
        frontier = [start]
        visited = set()
        while frontier:
            state = frontier.pop()
            state_key = _partial_assignment_key(state)
            if state_key in visited:
                continue
            visited.add(state_key)
            
            if explored >= max_cap:
                stop_reason = f"Safety stop: reached max_explored_states={max_cap}."
                break
            explored += 1
            key = next_component_key(state)
            if key is None:
                ok, _ = is_final_state_valid(state, budget, purpose)
                if ok:
                    found_states.append(state)
                    if len(found_states) >= MAX_RESULTS:
                        stop_reason = f"Stopped after finding {MAX_RESULTS} valid builds."
                        break
                continue

            candidates = expansion_candidates(key, db, state, purpose, budget)
            for item in reversed(candidates):
                child = clone_state_with_component(state, key, item)
                if child["total_price"] > budget:
                    continue
                if optimistic_completion_lower_bound(child, db, purpose, mfc_memo) > budget:
                    continue
                ok, _ = is_compatible_partial(child, budget, purpose)
                if ok:
                    frontier.append(child)

    elif algorithm == "UCS":
        frontier = []
        heapq.heappush(frontier, (0.0, counter, start))
        counter += 1
        visited = set()
        while frontier:
            _, _, state = heapq.heappop(frontier)
            state_key = _partial_assignment_key(state)
            if state_key in visited:
                continue
            visited.add(state_key)
            
            if explored >= max_cap:
                stop_reason = f"Safety stop: reached max_explored_states={max_cap}."
                break
            explored += 1
            key = next_component_key(state)
            if key is None:
                ok, _ = is_final_state_valid(state, budget, purpose)
                if ok:
                    found_states.append(state)
                    if len(found_states) >= MAX_RESULTS:
                        stop_reason = f"Stopped after finding {MAX_RESULTS} valid builds."
                        break
                continue

            for item in expansion_candidates(key, db, state, purpose, budget):
                child = clone_state_with_component(state, key, item)
                if child["total_price"] > budget:
                    continue
                if optimistic_completion_lower_bound(child, db, purpose, mfc_memo) > budget:
                    continue
                ok, _ = is_compatible_partial(child, budget, purpose)
                if not ok:
                    continue
                heapq.heappush(frontier, (child["total_price"], counter, child))
                counter += 1
    elif algorithm == "A*":
        frontier = []
        h0 = min_finish_cost(start, db, purpose, mfc_memo)
        if not math.isfinite(h0):
            h0 = 0.0
        heapq.heappush(frontier, (h0, 0.0, counter, start))
        counter += 1
        visited = set()
        while frontier:
            _, g_cost, _, state = heapq.heappop(frontier)
            state_key = _partial_assignment_key(state)
            if state_key in visited:
                continue
            visited.add(state_key)
            
            if explored >= max_cap:
                stop_reason = f"Safety stop: reached max_explored_states={max_cap}."
                break
            explored += 1
            key = next_component_key(state)
            if key is None:
                ok, _ = is_final_state_valid(state, budget, purpose)
                if ok:
                    found_states.append(state)
                    if len(found_states) >= MAX_RESULTS:
                        stop_reason = f"Stopped after finding {MAX_RESULTS} valid builds."
                        break
                continue

            for item in expansion_candidates(key, db, state, purpose, budget):
                child = clone_state_with_component(state, key, item)
                if child["total_price"] > budget:
                    continue
                if optimistic_completion_lower_bound(child, db, purpose, mfc_memo) > budget:
                    continue
                ok, _ = is_compatible_partial(child, budget, purpose)
                if not ok:
                    continue
                new_g = child["total_price"]
                h = min_finish_cost(child, db, purpose, mfc_memo)
                if not math.isfinite(h):
                    h = 0.0
                f = new_g + h
                heapq.heappush(frontier, (f, new_g, counter, child))
                counter += 1
    else:
        return {
            "success": False,
            "message": "Invalid algorithm selected.",
            "algorithm": algorithm,
            "explored_states": 0,
            "search_time_ms": 0.0,
            "search_time": 0.0,
            "path_depth": 0,
            "steps_to_goal": 0,
            "results_count": 0,
            "top_builds": [],
            "stopped_reason": "Invalid algorithm.",
            "max_explored_states": max_cap,
            "remaining_budget": _finite_or_none(budget),
            "cheapest_possible_remaining": _finite_or_none(cheapest_possible_remaining(start, db, purpose)),
        }

    elapsed = (time.perf_counter() - started) * 1000

    valid_found = []
    for st in found_states:
        ok, _ = is_final_state_valid(st, budget, purpose)
        if ok:
            valid_found.append(st)

    root_cheapest = cheapest_possible_remaining(start, db, purpose, mfc_memo)

    if not valid_found:
        message = "No valid build found for this budget and purpose."
        if stop_reason:
            message = f"{message} {stop_reason}".strip()
        return {
            "success": False,
            "message": message,
            "algorithm": algorithm,
            "explored_states": explored,
            "search_time_ms": round(elapsed, 2),
            "search_time": round(elapsed, 2),
            "path_depth": 0,
            "steps_to_goal": 0,
            "results_count": 0,
            "top_builds": [],
            "stopped_reason": stop_reason or "exhausted_search_space",
            "max_explored_states": max_cap,
            "remaining_budget": _finite_or_none(budget),
            "cheapest_possible_remaining": _finite_or_none(root_cheapest),
        }

    valid_found = sorted(valid_found, key=lambda s: safe_float(s.get("total_price", 0)))[:MAX_RESULTS]
    best_state = valid_found[0]
    _, compatibility = is_final_state_valid(best_state, budget, purpose)
    top_builds = [
        {
            "selected_components": serialize_state(st),
            "total_price": round(safe_float(st.get("total_price", 0)), 2),
            "compatibility_status": is_final_state_valid(st, budget, purpose)[1],
            "path_depth": state_depth(st),
            "steps_to_goal": steps_to_goal(st),
        }
        for st in valid_found
    ]

    remaining = max(0.0, budget - safe_float(best_state.get("total_price", 0)))

    return {
        "success": True,
        "selected_components": serialize_state(best_state),
        "total_price": round(best_state["total_price"], 2),
        "compatibility_status": compatibility,
        "algorithm": algorithm,
        "explored_states": explored,
        "search_time_ms": round(elapsed, 2),
        "search_time": round(elapsed, 2),
        "path_depth": state_depth(best_state),
        "steps_to_goal": steps_to_goal(best_state),
        "results_count": len(top_builds),
        "top_builds": top_builds,
        "message": stop_reason if stop_reason else "Build(s) found.",
        "stopped_reason": stop_reason or "success",
        "max_explored_states": max_cap,
        "remaining_budget": _finite_or_none(remaining),
        "cheapest_possible_remaining": 0.0,
    }


def get_dataset_path() -> str:
    """Resolve dataset path in project root."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), DATASET_FILE)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def run_search():
    payload = request.get_json(silent=True) or {}

    budget = safe_float(payload.get("budget", 0), 0)
    purpose = safe_text(payload.get("purpose", ""))
    algorithm = safe_text(payload.get("algorithm", "")).upper()

    if budget <= 0:
        return jsonify({"success": False, "message": "Budget must be greater than 0."}), 400
    if purpose not in PURPOSES:
        return jsonify({"success": False, "message": "Invalid purpose selected."}), 400
    if algorithm not in ALGORITHMS:
        return jsonify({"success": False, "message": "Invalid algorithm selected."}), 400

    try:
        db = load_dataset(get_dataset_path())
    except Exception as exc:  # Keep explicit error details for assignment debugging.
        return jsonify({"success": False, "message": str(exc)}), 500

    result = search_build(db, budget, purpose, algorithm)
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)
