-- Reference schema snapshot. Runtime table initialization uses ORM metadata.

CREATE TABLE IF NOT EXISTS tb_model_provider (
    name VARCHAR(255) PRIMARY KEY,
    provider VARCHAR(32) NOT NULL CHECK (
        provider IN ('openai', 'anthropic', 'google', 'openai compatible')
    ),
    base_url VARCHAR(255),
    api_key VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS tb_model_selection (
    id INTEGER PRIMARY KEY,
    provider_name VARCHAR(255) NOT NULL,
    model_name VARCHAR(255) NOT NULL,
    UNIQUE (provider_name, model_name),
    FOREIGN KEY (provider_name) REFERENCES tb_model_provider(name)
);

CREATE TABLE IF NOT EXISTS tb_chat (
    id INTEGER PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    messages JSON default '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
