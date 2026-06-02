# Log Analyzer Tool
**Dev Weekend Fellowship Assessment**

A robust CLI log analyzer that handles messy, real-world log files gracefully — streaming line-by-line, never crashing on bad input, and surfacing meaningful insights fast.

---

## Quickstart (single command)

```bash
python analyze.py sample_logs.log
```

That's it. No dependencies beyond Python 3.9+.

---

## Setup on a fresh machine

```bash
# 1. Clone / unzip the project
cd log-analyzer

# 2. (Optional) Generate sample logs to test with
python scripts/generate_logs.py --seed 42 --lines 500 --output sample_logs.log

# 3. Run the analyzer
python analyze.py sample_logs.log
```

No `pip install` required. The tool uses only Python standard library modules (`re`, `datetime`, `json`, `argparse`, `collections`, `sys`, `os`).

---

## Usage

```
python analyze.py <logfile> [options]

positional arguments:
  logfile          Path to the log file to analyze

options:
  --top N, -t N    Show top N results per section (default: 5)
  --json           Output as JSON instead of a formatted report
  --no-color       Disable ANSI color (useful for piping to a file)
  -h, --help       Show this help message
```

### Examples

```bash
# Basic report
python analyze.py access.log

# Show top 10 slowest endpoints
python analyze.py access.log --top 10

# Machine-readable JSON output
python analyze.py access.log --json

# Save plain-text report to file
python analyze.py access.log --no-color > report.txt

# Generate 2000 lines of test logs then analyze them
python scripts/generate_logs.py --lines 2000 --output test.log
python analyze.py test.log
```

---

## What the report shows

| Section | Details |
|---|---|
| **Summary** | Total / valid / malformed / blank / duplicate line counts + malformed % |
| **Slowest endpoints** | Top N endpoints by average response time, with bar chart |
| **Status code distribution** | All HTTP status codes with counts and % |
| **Top IPs** | Top N IPs by request volume |
| **Traffic by hour** | 24-hour histogram (UTC) |
| **Anomaly flags** | Negative times, non-standard codes, missing fields, duplicates |

---

## Log format supported

Primary format:
```
2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 200 142ms
```

The analyzer also handles many real-world variations — see [ANSWERS.md](ANSWERS.md) for the full list of 38 edge cases.

---

## Project structure

```
log-analyzer/
├── analyze.py              ← Main CLI analyzer
├── scripts/
│   └── generate_logs.py    ← Test log generator (38 edge cases)
├── README.md               ← This file
└── ANSWERS.md              ← Assessment questions answered
```

---

## Running edge-case tests

`generate_logs.py` writes individual edge-case files to `test_logs/` automatically:

```bash
python scripts/generate_logs.py --seed 42
python analyze.py test_logs/edge35_empty.log        # empty file
python analyze.py test_logs/edge37_all_malformed.log  # 100% malformed
python analyze.py test_logs/edge38_no_final_newline.log
python analyze.py nonexistent.log                   # file not found → clean error
```
