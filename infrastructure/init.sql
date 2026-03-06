-- ============================================
-- MedLabAgent 数据库初始化脚本
-- ============================================

-- 创建 pgvector 扩展（用于向量相似度搜索）
CREATE EXTENSION IF NOT EXISTS vector;

-- 知识库记录表
CREATE TABLE IF NOT EXISTS knowledge_records (
    id BIGSERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    source VARCHAR(255),
    category VARCHAR(100),
    embedding vector(1536),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引以提升查询性能
CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge_records(category);
CREATE INDEX IF NOT EXISTS idx_knowledge_source ON knowledge_records(source);
CREATE INDEX IF NOT EXISTS idx_knowledge_created_at ON knowledge_records(created_at);

-- 向量相似度搜索索引
CREATE INDEX IF NOT EXISTS idx_knowledge_embedding 
ON knowledge_records USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

-- 医疗对话记录表（可选）
CREATE TABLE IF NOT EXISTS medical_conversations (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(100),
    user_query TEXT NOT NULL,
    agent_response TEXT,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50)
);

-- 用户会话表（可选）
CREATE TABLE IF NOT EXISTS user_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(100) UNIQUE,
    session_token VARCHAR(500),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

-- 插入示例知识数据
INSERT INTO knowledge_records (content, source, category) VALUES
('血液检查报告包含红细胞、白细胞、血小板等指标。正常范围：RBC 4.5-5.5×10¹²/L', '医学教科书', '血液检查'),
('肝功能检查包括胆红素、谷丙转氨酶、谷草转氨酶等指标。', '临床指南', '肝功能'),
('肾功能检查指标包括肌酐、尿素氮、尿酸等。', '医学文献', '肾功能')
ON CONFLICT DO NOTHING;

-- 向knowledge_records表添加注释
COMMENT ON TABLE knowledge_records IS '医疗知识库记录表，存储医学知识内容和向量嵌入';
COMMENT ON COLUMN knowledge_records.content IS '知识内容';
COMMENT ON COLUMN knowledge_records.source IS '知识来源';
COMMENT ON COLUMN knowledge_records.category IS '知识分类';
COMMENT ON COLUMN knowledge_records.embedding IS '内容向量嵌入，用于向量相似度搜索';
