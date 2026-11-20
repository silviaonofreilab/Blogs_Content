"""Extract the four MIMIC demo patients from 12 hospital tables.

Run from the project root: uv run python -m graph_build.process_mimic
Preserves source strings, row order and duplicates. Output is a source subset.
Existing outputs are refused.
"""

import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile

PROJECT = Path(__file__).resolve().parent.parent
RAW = PROJECT / "data" / "raw"
DEFAULT_SOURCE = RAW / "mimic-iv-clinical-database-demo-2.2"
PATIENTS = ("10000032", "10001217", "10001725", "10002495")


TABLE_LABELS = {
    "hosp/admissions": "Admission",
    "hosp/d_icd_diagnoses": "DiagnosisCode",
    "hosp/d_icd_procedures": "ProcedureCode",
    "hosp/d_labitems": "LabItem",
    "hosp/diagnoses_icd": "Diagnosis",
    "hosp/emar": "MedAdmin",
    "hosp/emar_detail": "MedAdminDetail",
    "hosp/labevents": "LabEvent",
    "hosp/patients": "Patient",
    "hosp/pharmacy": "PharmacyOrder",
    "hosp/prescriptions": "Prescription",
    "hosp/procedures_icd": "Procedure",
}
LOOKUPS = {
    "hosp/d_icd_diagnoses": ("hosp/diagnoses_icd", ("icd_code", "icd_version")),
    "hosp/d_icd_procedures": ("hosp/procedures_icd", ("icd_code", "icd_version")),
    "hosp/d_labitems": ("hosp/labevents", ("itemid",)),
}
DEFAULT_OUTPUT = PROJECT / "data/subsets/mimic_decision_4patients_12tables.json"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def open_csv(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    return opener(path, "rt", encoding="utf-8", newline="")


def read_table(path: Path, source: Path, checksum: str, select) -> dict:
    rows = []
    source_count = 0
    with open_csv(path) as stream:
        reader = csv.DictReader(stream, strict=True)
        columns = reader.fieldnames
        if not columns or len(columns) != len(set(columns)):
            raise ValueError(f"Missing or duplicate column names: {path}")
        for source_count, row in enumerate(reader, start=1):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Malformed CSV record {source_count}: {path}")
            if select(row):
                rows.append({"source_row": source_count, "values": row})
    return {
        "source_file": str(path.relative_to(source)),
        "source_sha256": checksum,
        "columns": columns,
        "source_row_count": source_count,
        "row_count": len(rows),
        "rows": rows,
    }


def write_json(document: dict, output: Path, overwrite: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=output.parent, encoding="utf-8",
                                         prefix=".mimic_subset_", suffix=".tmp",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        if overwrite:
            os.replace(temporary, output)
        else:
            os.link(temporary, output)  # Atomic publication, refuses an existing output.
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def extract(source: Path) -> dict:
    manifest = source / "SHA256SUMS.txt"
    expected = {name: digest for digest, name in
                (line.split(maxsplit=1) for line in manifest.read_text().splitlines()
                 if line.strip())}
    files, checksums = {}, {}
    for name in TABLE_LABELS:
        paths = [source / f"{name}{suffix}" for suffix in (".csv", ".csv.gz")]
        paths = [path for path in paths if path.is_file()]
        if len(paths) != 1:
            raise ValueError(f"Expected one CSV or gzip source for {name}")
        path = paths[0]
        digest = sha256(path)
        if digest != expected.get(str(path.relative_to(source))):
            raise ValueError(f"Source checksum missing or mismatched: {name}")
        files[name], checksums[name] = path, digest

    def read(name, select):
        return read_table(files[name], source, checksums[name], select)

    selected = set(PATIENTS)
    tables = {name: read(name, lambda row: row["subject_id"] in selected)
              for name in TABLE_LABELS if name not in LOOKUPS}
    present = {record["values"]["subject_id"] for record in tables["hosp/patients"]["rows"]}
    if present != selected:
        raise ValueError(f"Patients absent from source: {sorted(selected - present)}")
    for name, (referrer, columns) in LOOKUPS.items():
        required = {tuple(record["values"][column] for column in columns)
                    for record in tables[referrer]["rows"]}
        required = {key for key in required if all(key)}
        table = read(name, lambda row: tuple(row[column] for column in columns) in required)
        found = {tuple(record["values"][column] for column in columns)
                 for record in table["rows"]}
        if required - found:
            raise ValueError(f"Unmatched lookup keys in {name}: {sorted(required - found)}")
        tables[name] = table
    for name, table in tables.items():
        table["label"] = TABLE_LABELS[name]
    return {
        "metadata": {
            "format": "mimic_decision.raw_subset.12tables.v1",
            "dataset": "MIMIC-IV Clinical Database Demo", "dataset_version": "2.2",
            "source_url": "https://physionet.org/content/mimic-iv-demo/2.2/",
            "license": "ODbL-1.0",
            "license_url": "https://physionet.org/files/mimic-iv-demo/2.2/LICENSE.txt",
            "source_manifest_sha256": sha256(manifest),
            "patient_ids": list(PATIENTS), "table_labels": TABLE_LABELS,
            "selection": "Four subject_ids; only exact referenced ICD code/version and lab item keys.",
            "preservation": "Original CSV strings, empty cells, columns, row order and repeated rows.",
            "source_row": "One-based CSV data-record index, excluding the header.",
            "summary": {"tables": len(tables), "rows": sum(t["row_count"] for t in tables.values())},
        },
        "tables": {name: tables[name] for name in TABLE_LABELS},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if output.is_relative_to(source) or output.is_relative_to(RAW.resolve()):
        parser.error("Output must be outside the raw source directory.")
    if output.suffix != ".json" or output.exists():
        parser.error("Choose a new .json output path; existing files are preserved.")
    try:
        document = extract(source)
        write_json(document, output, overwrite=False)
    except (OSError, EOFError, ValueError, csv.Error, KeyError) as error:
        parser.exit(1, f"Extraction failed: {error}\n")
    print(f"Wrote {output}")
    print(json.dumps(document["metadata"]["summary"]))


if __name__ == "__main__":
    main()
