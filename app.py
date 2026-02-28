# ==============================
# IMPORTS
# ==============================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import sys
from io import StringIO
import traceback
import os
import json
import re
from google import genai
from google.genai import types

# ==============================
# FASTAPI APP
# ==============================

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================
# REQUEST / RESPONSE MODELS
# ==============================

class CodeRequest(BaseModel):
    code: str

class CodeResponse(BaseModel):
    error: List[int]
    result: str

class ErrorAnalysis(BaseModel):
    error_lines: List[int]

# ==============================
# TOOL FUNCTION: Execute Python
# ==============================

def execute_python_code(code: str) -> dict:
    """
    Execute Python code and return exact output.
    """

    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        exec(code)
        output = sys.stdout.getvalue()
        return {"success": True, "output": output}

    except Exception:
        output = traceback.format_exc()
        return {"success": False, "output": output}

    finally:
        sys.stdout = old_stdout

# ==============================
# AI ERROR ANALYZER
# ==============================

def analyze_error_with_ai(code: str, tb: str) -> List[int]:

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print("Missing GEMINI_API_KEY")
        return []

    client = genai.Client(api_key=api_key)

    prompt = f"""
Analyze the following Python code and its traceback.

Identify the exact line number(s) in the original CODE where the error occurred.

Return ONLY valid JSON in this format:
{{
  "error_lines": [integer_line_numbers]
}}

CODE:
{code}

TRACEBACK:
{tb}
"""

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash-latest",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "error_lines": types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(type=types.Type.INTEGER),
                        )
                    },
                    required=["error_lines"],
                ),
            ),
        )

        # Try parsing AI JSON
        try:
            data = json.loads(response.text)
            return data.get("error_lines", [])
        except:
            pass

    except Exception as e:
        print("AI Error:", e)

    # Fallback: extract line number directly from traceback
    match = re.search(r'line (\d+)', tb)
    if match:
        return [int(match.group(1))]

    return []

# ==============================
# MAIN ENDPOINT
# ==============================

@app.post("/code-interpreter", response_model=CodeResponse)
def code_interpreter(request: CodeRequest):

    execution = execute_python_code(request.code)

    # If success → return output directly
    if execution["success"]:
        return {
            "error": [],
            "result": execution["output"]
        }

    # If error → call AI analyzer
    error_lines = analyze_error_with_ai(
        request.code,
        execution["output"]
    )

    return {
        "error": error_lines,
        "result": execution["output"]
    }