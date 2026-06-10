"""
Load Snowflake credentials from Windows Credential Manager into os.environ.
Drop-in replacement for load_dotenv() in any script that needs Snowflake access.
"""

import os
import keyring

SERVICE = "ifit-snowflake"
KEYS = [
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA",
]

AUTOMATION_ROOT = r"C:\Users\devin.lindsay\Documents\Claude\Projects\AI Implementation\Automation"


def load_snowflake_creds():
    for key in KEYS:
        val = keyring.get_password(SERVICE, key)
        if val:
            os.environ[key] = val
