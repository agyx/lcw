#!/usr/bin/env bash

rm -rf venv
virtualenv -p /usr/local/bin/python3.9 venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
