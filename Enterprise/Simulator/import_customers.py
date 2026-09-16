"""Generate realistic synthetic customers or import a CSV into the local CRM."""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from urllib.request import Request, urlopen

CRM_IMPORT_URL = "http://127.0.0.1:8001/api/customers/bulk"
DEFAULT_CSV = Path(__file__).parent / "data" / "customers.csv"

FIRST_NAMES = [
    "Amara", "Mateo", "Priya", "Jonas", "Leila", "Noah", "Sofia", "Darius",
    "Elena", "Hana", "Lucas", "Maya", "Nadia", "Theo", "Aisha", "Rafael",
    "Zara", "Owen", "Fatima", "Elias", "Clara", "Arjun", "Mila", "Andre",
    "Yara", "Samuel", "Ines", "Kofi", "Lina", "Marco", "Nia", "David",
    "Aya", "Julian", "Mei", "Malik", "Freya", "Tomas", "Sana", "Emil",
    "Camila", "Ibrahim", "Grace", "Kenji", "Amina", "Leo", "Valentina", "Ethan",
    "Mariam", "Hugo", "Anika", "Rohan", "Isla", "Daniel", "Sienna", "Omar",
    "Nora", "Gabriel", "Laila", "Victor", "Chloe", "Samir",
]
LAST_NAMES = [
    "Okafor", "Silva", "Nair", "Berg", "Haddad", "Kim", "Petrov", "Reed",
    "Rossi", "Tanaka", "Mensah", "Thompson", "Chen", "Williams", "Patel", "Garcia",
    "Kowalski", "Laurent", "Muller", "Santos", "Andersson", "Novak", "Bennett", "Mori",
    "Alvarez", "Nielsen", "Khan", "Dubois", "Morgan", "Sato", "Adeyemi", "Fischer",
    "Costa", "Kaur", "Lindberg", "Martin", "Bianchi", "Ibrahim", "Evans", "Rahman",
    "Schmidt", "Young", "Pereira", "Johansson", "Wilson", "Hernandez", "Lee", "Brown",
    "Davis", "Osei", "Foster", "Moreau", "Singh", "Taylor", "Mendes", "Ali",
    "Sullivan", "Yamamoto", "Clarke", "Wright", "Keller", "Bouchard",
]
MIDDLE_NAMES = [
    "Alex", "Avery", "Blair", "Cameron", "Casey", "Drew", "Eden", "Ellis",
    "Emery", "Finley", "Hayden", "Jamie", "Jordan", "Kai", "Kendall", "Lane",
    "Logan", "Morgan", "Parker", "Quinn", "Reese", "Riley", "Robin", "Rowan",
    "Sage", "Sawyer", "Shane", "Skyler", "Taylor", "Arden", "Bailey", "Brooklyn",
    "Charlie", "Dakota", "Devon", "Harley", "Jesse", "Kelsey", "Marley", "Micah",
    "Nico", "Payton", "River", "Shiloh", "Sydney", "Tatum", "Winter", "Adrian",
    "Emerson", "Everett", "Harper", "Jules", "Lennox", "Marlowe", "Phoenix", "Remy",
    "Sterling", "Valen", "Wren", "Zion",
]
LOCATIONS = [("San Francisco", "US"), ("Sao Paulo", "BR"), ("Mumbai", "IN"), ("Stockholm", "SE"), ("Paris", "FR"), ("Seoul", "KR"), ("Berlin", "DE"), ("Chicago", "US"), ("Rome", "IT"), ("Tokyo", "JP"), ("Accra", "GH"), ("New York", "US")]
CHANNELS = ["email", "sms", "push"]


def email_slug(value: str) -> str:
    return "-".join(value.lower().split())


def generated_customers(count: int, seed: int) -> list[dict[str, str]]:
    randomizer = random.Random(seed)
    customers = []
    for index in range(count):
        first_name = f"{randomizer.choice(FIRST_NAMES)} {randomizer.choice(MIDDLE_NAMES)}"
        last_name = randomizer.choice(LAST_NAMES)
        city, country = randomizer.choice(LOCATIONS)
        customers.append(
            {
                "first_name": first_name,
                "last_name": last_name,
                "email": f"{email_slug(first_name)}.{email_slug(last_name)}.{index + 1}@customer360.test",
                "phone": f"+1-555-{index // 1000 + 1:03d}-{index % 1000:04d}",
                "status": randomizer.choices(["active", "inactive"], weights=[92, 8])[0],
                "age_group": randomizer.choice(["18-24", "25-34", "35-44", "45-54", "55-64"]),
                "city": city,
                "country": country,
                "preferred_channel": randomizer.choice(CHANNELS),
            }
        )
    return customers


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def import_customers(customers: list[dict[str, str]], batch_size: int) -> None:
    for start in range(0, len(customers), batch_size):
        batch = customers[start : start + batch_size]
        request = Request(
            CRM_IMPORT_URL,
            data=json.dumps(batch).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            response.read()
        print(f"Imported {min(start + batch_size, len(customers))}/{len(customers)} customers")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="CSV file to import")
    source.add_argument("--count", type=int, help="Generate this many synthetic customers")
    parser.add_argument("--seed", type=int, default=360, help="Seed for repeatable generated data")
    parser.add_argument("--batch-size", type=int, default=500, help="Customers per API request")
    parser.add_argument("--write-csv", type=Path, help="Write generated customers to this CSV before importing")
    parser.add_argument("--generate-only", action="store_true", help="Generate a CSV without calling the CRM API")
    args = parser.parse_args()

    if args.count is not None:
        if not 1 <= args.count <= 10000:
            parser.error("--count must be between 1 and 10000")
        customers = generated_customers(args.count, args.seed)
        if args.write_csv:
            args.write_csv.parent.mkdir(parents=True, exist_ok=True)
            with args.write_csv.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=customers[0].keys())
                writer.writeheader()
                writer.writerows(customers)
    else:
        customers = load_csv(args.csv)

    if not customers:
        parser.error("customer source is empty")
    if args.generate_only:
        if args.count is None or not args.write_csv:
            parser.error("--generate-only requires --count and --write-csv")
        print(f"Generated {len(customers)} customers in {args.write_csv}")
        return
    import_customers(customers, args.batch_size)


if __name__ == "__main__":
    main()
