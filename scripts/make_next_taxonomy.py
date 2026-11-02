"""Write a synthetic "next" taxonomy release for rehearsing an upgrade: the current release with 5 leaves renamed,
2 split into subcategories and 1 deleted, chosen among leaves that hold enriched products so the upgrade has
something to move.

    uv run python scripts/make_next_taxonomy.py        # -> build/taxonomy/2021-09-21-next.txt (+ .sha256)
"""

import hashlib
from pathlib import Path

from shelfsense_api.settings import settings
from shelfsense_api.taxonomy import VERSION_HEADER

REPO = Path(__file__).resolve().parents[1]
RENAMES = {
    100: "Backpacks & Daypacks",
    3809: "Water Bottles & Flasks",
    543626: "Over-Ear & On-Ear Headphones",
    662: "Frying Pans & Skillets",
    3640: "Exercise Mats",
}
SPLITS = {
    187: [(9900001, "Hiking Boots"), (9900002, "Running & Trail Shoes"), (9900003, "Casual Shoes")],
    5598: [(9900004, "Rain Jackets"), (9900005, "Insulated Jackets")],
}
DELETES = {6250}


def main() -> None:
    source = REPO / "data" / "taxonomy" / f"{settings.taxonomy_version}.txt"
    version = f"{settings.taxonomy_version}-next"
    lines = source.read_text(encoding="utf-8").splitlines()
    out = [f"{VERSION_HEADER}{version}"]
    renamed_paths: dict[str, str] = {}
    for line in lines[1:]:
        node_id_text, _, path = line.partition(" - ")
        node_id = int(node_id_text)
        if node_id in DELETES:
            continue
        for old, new in renamed_paths.items():  # descendants of a renamed node follow it
            if path.startswith(old + " > "):
                path = new + path[len(old):]
        if node_id in RENAMES:
            new_path = " > ".join([*path.split(" > ")[:-1], RENAMES[node_id]])
            renamed_paths[path] = new_path
            path = new_path
        out.append(f"{node_id} - {path}")
        for child_id, name in SPLITS.get(node_id, []):  # children right after their parent: parents load first
            out.append(f"{child_id} - {path} > {name}")
    target = REPO / "build" / "taxonomy" / f"{version}.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(out) + "\n", encoding="utf-8")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_name(target.name + ".sha256").write_text(f"{digest}  {target.name}\n")
    print(f"{target}: {len(out) - 1} nodes ({len(RENAMES)} renamed, {len(SPLITS)} split, {len(DELETES)} deleted)")


if __name__ == "__main__":
    main()
