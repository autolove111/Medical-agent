import re
with open('d:/Users/xiaoli/Desktop/MedLabAgent/langchain_service/core/agent_streaming.py', 'rb') as f:
    text = f.read().decode('gbk', 'ignore')

text = text.replace('metadata["isMedical"] = parsed_fields.get("鍖荤枟", "") == "鏄?', 'metadata["isMedical"] = parsed_fields.get("医疗", "") == "是"')
text = text.replace('disease = parsed_fields.get("鐤剧梾", "")', 'disease = parsed_fields.get("疾病", "")')
text = text.replace('allergy = parsed_fields.get("杩囨晱", "")', 'allergy = parsed_fields.get("过敏", "")')
text = text.replace('metadata["diseases"] = "" if disease == "鏃?', 'metadata["diseases"] = "" if disease == "无"')
text = text.replace('metadata["drugAllergies"] = "" if allergy == "鏃?', 'metadata["drugAllergies"] = "" if allergy == "无"')

with open('d:/Users/xiaoli/Desktop/MedLabAgent/langchain_service/core/agent_streaming.py', 'w', encoding='utf-8') as f:
    f.write(text)
