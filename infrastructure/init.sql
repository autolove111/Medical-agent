-- ============================================
-- MedLabAgent 数据库初始化脚本
-- ============================================

-- 创建数据库和用户（需以 postgres 超级用户身份执行）
-- CREATE DATABASE medlab_db;
-- CREATE USER medlab_user WITH PASSWORD 'medlab_password';
-- GRANT ALL PRIVILEGES ON DATABASE medlab_db TO medlab_user;

-- 以下在 medlab_db 数据库中执行 --

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
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引以提升查询性能
CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge_records(category);
CREATE INDEX IF NOT EXISTS idx_knowledge_source ON knowledge_records(source);
CREATE INDEX IF NOT EXISTS idx_knowledge_created_at ON knowledge_records(created_at);

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
COMMENT ON TABLE knowledge_records IS '医疗知识库记录表，存储医学知识内容（向量存储在Faiss中）';
COMMENT ON COLUMN knowledge_records.content IS '知识内容';
COMMENT ON COLUMN knowledge_records.source IS '知识来源';
COMMENT ON COLUMN knowledge_records.category IS '知识分类';

-- ============================================
-- 双图架构表
-- ============================================

-- 图1: 化验指标生理关联图
-- 存储指标之间的生理耦合关系（如Cr与BUN的正相关）
CREATE TABLE IF NOT EXISTS indicator_graph (
    id SERIAL PRIMARY KEY,
    source_indicator VARCHAR(50) NOT NULL,  -- 源指标，如 'Cr'
    target_indicator VARCHAR(50) NOT NULL,  -- 目标指标，如 'BUN'
    relation_type VARCHAR(30) NOT NULL,    -- 关系类型: 'POSITIVE_CORR', 'NEGATIVE_CORR', 'SAME_SYSTEM', 'CLINICAL_PATH'
    weight FLOAT DEFAULT 0.5,               -- 关联强度 0.0~1.0
    description TEXT,                       -- 关系描述，如"同属肾功能代谢产物"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_indicator, target_indicator)
);

-- 图2: 专家协作图
-- 存储科室/Agent节点及其协作关系
CREATE TABLE IF NOT EXISTS expert_graph (
    id SERIAL PRIMARY KEY,
    source_node VARCHAR(50) NOT NULL,       -- 源节点，如 'RenalDepartment' 或 'RenalExpert'
    source_type VARCHAR(20) NOT NULL,       -- 节点类型: 'DEPARTMENT' or 'AGENT'
    target_node VARCHAR(50) NOT NULL,       -- 目标节点
    target_type VARCHAR(20) NOT NULL,       -- 目标节点类型
    relation_type VARCHAR(30) NOT NULL,    -- 关系类型: 'COLLABORATE', 'PRECEDES', 'MUTUAL_EXCLUSIVE'
    weight FLOAT DEFAULT 0.5,               -- 协作紧密度或调用优先级 0.0~1.0
    description TEXT,                       -- 关系描述
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_node, target_node)
);

-- 指标与科室的映射表（用于从指标集合推导科室集合）
CREATE TABLE IF NOT EXISTS indicator_department_mapping (
    id SERIAL PRIMARY KEY,
    indicator_name VARCHAR(50) NOT NULL,    -- 如 'Cr', 'ALT'
    department_name VARCHAR(50) NOT NULL,   -- 如 'RenalDepartment'
    relevance_score FLOAT DEFAULT 0.8,      -- 指标对科室的相关度
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(indicator_name, department_name)
);

-- 创建索引以提升查询性能
CREATE INDEX IF NOT EXISTS idx_indicator_graph_source ON indicator_graph(source_indicator);
CREATE INDEX IF NOT EXISTS idx_indicator_graph_target ON indicator_graph(target_indicator);
CREATE INDEX IF NOT EXISTS idx_expert_graph_source ON expert_graph(source_node);
CREATE INDEX IF NOT EXISTS idx_expert_graph_target ON expert_graph(target_node);
CREATE INDEX IF NOT EXISTS idx_indicator_dept_mapping_indicator ON indicator_department_mapping(indicator_name);
CREATE INDEX IF NOT EXISTS idx_indicator_dept_mapping_dept ON indicator_department_mapping(department_name);

