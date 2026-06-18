"""
RAG 端到端测试脚本
================================
模拟完整链路：嵌入 → FAISS 召回 → Reranker 精排 → 阈值过滤

不依赖 langchain，直接使用 sentence_transformers + FAISS 原生 API。
"""

import os
import sys
import time
import json
import logging
import numpy as np

# Ensure we can import from python_service
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PY_SERVICE = os.path.join(_PROJECT_ROOT, "python_service")
sys.path.insert(0, _PY_SERVICE)

from dotenv import load_dotenv
load_dotenv(os.path.join(_PY_SERVICE, ".env"))

# Override with absolute paths
os.environ["RAG_LOCAL_EMBEDDING_PATH"] = os.path.join(_PROJECT_ROOT, "models", "Zhinao-ChineseModernBert-Embedding")
os.environ["RERANKER_MODEL_PATH"] = os.path.join(_PROJECT_ROOT, "models", "bge-reranker-base")
os.environ["RERANKER_DEVICE"] = "cpu"
os.environ["RERANKER_SCORE_THRESHOLD"] = "0.1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("rag_test")


# ═══════════════════════════════════════════════════════════
# 1. 加载嵌入模型
# ═══════════════════════════════════════════════════════════

def load_embedding_model():
    """加载 Zhinao 嵌入模型"""
    from sentence_transformers import SentenceTransformer
    path = os.environ["RAG_LOCAL_EMBEDDING_PATH"]

    logger.info("=" * 50)
    logger.info("Step 1: Loading embedding model")
    logger.info("  Path: %s", path)
    t0 = time.time()
    model = SentenceTransformer(path, device="cpu", trust_remote_code=True)
    logger.info("  Loaded in %.1fs (dim=%d)", time.time() - t0, model.get_sentence_embedding_dimension())
    return model


# ═══════════════════════════════════════════════════════════
# 2. 构建测试用 FAISS 向量库
# ═══════════════════════════════════════════════════════════

