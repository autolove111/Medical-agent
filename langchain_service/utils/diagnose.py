#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MedLabAgent System - Python 组件诊断脚本
用于快速诊断 Python 服务的配置和依赖问题
"""

import sys
import os
import importlib.util
from pathlib import Path

def print_header(text):
    print("\n" + "=" * 50)
    print(f"  {text}")
    print("=" * 50)

def print_success(text):
    print(f"✓ {text}")

def print_error(text):
    print(f"✗ {text}")

def print_warning(text):
    print(f"⚠ {text}")

def check_python_version():
    """检查 Python 版本"""
    print_header("检查 Python 环境")
    print(f"Python 版本: {sys.version}")
    print(f"Python 路径: {sys.executable}")
    
    if sys.version_info >= (3, 9):
        print_success("Python 版本满足要求 (>= 3.9)")
        return True
    else:
        print_error(f"Python 版本过低: {sys.version_info.major}.{sys.version_info.minor}")
        return False

def check_package(package_name, import_name=None):
    """检查包是否已安装"""
    if import_name is None:
        import_name = package_name.replace('-', '_')
    
    try:
        __import__(import_name)
        print_success(f"{package_name} 已安装")
        return True
    except ImportError:
        print_error(f"{package_name} 未安装")
        return False

def check_langchain_dependencies():
    """检查 LangChain 相关依赖"""
    print_header("检查 LangChain 依赖")
    
    packages = [
        ('fastapi', 'fastapi'),
        ('uvicorn', 'uvicorn'),
        ('langchain', 'langchain'),
        ('langchain-community', 'langchain_community'),
        ('langchain-core', 'langchain_core'),
        ('dashscope', 'dashscope'),
        ('pydantic', 'pydantic'),
        ('pydantic-settings', 'pydantic_settings'),
        ('aiohttp', 'aiohttp'),
        ('httpx', 'httpx'),
        ('faiss-cpu', 'faiss'),
    ]
    
    all_ok = True
    for pkg_name, import_name in packages:
        if not check_package(pkg_name, import_name):
            all_ok = False
    
    return all_ok

def check_env_file():
    """检查 .env 文件"""
    print_header("检查环境变量配置")
    
    env_path = Path(__file__).parent / ".env"
    
    if not env_path.exists():
        print_error(".env 文件不存在")
        return False
    
    print_success(".env 文件已找到")
    
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            env_content = f.read()
        
        # 检查关键配置
        required_keys = ['DASHSCOPE_API_KEY', 'DATABASE_URL']
        for key in required_keys:
            if key in env_content and f'{key}=' in env_content:
                if 'sk-' in env_content or 'postgresql://' in env_content:
                    print_success(f"{key} 已配置")
                else:
                    print_warning(f"{key} 已配置但值可能无效")
            else:
                print_error(f"{key} 未配置")
        
        return True
    except Exception as e:
        print_error(f"读取 .env 文件失败: {e}")
        return False

def check_config():
    """检查配置加载"""
    print_header("检查配置加载")
    
    try:
        from core.config import settings
        print_success("配置文件加载成功")
        print(f"  - DASHSCOPE_MODEL: {settings.DASHSCOPE_MODEL}")
        print(f"  - SERVICE_PORT: {settings.SERVICE_PORT}")
        print(f"  - SERVICE_HOST: {settings.SERVICE_HOST}")
        return True
    except Exception as e:
        print_error(f"配置加载失败: {e}")
        return False

def check_rag():
    """检查 RAG 系统"""
    print_header("检查 RAG 系统")
    
    try:
        from knowledge.rag import RAGSystem
        print("初始化 RAG 系统...")
        rag = RAGSystem()
        print_success("RAG 系统初始化成功")
        return True
    except Exception as e:
        print_error(f"RAG 系统初始化失败: {e}")
        return False

def check_agent():
    """检查 Agent"""
    print_header("检查 Medical Agent")
    
    try:
        from core.agent_streaming import create_medical_agent
        print("创建 Medical Agent...")
        agent = create_medical_agent()
        if agent.agent is not None:
            print_success("Medical Agent 创建成功")
            return True
        else:
            print_error("Medical Agent 创建失败（内部错误）")
            return False
    except Exception as e:
        print_error(f"Medical Agent 创建失败: {e}")
        return False

def check_tools():
    """检查工具"""
    print_header("检查工具集合")
    
    try:
        from tools import tools
        print_success(f"工具集合加载成功，共 {len(tools)} 个工具")
        for tool in tools:
            print(f"  - {tool.name}")
        return True
    except Exception as e:
        print_error(f"工具加载失败: {e}")
        return False

def main():
    print("\n")
    print("╔" + "=" * 48 + "╗")
    print("║  MedLabAgent LangChain 服务 - 诊断工具       ║")
    print("╚" + "=" * 48 + "╝")
    
    # 改变到脚本所在目录
    os.chdir(Path(__file__).parent)
    sys.path.insert(0, str(Path(__file__).parent))
    
    results = []
    
    # 执行检查
    results.append(("Python 环境", check_python_version()))
    results.append(("依赖包", check_langchain_dependencies()))
    results.append((".env 配置", check_env_file()))
    results.append(("配置加载", check_config()))
    results.append(("工具集合", check_tools()))
    results.append(("RAG 系统", check_rag()))
    results.append(("Agent", check_agent()))
    
    # 打印总结
    print_header("诊断总结")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name:.<30} {status}")
    
    print(f"\n总体: {passed}/{total} 项通过")
    
    if passed == total:
        print_success("所有检查通过！可以启动服务")
        print("\n启动命令: python main.py")
    else:
        print_error("存在未通过的检查，请查看上面的错误信息")
    
    print("\n")

if __name__ == "__main__":
    main()