-- ============================================
-- 双图初始数据
-- ============================================

-- 初始化图1：化验指标生理关联图
INSERT INTO indicator_graph (source_indicator, target_indicator, relation_type, weight, description) VALUES
-- 肾功能系统内的关联
('Cr', 'BUN', 'POSITIVE_CORR', 0.95, '肌酐与尿素氮正相关，同属肾功能代谢产物'),
('Cr', 'UA', 'POSITIVE_CORR', 0.85, '肌酐与尿酸正相关，均通过肾脏排泄'),
('BUN', 'UA', 'POSITIVE_CORR', 0.80, '尿素氮与尿酸正相关，反映肾功能状态'),
('Cr', 'eGFR', 'NEGATIVE_CORR', 0.92, '肌酐升高，肾小球滤过率下降'),
-- 肝功能系统内的关联
('ALT', 'AST', 'POSITIVE_CORR', 0.88, '丙氨酸转氨酶与天冬氨酸转氨酶正相关'),
('ALT', 'TBIL', 'POSITIVE_CORR', 0.80, '转氨酶升高可能伴随胆红素升高'),
('AST', 'TBIL', 'POSITIVE_CORR', 0.82, '天冬氨酸转氨酶与胆红素正相关'),
-- 血液系统内的关联
('RBC', 'Hb', 'POSITIVE_CORR', 0.90, '红细胞与血红蛋白正相关'),
('RBC', 'PLT', 'POSITIVE_CORR', 0.60, '红细胞与血小板弱相关'),
('WBC', 'PLT', 'POSITIVE_CORR', 0.65, '白细胞与血小板弱相关'),
('Hb', 'RDW', 'NEGATIVE_CORR', 0.70, '血红蛋白与红细胞分布宽度可能负相关'),
-- 血糖系统
('GLU', 'HbA1c', 'POSITIVE_CORR', 0.85, '血糖升高，糖化血红蛋白升高'),
-- 临床路径
('GLU', 'Cr', 'CLINICAL_PATH', 0.75, '血糖异常患者应检查肾功能'),
('Cr', 'Na', 'CLINICAL_PATH', 0.70, '肾功能异常时需评估电解质'),
('ALT', 'BNP', 'CLINICAL_PATH', 0.60, '肝脏与心脏在某些系统性疾病中关联'),
-- 心肌标志物
('CK-MB', 'Troponin', 'POSITIVE_CORR', 0.85, '心肌酶与心肌肽标志物正相关'),
('CK-MB', 'BNP', 'POSITIVE_CORR', 0.80, '心肌酶升高时BNP可能升高')
ON CONFLICT (source_indicator, target_indicator) DO NOTHING;

