-- Supabase 数据库初始化脚本
-- 使用方法：在 Supabase SQL Editor 中执行此脚本

-- 创建 usage 表（记录每个 API Key 的使用次数和激活状态）
CREATE TABLE IF NOT EXISTS usage (
    id BIGSERIAL PRIMARY KEY,
    api_key_hash TEXT NOT NULL UNIQUE,  -- API Key 的 SHA-256 哈希
    date TEXT NOT NULL,                  -- 日期，格式 YYYY-MM-DD
    count INTEGER DEFAULT 0,             -- 今日使用次数
    activated BOOLEAN DEFAULT FALSE,     -- 是否已激活
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建 activation_codes 表（存储激活码）
CREATE TABLE IF NOT EXISTS activation_codes (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,           -- 激活码
    used BOOLEAN DEFAULT FALSE,          -- 是否已使用
    used_by TEXT,                        -- 被哪个 API Key Hash 使用
    used_at TEXT,                        -- 使用时间，格式 YYYY-MM-DD HH:MM:SS
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 插入预置激活码
INSERT INTO activation_codes (code, used, used_by, used_at) VALUES
    ('TCGEN-PRO-2026A', FALSE, NULL, NULL),
    ('TCGEN-PRO-2026B', FALSE, NULL, NULL),
    ('TCGEN-PRO-2026C', FALSE, NULL, NULL),
    ('TCGEN-PRO-2026D', FALSE, NULL, NULL),
    ('TCGEN-PRO-2026E', FALSE, NULL, NULL)
ON CONFLICT (code) DO NOTHING;

-- 创建索引（提升查询性能）
CREATE INDEX IF NOT EXISTS idx_usage_api_key_hash ON usage(api_key_hash);
CREATE INDEX IF NOT EXISTS idx_activation_codes_code ON activation_codes(code);

-- 启用行级安全（RLS）- 仅允许认证用户读写
ALTER TABLE usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE activation_codes ENABLE ROW LEVEL SECURITY;

-- 允许所有操作（生产环境应更严格）
CREATE POLICY "Allow all access to usage" ON usage FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all access to activation_codes" ON activation_codes FOR ALL USING (true) WITH CHECK (true);

-- 添加 updated_at 自动更新触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_usage_updated_at BEFORE UPDATE ON usage
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();