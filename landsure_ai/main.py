import json
from pathlib import Path

from engine import analyze_records


def load_records(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def main():
    records_path = Path(__file__).with_name("sample_records.json")
    records = load_records(records_path)
    findings = analyze_records(records)

    print("LandSure AI - Land Record Verification Demo")
    print("=" * 52)
    print(f"Total records checked: {len(findings)}")

    for item in findings:
        print(f"\nRecord ID: {item['record_id']}")
        print(f"Owner: {item['owner_name']}")
        print(f"District: {item['district']}")
        print(f"Area: {item['area_ha']} ha")
        print(f"Risk Score: {item['risk_score']}/100")
        print(f"Risk Level: {item['risk_level']}")

        if item["flags"]:
            print("Flags:")
            for flag in item["flags"]:
                print(f"  - {flag}")
        else:
            print("Flags: None")

    print("\nRecommended action: Manual review for medium/high risk records.")


if __name__ == "__main__":
    main()
