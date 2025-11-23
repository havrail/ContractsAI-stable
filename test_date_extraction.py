import sys
sys.path.insert(0, 'src_python')

from utils import extract_date_from_filename, clean_turkish_chars

# Test date extraction
test_cases = [
    ("Contract_11August_2025.pdf", "2025-08-11"),
    ("11_August_2025_Agreement.pdf", "2025-08-11"),
    ("2023-05-12_Contract.pdf", "2023-05-12"),
    ("Agreement_15-03-2024.pdf", "2024-03-15"),
    ("NDA_01Jan2023.pdf", "2023-01-01"),
    ("NoDateHere.pdf", None),
]

print("Testing Date Extraction:")
print("-" * 50)
for filename, expected in test_cases:
    result = extract_date_from_filename(filename)
    status = "✓" if result == expected else "✗"
    print(f"{status} {filename:40} -> {result} (expected: {expected})")

print("\n" + "=" * 50)
print("\nTesting Turkish Character Cleaning:")
print("-" * 50)

test_addresses = [
    "Ýstanbul, Türkiye",
    "Maslak Mahallesi, Sarýyer",
    "Ã§ok güzel bir adres",
]

for addr in test_addresses:
    cleaned = clean_turkish_chars(addr)
    print(f"Original: {addr}")
    print(f"Cleaned:  {cleaned}")
    print()
