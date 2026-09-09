#!/usr/bin/env python3
"""Vertex AI / Gemini 2.5 Pro Cloud Connection Test.

Verifies connectivity to Google Cloud Vertex AI or Google AI Studio using
credentials configured in .env, testing multimodal image/video diagnosis
and confirming that inference is active and routed.
"""

import os
import sys
import time
from pathlib import Path

# Load .env from workspace root
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "incident-arbiter"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass


def print_banner(title: str):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)


def test_cloud_connection():
    print_banner("ICVFX SYNC ENGINE - VERTEX AI & GEMINI CLOUD CHECK")

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    cred_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    backend = os.environ.get("GEMINI_BACKEND", "vertex" if project else "api_key").lower()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")

    print(f"[*] Configured Backend:     {backend.upper()}")
    print(f"[*] Target AI Model:        {model}")
    print(f"[*] GCP Project ID:         {project or '(Not set in .env)'}")
    print(f"[*] GCP Region/Location:    {location}")
    print(f"[*] Auth Key / Credentials: {'[PRESENT]' if (api_key or cred_file) else '[NONE DETECTED]'}")
    if cred_file:
        resolved_cred = Path(cred_file)
        if not resolved_cred.is_absolute():
            resolved_cred = ROOT_DIR / cred_file
        print(f"[*] Service Account File:   {resolved_cred} (Exists: {resolved_cred.exists()})")

    try:
        from google import genai
        from google.genai import types
        print(f"[*] google-genai SDK:       v{getattr(genai, '__version__', 'latest')} (Installed)")
    except ImportError as e:
        print(f"\n[!] Error: google-genai package not found ({e}). Run: pip install google-genai")
        return False

    client = None
    active_mode = ""

    # Initialize client based on backend
    try:
        if backend == "vertex" or (project and backend != "api_key"):
            print(f"\n[*] Initializing Vertex AI Client (project={project}, location={location})...")
            if cred_file:
                resolved_cred = Path(cred_file)
                if not resolved_cred.is_absolute():
                    resolved_cred = ROOT_DIR / cred_file
                if resolved_cred.exists():
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(resolved_cred)

            from google.genai.types import HttpOptions

            http_opts = HttpOptions(
                headers={"x-goog-user-project": project} if project else None
            )

            if project:
                client = genai.Client(vertexai=True, project=project, location=location, http_options=http_opts)
            else:
                client = genai.Client(vertexai=True, location=location, http_options=http_opts)
            active_mode = f"Google Cloud Vertex AI (Project: {project or 'default'})"
        elif api_key:
            print("\n[*] Initializing Google AI Client via API Key...")
            client = genai.Client(api_key=api_key)
            active_mode = "Google AI Studio Developer API"
        else:
            print("\n[!] No valid GCP Project ID or API Key configured in .env.")
            print("    Please set GOOGLE_CLOUD_PROJECT and/or GEMINI_API_KEY in .env.")
            return False

    except Exception as e:
        print(f"[!] Failed to initialize client: {e}")
        return False

    print(f"[+] Client initialized successfully ({active_mode}).")

    candidate_models = ["gemini-3.8-flash", model, "gemini-2.5-flash", "gemini-3.1-pro-preview", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
    unique_models = []
    for m in candidate_models:
        if m and m not in unique_models:
            unique_models.append(m)

    success = False
    for target_m in unique_models:
        print(f"\n[*] Sending live diagnostic inference request to {target_m}...")
        t0 = time.monotonic()
        try:
            response = client.models.generate_content(
                model=target_m,
                contents="Confirm ICVFX Autonomous Telemetry Engine connection. Respond with 1 concise sentence summarizing stage synchronization health.",
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=100,
                )
            )
            latency = round((time.monotonic() - t0) * 1000, 2)
            print(f"[+] Response received from {target_m} in {latency} ms!")
            print(f"[+] Model Output:\n    \"{response.text.strip()}\"")
            print("\n" + "-" * 65)
            print(f"[SUCCESS] Cloud connection verified! Active Model: {target_m}")
            print(f"          Backend: {active_mode}")
            print("-" * 65)
            success = True
            break
        except Exception as e:
            latency = round((time.monotonic() - t0) * 1000, 2)
            print(f"[!] Request to {target_m} failed after {latency} ms: {e}")
            continue

    if not success:
        print("\n[!] All candidate models failed.")
        return False
    return True


if __name__ == "__main__":
    success = test_cloud_connection()
    sys.exit(0 if success else 1)
