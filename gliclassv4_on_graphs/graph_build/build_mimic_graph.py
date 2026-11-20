"""Build mimic-graph.json from the 12-table subset using the join rules declared below.

Run from the project root: uv run python -m graph_build.build_mimic_graph
Keeps source values and identities; includes only joins between retained tables.
Existing output files are never overwritten. No database connection is used.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from graph_build.process_mimic import DEFAULT_OUTPUT as DEFAULT_SUBSET
from graph_build.process_mimic import PROJECT, TABLE_LABELS, sha256, write_json


# Each join links a child row to one parent row by exact, nonempty
# (child column, parent column) pairs. Children map to their relationship type.
# J numbers follow the original 31-table join design, so gaps are expected.
JOIN_RULES = [
    {"id": "J01", "parent": "hosp/patients", "parent_to_child": True,
     "pairs": [["subject_id", "subject_id"]],
     "children": {"hosp/admissions": "HAD_ADMISSION"}},
    {"id": "J02", "parent": "hosp/patients", "parent_to_child": True,
     "pairs": [["subject_id", "subject_id"]],
     "children": {
         "hosp/diagnoses_icd": "HAD_RECORDED_DIAGNOSIS",
         "hosp/emar": "HAD_MEDICATION_RECORD",
         "hosp/emar_detail": "HAD_MEDICATION_DETAIL",
         "hosp/labevents": "HAD_LAB_TEST",
         "hosp/pharmacy": "HAD_PHARMACY_ORDER",
         "hosp/prescriptions": "WAS_PRESCRIBED",
         "hosp/procedures_icd": "UNDERWENT",
     }},
    {"id": "J04", "parent": "hosp/admissions", "parent_to_child": True,
     "pairs": [["subject_id", "subject_id"], ["hadm_id", "hadm_id"]],
     "children": {
         "hosp/diagnoses_icd": "RECORDED_DIAGNOSIS",
         "hosp/emar": "INCLUDED_MEDICATION_EVENT",
         "hosp/labevents": "INCLUDED_LAB_TEST",
         "hosp/pharmacy": "INCLUDED_PHARMACY_ORDER",
         "hosp/prescriptions": "INCLUDED_PRESCRIPTION",
         "hosp/procedures_icd": "INCLUDED_PROCEDURE",
     }},
    {"id": "J06", "parent": "hosp/pharmacy", "parent_to_child": True,
     "pairs": [["subject_id", "subject_id"], ["pharmacy_id", "pharmacy_id"]],
     "children": {"hosp/prescriptions": "FOR_PRESCRIPTION"}},
    {"id": "J07", "parent": "hosp/emar", "parent_to_child": True,
     "pairs": [["subject_id", "subject_id"], ["emar_id", "emar_id"]],
     "children": {"hosp/emar_detail": "HAS_DOSE_DETAIL"}},
    {"id": "J09", "parent": "hosp/pharmacy", "parent_to_child": False,
     "pairs": [["subject_id", "subject_id"], ["pharmacy_id", "pharmacy_id"]],
     "children": {"hosp/emar": "REFERENCES_PHARMACY_ORDER"}},
    {"id": "J10", "parent": "hosp/pharmacy", "parent_to_child": False,
     "pairs": [["subject_id", "subject_id"], ["pharmacy_id", "pharmacy_id"]],
     "children": {"hosp/emar_detail": "REFERENCES_PHARMACY_ORDER"}},
    {"id": "J14", "parent": "hosp/d_icd_diagnoses", "parent_to_child": False,
     "pairs": [["icd_code", "icd_code"], ["icd_version", "icd_version"]],
     "children": {"hosp/diagnoses_icd": "HAS_DIAGNOSIS_CODE"}},
    {"id": "J15", "parent": "hosp/d_icd_procedures", "parent_to_child": False,
     "pairs": [["icd_code", "icd_code"], ["icd_version", "icd_version"]],
     "children": {"hosp/procedures_icd": "HAS_PROCEDURE_CODE"}},
    {"id": "J16", "parent": "hosp/d_labitems", "parent_to_child": False,
     "pairs": [["itemid", "itemid"]],
     "children": {"hosp/labevents": "MEASURES"}},
]


def display_name(label, values, source_row):
    if label == "Patient":
        return f"Patient {values['subject_id']}"
    if label == "Admission":
        return f"Admission {values['hadm_id']}"
    for column in ("long_title", "label", "medication", "drug", "product_description"):
        if values.get(column):
            return values[column]
    return f"{label} {source_row}"


def build_graph(subset):
    tables, metadata = subset["tables"], subset["metadata"]
    if set(tables) != set(TABLE_LABELS) or metadata["table_labels"] != TABLE_LABELS:
        raise ValueError("Subset must contain the agreed tables and labels.")
    nodes, by_table = [], {}
    for table_name, label in TABLE_LABELS.items():
        by_table[table_name] = []
        for record in tables[table_name]["rows"]:
            values, row = record["values"], record["source_row"]
            node = {
                "id": f"mimic-iv-demo:{metadata['dataset_version']}:{table_name}:{row}",
                "type": label,
                "name": display_name(label, values, row),
                "properties": {**values, "_source_table": table_name, "_source_row": row},
            }
            nodes.append(node)
            by_table[table_name].append(node)
    if len({n["id"] for n in nodes}) != len(nodes):
        raise ValueError("Duplicate source record identities.")

    relations, join_rules = [], []
    for rule in JOIN_RULES:
        join_id, pairs = rule["id"], rule["pairs"]
        parents = {}
        for parent in by_table[rule["parent"]]:
            key = tuple(parent["properties"][p] for _, p in pairs)
            if all(key):
                if key in parents:
                    raise ValueError(f"Ambiguous parent key for join {join_id}: {key}")
                parents[key] = parent
        for table_name, relation_type in rule["children"].items():
            blank_key_rows = 0
            for child in by_table[table_name]:
                key = tuple(child["properties"][c] for c, _ in pairs)
                if not all(key):
                    blank_key_rows += 1
                    continue
                if key not in parents:
                    raise ValueError(f"Missing parent for join {join_id}: {child['id']}")
                parent = parents[key]
                source, target = (parent, child) if rule["parent_to_child"] else (child, parent)
                identity = json.dumps([source["id"], relation_type, target["id"]])
                properties = {"_join_rule": join_id}
                child_admission = child["properties"].get("hadm_id")
                parent_admission = parent["properties"].get("hadm_id")
                if child_admission and parent_admission and child_admission != parent_admission:
                    properties["_admission_id_mismatch"] = True
                relations.append({
                    "id": "mimic-rel:" + hashlib.sha256(identity.encode()).hexdigest(),
                    "source": source["id"], "type": relation_type, "target": target["id"],
                    "properties": properties,
                })
                if join_id in ("J14", "J15", "J16"):
                    child["name"] = parent["name"]
            join_rules.append({"parent": rule["parent"], "pairs": pairs,
                               "parent_to_child": rule["parent_to_child"], "id": join_id,
                               "type": relation_type, "children": [table_name],
                               "blank_key_rows": blank_key_rows})
    if len({r["id"] for r in relations}) != len(relations):
        raise ValueError("Duplicate relationships.")

    return {
        "metadata": {
            "title": "MIMIC decision graph — four patients, 12 tables",
            "graph_id": "mimic_decision_12tables_v2",
            "relationship_vocabulary_version": "v3",
            "format": "mimic_decision.graph.v1",
            "synthetic": False,
            **{key: metadata[key] for key in
               ("dataset", "dataset_version", "source_url", "license", "patient_ids")},
            "schema_file": "mimic-schema.json",
            "table_labels": TABLE_LABELS,
            "source_files": {name: {"file": table["source_file"], "sha256": table["source_sha256"]}
                             for name, table in tables.items()},
            "values": "Original CSV strings, including blanks and leading zeros; one node per source row.",
            "names": "Display text from source fields; Diagnosis/Procedure use linked code descriptions; LabEvent uses its LabItem label.",
            "joins": "Exact nonempty keys only; blank_key_rows counts child rows left unlinked because a key is blank. _admission_id_mismatch=true records a disagreement between nonempty endpoint admission IDs.",
            "join_id_convention": "J numbers follow the original 31-table join design, so gaps are expected; a join has a separate typed declaration for each child table.",
            "join_rules": join_rules,
            "summary": {
                "nodes": len(nodes), "relations": len(relations),
                "node_counts": dict(sorted(Counter(n["type"] for n in nodes).items())),
                "relation_counts": dict(sorted(Counter(r["type"] for r in relations).items())),
            },
        },
        "nodes": nodes,
        "relations": relations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset", type=Path, default=DEFAULT_SUBSET)
    parser.add_argument("--output", type=Path, default=PROJECT / "mimic-graph.json")
    args = parser.parse_args()
    if args.output.suffix != ".json" or args.output.exists():
        parser.error("Choose a new .json output path; existing files are preserved.")
    try:
        graph = build_graph(json.loads(args.subset.read_text()))
        graph["metadata"].update({
            "source_json": args.subset.resolve().relative_to(PROJECT).as_posix(),
            "source_sha256": sha256(args.subset),
        })
        write_json(graph, args.output.resolve(), overwrite=False)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Graph generation failed: {error}\n")
    print(json.dumps(graph["metadata"]["summary"], indent=2))


if __name__ == "__main__":
    main()
