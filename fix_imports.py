with open('d:/Users/xiaoli/Desktop/MedLabAgent/langchain_service/core/agent_streaming.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Replace all incorrect imports
content = content.replace('from core.rag import', 'from knowledge.rag import')
content = content.replace('from core.tools import', 'from tools import')
content = content.replace('from core.medical_knowledge import', 'from knowledge.medical_knowledge import')

with open('d:/Users/xiaoli/Desktop/MedLabAgent/langchain_service/core/agent_streaming.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Import paths fixed")