-- 初始化图2：专家协作图
INSERT INTO expert_graph (source_node, source_type, target_node, target_type, relation_type, weight, description) VALUES
-- 肾内科与其他科室的协作
('RenalDepartment', 'DEPARTMENT', 'LaboratoryDepartment', 'DEPARTMENT', 'PRECEDES', 0.95, '调用肾内科前应先获得检验科的尿常规结果'),
('RenalDepartment', 'DEPARTMENT', 'CardiologyDepartment', 'DEPARTMENT', 'COLLABORATE', 0.85, '肾功能异常时常需心内科评估（肾性高血压等）'),
('RenalDepartment', 'DEPARTMENT', 'EndocrinologyDepartment', 'DEPARTMENT', 'COLLABORATE', 0.75, '肾功能异常时需排除糖代谢异常'),
-- 心内科与其他科室的协作
('CardiologyDepartment', 'DEPARTMENT', 'LaboratoryDepartment', 'DEPARTMENT', 'PRECEDES', 0.90, '调用心内科前应先获得心肌标志物结果'),
('CardiologyDepartment', 'DEPARTMENT', 'RenalDepartment', 'DEPARTMENT', 'COLLABORATE', 0.80, '心脏病患者需关注肾功能'),
-- 血液科与其他科室的协作
('HematologyDepartment', 'DEPARTMENT', 'LaboratoryDepartment', 'DEPARTMENT', 'PRECEDES', 0.95, '血液科诊断前需完整血象检查'),
('HematologyDepartment', 'DEPARTMENT', 'InfectiousDepartment', 'DEPARTMENT', 'COLLABORATE', 0.70, '感染导致的血象异常需两科协作'),
-- 内分泌科与其他科室的协作
('EndocrinologyDepartment', 'DEPARTMENT', 'LaboratoryDepartment', 'DEPARTMENT', 'PRECEDES', 0.95, '调用内分泌科前需血糖、电解质结果'),
('EndocrinologyDepartment', 'DEPARTMENT', 'RenalDepartment', 'DEPARTMENT', 'COLLABORATE', 0.75, '糖尿病肾病需两科联合管理'),
-- 感染科与其他科室的协作
('InfectiousDepartment', 'DEPARTMENT', 'HematologyDepartment', 'DEPARTMENT', 'COLLABORATE', 0.80, '感染常伴血象改变'),
('InfectiousDepartment', 'DEPARTMENT', 'RenalDepartment', 'DEPARTMENT', 'COLLABORATE', 0.70, '感染可导致肾功能异常'),
-- 检验科总是前置依赖
('LaboratoryDepartment', 'DEPARTMENT', 'RenalDepartment', 'DEPARTMENT', 'PRECEDES', 1.0, '检验科结果是肾内科诊断的基础'),
('LaboratoryDepartment', 'DEPARTMENT', 'CardiologyDepartment', 'DEPARTMENT', 'PRECEDES', 1.0, '检验科结果是心内科诊断的基础'),
('LaboratoryDepartment', 'DEPARTMENT', 'HematologyDepartment', 'DEPARTMENT', 'PRECEDES', 1.0, '检验科结果是血液科诊断的基础'),
('LaboratoryDepartment', 'DEPARTMENT', 'EndocrinologyDepartment', 'DEPARTMENT', 'PRECEDES', 1.0, '检验科结果是内分泌科诊断的基础')
ON CONFLICT (source_node, target_node) DO NOTHING;

-- 初始化指标与科室的映射表
INSERT INTO indicator_department_mapping (indicator_name, department_name, relevance_score) VALUES
-- 肾功能指标
('Cr', 'RenalDepartment', 0.98),
('BUN', 'RenalDepartment', 0.97),
('UA', 'RenalDepartment', 0.95),
('eGFR', 'RenalDepartment', 0.99),
-- 肝功能指标
('ALT', 'GastroenterologyDepartment', 0.90),
('AST', 'GastroenterologyDepartment', 0.90),
('TBIL', 'GastroenterologyDepartment', 0.95),
('GGT', 'GastroenterologyDepartment', 0.85),
-- 血液指标
('WBC', 'HematologyDepartment', 0.98),
('RBC', 'HematologyDepartment', 0.97),
('PLT', 'HematologyDepartment', 0.97),
('Hb', 'HematologyDepartment', 0.98),
-- 血糖指标
('GLU', 'EndocrinologyDepartment', 0.95),
('HbA1c', 'EndocrinologyDepartment', 0.97),
-- 心肌标志物
('CK-MB', 'CardiologyDepartment', 0.96),
('Troponin', 'CardiologyDepartment', 0.98),
('BNP', 'CardiologyDepartment', 0.94),
-- 电解质
('Na', 'RenalDepartment', 0.80),
('K', 'RenalDepartment', 0.85),
('Cl', 'RenalDepartment', 0.75)
ON CONFLICT (indicator_name, department_name) DO NOTHING;

-- ============================================
-- 测试用户初始化
-- ============================================
-- 创建默认测试用户用于快速验证系统
-- 身份证号：110101199001011234
-- 密码：123456

INSERT INTO users (id, real_name, id_number, password_hash, drug_allergy, lifetime_medical_history) 
VALUES (
    gen_random_uuid(),
    'Li Ming',
    '110101199001011234',
    '$2a$10$Ej.GtXBvScWYvNxHhAZvJ.FgVLdVqN7LN.0H5WK5Yp5YkPqA5PsRC',
    'No known allergies',
    'No significant medical history'
)
ON CONFLICT (id_number) DO NOTHING;
