#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path


def print_header(text):
    print("\n" + "=" * 50)
    print(f"  {text}")
    print("=" * 50)


def print_success(text):
    print(f"[OK] {text}")


def print_error(text):
    print(f"[ERR] {text}")


def check_package(package_name, import_name=None):
    import_name = import_name or package_name.replace("-", "_")
    try:
        __import__(import_name)
        print_success(f"{package_name} installed")
        return True
    except ImportError:
        print_error(f"{package_name} missing")
        return False


def check_langchain_dependencies():
    print_header("Dependency Check")
    packages = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("langchain", "langchain"),
        ("langchain-community", "langchain_community"),
        ("langchain-core", "langchain_core"),
        ("transformers", "transformers"),
        ("pydantic", "pydantic"),
        ("pydantic-settings", "pydantic_settings"),
        ("httpx", "httpx"),
        ("faiss-cpu", "faiss"),
    ]
    return all(check_package(pkg, imp) for pkg, imp in packages)


def check_env_file():
    print_header("Env Check")
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        print_error(".env missing")
        return False

    content = env_path.read_text(encoding="utf-8")
    required_keys = ["LLM_MODEL_PATH", "RAG_LOCAL_EMBEDDING_PATH"]
    ok = True
    for key in required_keys:
        if f"{key}=" in content:
            print_success(f"{key} configured")
        else:
            print_error(f"{key} missing")
            ok = False
    return ok


def check_config():
    print_header("Config Check")
    try:
        from core.config import settings

        print_success("config loaded")
        print(f"  - LLM_MODEL_PATH: {settings.LLM_MODEL_PATH}")
        print(f"  - RAG_LOCAL_EMBEDDING_PATH: {settings.RAG_LOCAL_EMBEDDING_PATH}")
        print(f"  - SERVICE_HOST: {settings.SERVICE_HOST}")
        print(f"  - SERVICE_PORT: {settings.SERVICE_PORT}")
        return True
    except Exception as exc:
        print_error(f"config load failed: {exc}")
        return False


def main():
    os.chdir(Path(__file__).parent.parent)
    sys.path.insert(0, str(Path(__file__).parent.parent))

    results = [
        ("Dependencies", check_langchain_dependencies()),
        ("Env", check_env_file()),
        ("Config", check_config()),
    ]

    print_header("Summary")
    for name, ok in results:
        print(f"{name:.<30} {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
