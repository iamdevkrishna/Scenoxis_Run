import os
import sys
from dotenv import load_dotenv

load_dotenv()

from agent.graph import run_query
import logging

logging.basicConfig(level=logging.DEBUG)

messages = []
query = "Who is Virat Kohli, and what was his recent score in recent match"

try:
    print("Running query...")
    res = run_query(query, None, messages, None)
    print("Result:", res)
except Exception as e:
    print("FATAL ERROR:", e)
