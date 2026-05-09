from app import load_dataset, get_dataset_path, search_build

db = load_dataset(get_dataset_path())
cases = [
    (1500, "Gaming", "BFS"),
    (1500, "Gaming", "DFS"),
    (1500, "Gaming", "UCS"),
    (1500, "Gaming", "A*"),
    (1500, "Office / General Use", "BFS"),
    (2500, "Content Creation", "DFS"),
    (3000, "AI / ML Workstation", "UCS"),
    (4000, "High-End Build", "A*"),
]
for budget, purpose, algo in cases:
    r = search_build(db, budget, purpose, algo)
    ok = r["success"]
    tp = r.get("total_price")
    print(
        f"{algo:4} {purpose[:24]:24} budget={budget} success={ok} price={tp} "
        f"explored={r.get('explored_states')} stop={r.get('stopped_reason')}"
    )
    if not ok:
        print("  msg:", r.get("message"))