def build_test_vectorstore(embed_model):
    """构建小型测试知识库（30 篇中文医学文档）"""
    import faiss

    documents = [
        # ── 肾功能相关 ──
        "血清肌酐(Cr)是评估肾功能的核心指标，正常范围男性62-115μmol/L，女性53-97μmol/L。肌酐升高提示肾小球滤过功能下降。",
        "慢性肾脏病(CKD)分期标准：1期eGFR≥90，2期60-89，3期30-59，4期15-29，5期<15ml/min/1.73m²。治疗重点为延缓进展。",
        "急性肾损伤(AKI)诊断标准：48小时内肌酐升高≥26.5μmol/L，或7天内肌酐升至基线1.5倍以上。需积极寻找并纠正病因。",
        "肾小球滤过率(eGFR)常用CKD-EPI公式计算，基于血肌酐、年龄、性别、种族。eGFR<60持续3个月可诊断CKD。",
        "尿微量白蛋白/肌酐比值(UACR)是早期肾损伤敏感指标，正常<30mg/g。30-300mg/g为微量白蛋白尿期。",
        "肾功能不全患者饮食管理：优质低蛋白饮食(0.6-0.8g/kg/d)，限制钠摄入(<2g/d)，控制钾(2-3g/d)和磷(<800mg/d)。",
        "血液透析适应症：eGFR<15ml/min，或出现尿毒症症状、难治性高钾血症、代谢性酸中毒、容量负荷过重。",
        "造影剂肾病预防：检查前水化(生理盐水1ml/kg/h持续12h)，停用肾毒性药物，选用等渗造影剂，控制造影剂用量。",

        # ── 高尿酸/痛风 ──
        "高尿酸血症诊断标准：男性空腹血尿酸>420μmol/L，女性>360μmol/L。长期高尿酸可导致痛风、肾结石、肾功能损害。",
        "痛风急性发作期处理：秋水仙碱（首剂1mg，1h后再给0.5mg）或NSAIDs或糖皮质激素。急性期不启动降尿酸治疗。",
        "痛风缓解期降尿酸目标：一般<360μmol/L，有痛风石者<300μmol/L。常用药物：别嘌醇、非布司他、苯溴马隆。",

        # ── 肝功能 ──
        "丙氨酸氨基转移酶(ALT)正常范围<40U/L，天冬氨酸氨基转移酶(AST)<40U/L。ALT/AST升高提示肝细胞损伤。",
        "总胆红素(TBIL)正常范围<21μmol/L，直接胆红素(DBIL)<8μmol/L。TBIL升高见于肝细胞性黄疸、梗阻性黄疸、溶血性黄疸。",
        "γ-谷氨酰转移酶(GGT)正常范围男性<50U/L，女性<32U/L。GGT升高提示肝胆系统疾病或酒精性肝损伤。",
        "肝硬化代偿期可无明显症状，失代偿期出现腹水、食管胃底静脉曲张破裂出血、肝性脑病、肝肾综合征等。",

        # ── 血常规 ──
        "白细胞计数(WBC)正常范围4.5-11.0×10⁹/L。增高(白细胞增多症)常见于感染、炎症、应激、白血病。",
        "红细胞计数(RBC)正常范围男性4.5-5.9×10¹²/L，女性4.1-5.1×10¹²/L。减少提示贫血。",
        "血红蛋白(Hb)正常范围男性130-160g/L，女性115-150g/L。Hb<120g/L(女性<110g/L)可诊断贫血。",
        "血小板计数(PLT)正常范围150-400×10⁹/L。PLT<100为血小板减少，<50有出血风险，<20有严重出血风险。",

        # ── 血脂/血糖 ──
        "总胆固醇(TC)理想水平<5.2mmol/L，边缘升高5.2-6.2mmol/L，升高≥6.2mmol/L。高胆固醇血症是动脉粥样硬化危险因素。",
        "甘油三酯(TG)正常范围<1.7mmol/L。重度高甘油三酯血症(TG>5.6mmol/L)有诱发急性胰腺炎风险。",
        "空腹血糖正常范围3.9-6.1mmol/L。6.1≤FPG<7.0为空腹血糖受损，FPG≥7.0可诊断糖尿病。",
        "糖化血红蛋白(HbA1c)正常<6.0%，6.0-6.5%为糖尿病前期，≥6.5%可诊断糖尿病。反映近2-3月平均血糖水平。",

        # ── 电解质 ──
        "血清钠(Na)正常范围135-145mmol/L。低钠血症(<135)可导致脑水肿，高钠血症(>145)提示脱水。",
        "血清钾(K)正常范围3.5-5.5mmol/L。高钾血症(>5.5)可致心律失常甚至心搏骤停，为内科急症。",
        "血清钙(Ca)正常范围2.25-2.75mmol/L。低钙血症可导致手足搐搦，高钙血症常见于原发性甲状旁腺功能亢进。",

        # ── 其他指标 ──
        "C反应蛋白(CRP)正常<8mg/L。CRP是急性时相反应蛋白，增高见于感染、炎症、组织损伤、恶性肿瘤。",
        "促甲状腺激素(TSH)正常范围0.35-5.5mIU/L。TSH降低提示甲亢，升高提示甲减。是甲状腺功能筛查首选指标。",
        "肌酸激酶(CK)正常范围男性38-174U/L，女性26-140U/L。CK显著升高(>1000)提示心肌损伤或横纹肌溶解。",
        "乳酸脱氢酶(LDH)正常范围100-240U/L。LDH升高见于心肌梗死、肝病、恶性肿瘤、溶血性贫血等多种情况。",
    ]

    logger.info("=" * 50)
    logger.info("Step 2: Building FAISS vectorstore")
    logger.info("  Documents: %d", len(documents))

    # Encode all documents
    t0 = time.time()
    vectors = embed_model.encode(documents, show_progress_bar=True, normalize_embeddings=True)
    dim = vectors.shape[1]
    logger.info("  Encoded in %.1fs (dim=%d)", time.time() - t0, dim)

    # Build FAISS index (inner product for cosine similarity with normalized vectors)
    index = faiss.IndexFlatIP(dim)
    index.add(vectors.astype(np.float32))
    logger.info("  FAISS index: %d vectors", index.ntotal)

    return index, documents, dim


# ═══════════════════════════════════════════════════════════
# 3. FAISS 粗排（Top-20 召回）
# ═══════════════════════════════════════════════════════════

def faiss_recall(query, embed_model, index, documents, top_k=20):
    """FAISS 语义检索，返回 Top-K 文档"""
    q_vec = embed_model.encode([query], normalize_embeddings=True).astype(np.float32)
    scores, indices = index.search(q_vec, top_k)

    results = []
    for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
        if idx < 0 or idx >= len(documents):
            continue
        results.append({
            "rank": i + 1,
            "score": float(score),
            "content": documents[idx],
            "idx": int(idx),
        })
    return results


# ═══════════════════════════════════════════════════════════
# 4. Reranker 精排（Cross-Encoder）
# ═══════════════════════════════════════════════════════════

