#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec streamlit run app/ui/streamlit_app.py
