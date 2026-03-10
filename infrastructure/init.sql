-- ============================================
-- MedLabAgent 数据库初始化脚本
-- ============================================

-- 创建数据库和用户（需以 postgres 超级用户身份执行）
-- CREATE DATABASE medlab_db;
-- CREATE USER medlab_user WITH PASSWORD 'medlab_password';
-- GRANT ALL PRIVILEGES ON DATABASE medlab_db TO medlab_user;

-- 以下在 medlab_db 数据库中执行 --

-- 创建 pgvector 扩展（用于向量相似度搜索）
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================
-- 用户认证与管理相关表
-- ============================================

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    real_name VARCHAR(100) NOT NULL,
    id_number VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    drug_allergy TEXT,
    lifetime_medical_history TEXT
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_users_id_number ON users(id_number);

-- 化验单主表
CREATE TABLE IF NOT EXISTS lab_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    report_name VARCHAR(255),
    report_type VARCHAR(100),
    upload_file_path VARCHAR(500),
    minio_object_name VARCHAR(500),
    status VARCHAR(50) DEFAULT 'PENDING',
    ocr_text TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    report_date DATE
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_lab_reports_user_id ON lab_reports(user_id);
CREATE INDEX IF NOT EXISTS idx_lab_reports_status ON lab_reports(status);
CREATE INDEX IF NOT EXISTS idx_lab_reports_created_at ON lab_reports(created_at);

-- 化验单详细指标表
CREATE TABLE IF NOT EXISTS report_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES lab_reports(id) ON DELETE CASCADE,
    item_name VARCHAR(255),
    item_value VARCHAR(255),
    unit VARCHAR(50),
    reference_range VARCHAR(255),
    is_abnormal BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_report_items_report_id ON report_items(report_id);

-- 用户对话记录表
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    report_id UUID REFERENCES lab_reports(id) ON DELETE SET NULL,
    message_type VARCHAR(50),
    user_message TEXT,
    agent_response TEXT,
    tokens_used INT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at);

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