def cross_encoder_rerank(query, faiss_results, top_k=5, threshold=0.1):
    """Cross-Encoder 对 FAISS 召回结果精排"""
    from sentence_transformers import CrossEncoder

    logger.info("=" * 50)
    logger.info("Step 4: Cross-Encoder reranking")

    path = os.environ["RERANKER_MODEL_PATH"]
    t0 = time.time()
    ce = CrossEncoder(path, device="cpu", trust_remote_code=True)
    logger.info("  CrossEncoder loaded in %.1fs", time.time() - t0)

    # Build (query, doc) pairs
    pairs = [(query, r["content"]) for r in faiss_results]
    t1 = time.time()
    scores = ce.predict(pairs, show_progress_bar=True)
    logger.info("  Scored %d pairs in %.2fs", len(pairs), time.time() - t1)

    # Combine, sort, filter
    combined = []
    for i, (r, score) in enumerate(zip(faiss_results, scores)):
        combined.append({
            "faiss_rank": r["rank"],
            "faiss_score": r["score"],
            "rerank_score": float(score),
            "content": r["content"],
            "idx": r["idx"],
        })

    combined.sort(key=lambda x: x["rerank_score"], reverse=True)

    # Threshold filter
    passed = [c for c in combined if c["rerank_score"] >= threshold]
    final = passed[:top_k]

    return combined, final


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def run_test(query, embed_model, index, documents):
    """Run a single query through the full pipeline"""
    print()
    print("=" * 70)
    print(f"  Query: {query}")
    print("=" * 70)

    # Step 3: FAISS recall (Top-20)
    t0 = time.time()
    faiss_results = faiss_recall(query, embed_model, index, documents, top_k=20)
    t_faiss = time.time() - t0

    print(f"\n  FAISS Recall (Top-20, {t_faiss:.3f}s):")
    for r in faiss_results[:5]:
        marker = " ←" if r["rank"] <= 3 else "  "
        print(f"    [{r['rank']:2d}] score={r['score']:.4f} | {r['content'][:70]}...{marker}")

    if len(faiss_results) > 5:
        print(f"    ... ({len(faiss_results) - 5} more)")

    # Step 4: Cross-Encoder rerank
    t0 = time.time()
    all_reranked, final = cross_encoder_rerank(query, faiss_results, top_k=5, threshold=0.1)
    t_rerank = time.time() - t0

    print(f"\n  Cross-Encoder Rerank ({t_rerank:.1f}s):")
    print(f"  {'Rank':<4} {'Rerank':>8} {'FAISS':>8}  Content")
    print(f"  {'-'*4} {'-'*8} {'-'*8}  {'-'*60}")

    for i, r in enumerate(all_reranked):
        status = "PASS" if r["rerank_score"] >= 0.1 else "DROP"
        print(f"  [{i+1:2d}] {r['rerank_score']:8.4f} {r['faiss_score']:8.4f}  [{status}] {r['content'][:55]}...")

    print(f"\n  Final Top-{len(final)} (threshold=0.1):")
    if final:
        for i, r in enumerate(final):
            print(f"    [{i+1}] rerank_score={r['rerank_score']:.4f} | {r['content'][:80]}...")
    else:
        print(f"    (all docs below threshold — reranker working correctly for irrelevant queries)")

    print(f"\n  Timings: FAISS={t_faiss*1000:.0f}ms  Rerank={t_rerank:.1f}s  Total={t_faiss+t_rerank:.1f}s")
    return final


def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       Medical RAG Pipeline - End-to-End Test            ║")
    print("║   Embedding: Zhinao-ChineseModernBert-Embedding          ║")
    print("║   Retriever: FAISS (Top-20 recall)                       ║")
    print("║   Reranker:  bge-reranker-base (Cross-Encoder)           ║")
    print("╚══════════════════════════════════════════════════════════╝")

    # Load embedding model
    embed_model = load_embedding_model()

    # Build test vectorstore
    index, documents, dim = build_test_vectorstore(embed_model)

    # ── Test queries ──
    test_queries = [
        "肌酐120偏高怎么办严重吗",
        "高尿酸血症怎么治疗",
        "肾功能不全吃什么好",
        "白细胞高是什么原因",
        "高血压的诊断标准",
    ]

    for query in test_queries:
        run_test(query, embed_model, index, documents)

    print("\n" + "=" * 70)
    print("  All tests completed!")
    print("=" * 70)


if __name__ == "__main__":
    main()
