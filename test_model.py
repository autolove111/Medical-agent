from sentence_transformers import SentenceTransformer
model = SentenceTransformer("D:/Users/xiaoli/Desktop/MedLabAgent/bce-embedding-base_v1")
emb = model.encode("测试句子")
print(emb.shape)
print("模型加载成功！")
