#!/usr/bin/env python3
"""
Manual edge case verifier — works on Windows, Mac, Linux.
Run: python test_manual.py
"""

import subprocess, sys, os, tempfile

PASS = 0
FAIL = 0

def run(label, input_line, expect):
    global PASS, FAIL
    # Write the test line to a temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(input_line + "\n")
        tmp = f.name

    try:
        result = subprocess.run(
            [sys.executable, 'analyze.py', tmp, '--no-color'],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )
        output = result.stdout + result.stderr
        ok = expect.lower() in output.lower()
    finally:
        os.unlink(tmp)

    if ok:
        print(f"  ✅  {label}")
        PASS += 1
    else:
        print(f"  ❌  {label}")
        print(f"        Input:    {input_line[:80]}")
        print(f"        Expected: output to contain '{expect}'")
        # Show first relevant lines of actual output
        lines = [l for l in output.splitlines() if l.strip()]
        for l in lines[:6]:
            print(f"        Got:      {l}")
        FAIL += 1

def run_file(label, filepath, expect):
    global PASS, FAIL
    result = subprocess.run(
        [sys.executable, 'analyze.py', filepath, '--no-color'],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )
    output = result.stdout + result.stderr
    ok = expect.lower() in output.lower()
    if ok:
        print(f"  ✅  {label}")
        PASS += 1
    else:
        print(f"  ❌  {label}")
        print(f"        Expected: output to contain '{expect}'")
        lines = [l for l in output.splitlines() if l.strip()]
        for l in lines[:6]:
            print(f"        Got:      {l}")
        FAIL += 1

def section(title):
    print(f"\n── {title} {'─' * (40 - len(title))}")

print()
print("═" * 50)
print("  Manual Edge Case Verification")
print("═" * 50)

section("TIMESTAMPS")
run("E1  ISO 8601 Z timestamp",
    "2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 200 142ms",
    "valid lines")
run("E2  Slash-separated date",
    "2024/03/15 14:23:01 192.168.1.42 GET /api/users 200 142ms",
    "valid lines")
run("E3  Human-readable month",
    "15-Mar-2024 14:23:01 192.168.1.42 GET /api/users 200 142ms",
    "valid lines")
run("E4  Unix epoch integer",
    "1710512581 192.168.1.42 GET /api/users 200 142ms",
    "valid lines")
run("E5  Missing timestamp → flagged",
    "192.168.1.42 GET /api/users 200 142ms",
    "missing_timestamp")
run("E6  Malformed timestamp → flagged",
    "2024-99-99T25:61:00Z 192.168.1.42 GET /api/users 200 142ms",
    "malformed_timestamp")

section("RESPONSE TIME")
run("E7  Milliseconds suffix (142ms)",
    "2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 200 142ms",
    "142.0ms")
run("E8  Seconds suffix (0.142s → 142ms)",
    "2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 200 0.142s",
    "142.0ms")
run("E9  Bare number, no unit (142 → 142ms)",
    "2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 200 142",
    "142.0ms")
run("E10 Negative response time → flagged",
    "2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 200 -50ms",
    "negative_response_time")
run("E11 Missing response time → flagged",
    "2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 200",
    "missing_response_time")

section("STATUS CODES")
run("E12 Standard 3-digit status (200)",
    "2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 200 142ms",
    "200")
run("E13 Dash placeholder → flagged",
    "2024-03-15T14:23:01Z 192.168.1.42 GET /api/users - 142ms",
    "status_dash_placeholder")
run("E14 Missing status entirely",
    "2024-03-15T14:23:01Z 192.168.1.42 GET /api/users",
    "missing_response_time")
run("E15 Non-standard status 999 → flagged",
    "2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 999 142ms",
    "nonstandard_status")

section("EXTRA / UNEXPECTED FIELDS")
run("E17 User agent appended (ignored cleanly)",
    "2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 200 142ms Mozilla/5.0",
    "200")
run("E18 Quoted referrer with spaces inside",
    '2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 200 142ms "https://site.com/a page"',
    "200")
