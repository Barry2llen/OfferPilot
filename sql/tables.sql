CREATE TABLE IF NOT EXISTS tb_model_providers (
    name VARCHAR(255) PRIMARY KEY,
    provider VARCHAR(32) NOT NULL CHECK (
        provider IN ('openai', 'anthropic', 'google', 'openai compatible')
    ),
    model VARCHAR(255) NOT NULL,
    base_url VARCHAR(255),
    api_key VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS tb_chats (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    messages JSON NOT NULL
);
