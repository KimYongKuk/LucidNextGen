@echo off
cd /d "%~dp0"
echo Starting backend with 4 workers for better concurrency...
python start_workers.py
