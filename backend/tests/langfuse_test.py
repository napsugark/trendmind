from langfuse import Langfuse, observe
from dotenv import load_dotenv, find_dotenv

import os
load_dotenv(find_dotenv())

lf = Langfuse()
@observe()
def connection_test():
    print("Hello Langfuse!")
    return "✅ Connection successful"

try:
    result = connection_test()
    print(result)
except Exception as e:
    print("❌ Langfuse connection failed:", str(e))