run("E19 User agent + referrer both present",
    '2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 200 142ms Mozilla/5.0 "https://ref.com"',
    "200")
run("E20 Path with query string",
    "2024-03-15T14:23:01Z 192.168.1.42 GET /api/users?page=2&limit=50 200 142ms",
    "200")
run("E21 Path with spaces (unquoted, best-effort)",
    "2024-03-15T14:23:01Z 192.168.1.42 GET /api/files/my document.pdf 200 142ms",
    "valid lines")

section("MALFORMED LINES")
run("E22 Blank line skipped silently",
    "",
    "blank lines")
run("E23 Truncated / partial line",
    "2024-03-15T14:23:01Z 10.0.0.1",
    "malformed lines")
run("E24 Java stack trace line",
    "java.lang.NullPointerException: at com.example.Foo.bar(Foo.java:42)",
    "malformed lines")
run("E25 Leading + trailing whitespace stripped",
    "   2024-03-15T14:23:01Z 192.168.1.42 GET /api/users 200 142ms   ",
    "valid lines")
run("E26 Non-UTF8 replacement char doesn't crash",
    "2024-03-15T14:23:01Z 192.168.1.42 GET /api/\ufffdusers 200 142ms",
    "valid lines")
run("E27 Comment / header line skipped",
    "# Log file started 2024-03-15",
    "comment lines")

section("JSON FORMAT LINES")
run("E29 Full JSON log line",
    '{"timestamp":"2024-03-15T14:23:01Z","ip":"192.168.1.42","method":"GET","path":"/api/users","status":200,"response_time":"142ms"}',
    "200")
run("E30 JSON with alternative field names",
    '{"ts":"2024-03-15T14:23:01Z","remote_addr":"192.168.1.42","verb":"GET","uri":"/api/users","status_code":404,"duration":"88ms"}',
    "404")
run("E31 JSON response_time as number not string",
    '{"timestamp":"2024-03-15T14:23:01Z","ip":"192.168.1.42","method":"GET","path":"/api/users","status":200,"response_time":99}',
    "99.0ms")
run("E32 Partial / malformed JSON → malformed",
    '{"timestamp":"2024-03-15T14:23:01Z","ip":"1.2.3.4"',
    "malformed lines")
run("E33 Plaintext prefix + JSON suffix",
    'ERROR {"timestamp":"2024-03-15T14:23:01Z","ip":"1.2.3.4","method":"GET","path":"/x","status":500,"response_time":"10ms"}',
    "500")

section("FILE-LEVEL EDGE CASES")
run_file("E35 Empty file → clean message",
    "test_logs/edge35_empty.log",
    "empty")
run_file("E37 All-malformed file → no crash",
    "test_logs/edge37_all_malformed.log",
    "malformed")
run_file("E38 No trailing newline → last line parsed",
    "test_logs/edge38_no_final_newline.log",
    "valid lines")

# E36 separately (checks exit code too)
print()
result = subprocess.run(
    [sys.executable, 'analyze.py', 'nonexistent_file.log', '--no-color'],
    capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"}
)
e36_ok = result.returncode == 1 and 'not found' in (result.stderr + result.stdout).lower()
if e36_ok:
    print(f"  ✅  E36 File not found → clean error + exit code 1")
    PASS += 1
else:
    print(f"  ❌  E36 File not found")
    print(f"        Exit code: {result.returncode} (expected 1)")
    print(f"        Output: {result.stderr.strip()}")
    FAIL += 1

# E34 note
print()
print("  ℹ️   E34 Large file streaming — run manually if you want:")
print(f"        python scripts/generate_logs.py --lines 500000 --output big.log")
print(f"        python analyze.py big.log")
print(f"        (should complete without memory errors)")

print()
print("═" * 50)
total = PASS + FAIL
print(f"  Result: {PASS}/{total} passed", end="")
if FAIL == 0:
    print("  🎉 All clear!")
else:
    print(f"  ← {FAIL} FAILED — check output above")
print("═" * 50)
print()
