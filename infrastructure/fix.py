import re

with open('d:/Users/xiaoli/Desktop/MedLabAgent/langchain_service/core/agent_streaming.py', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

text = re.sub(r'metadata\["isMedical"\].*?\n', '    metadata["isMedical"] = parsed_fields.get("医疗", "") == "是"\n', text)
text = re.sub(r'disease = parsed_fields\.get.*?\n', '    disease = parsed_fields.get("疾病", "")\n', text)
text = re.sub(r'allergy = parsed_fields\.get.*?\n', '    allergy = parsed_fields.get("过敏", "")\n', text)
text = re.sub(r'metadata\["diseases"\].*?\n', '    metadata["diseases"] = "" if disease == "无" else disease\n', text)
text = re.sub(r'metadata\["drugAllergies"\].*?\n', '    metadata["drugAllergies"] = "" if allergy == "无" else allergy\n', text)

with open('d:/Users/xiaoli/Desktop/MedLabAgent/langchain_service/core/agent_streaming.py', 'w', encoding='utf-8') as f:
    f.write(text)
