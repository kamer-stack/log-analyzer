# ANSWERS.md 
## 1. How to run (exact commands on a fresh machine)

No dependencies to install — Python standard library only.

```bash
# Clone or unzip the project, then:
cd log_analyzer/

# Generate a test log file
python scripts/generate_logs.py --seed 42 --lines 500 --output sample_logs.log

# Run the analyzer
python analyze.py sample_logs.log
```

**Full fresh-machine sequence (Windows):**

```powershell
# Verify Python version (needs 3.8+)
python --version

# Set encoding for Unicode bar characters
$env:PYTHONIOENCODING="utf-8"

# Generate test data
python scripts/generate_logs.py --seed 42 --lines 500 --output sample_logs.log

# Analyze it
python analyze.py sample_logs.log

# Or get JSON output
python analyze.py sample_logs.log --json

# Test specific edge cases
python analyze.py test_logs/edge35_empty.log
python analyze.py test_logs/edge37_all_malformed.log
python analyze.py nonexistent.log

# Run the test suite
python test_manual.py
```

**Full fresh-machine sequence (macOS / Linux):**

```bash
python3 scripts/generate_logs.py --seed 42 --lines 500 --output sample_logs.log
python3 analyze.py sample_logs.log
python3 test_manual.py
```



