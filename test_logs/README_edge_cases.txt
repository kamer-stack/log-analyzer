Edge case files for analyze.py testing
======================================

edge35_empty.log          — Edge 35: empty file
edge37_all_malformed.log  — Edge 37: 100% malformed lines
edge38_no_final_newline.log — Edge 38: no trailing newline

Edge 34 (large file / streaming): use sample_logs.log with --lines 100000
  python scripts/generate_logs.py --lines 100000 --output large_test.log
  python analyze.py large_test.log

Edge 36 (file not found): python analyze.py nonexistent.log
