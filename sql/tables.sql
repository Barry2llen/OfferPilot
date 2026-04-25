-- Reference schema snapshot. Runtime table initialization uses ORM metadata.

CREATE TABLE IF NOT EXISTS tb_model_provider (
    name VARCHAR(255) PRIMARY KEY,
    provider VARCHAR(32) NOT NULL,
    base_url VARCHAR(255),
    api_key VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS tb_model_selection (
    id INTEGER PRIMARY KEY,
    provider_name VARCHAR(255) NOT NULL,
    model_name VARCHAR(255) NOT NULL,
    supports_image_input BOOLEAN NOT NULL DEFAULT FALSE,
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

CREATE TABLE IF NOT EXISTS tb_resume (
    id INTEGER PRIMARY KEY,
    file_path VARCHAR(512),
    content TEXT NOT NULL,
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    original_filename VARCHAR(255),
    media_type VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS tb_graph_checkpoint (
    thread_id VARCHAR(255) NOT NULL,
    checkpoint_ns VARCHAR(255) NOT NULL DEFAULT '',
    checkpoint_id VARCHAR(255) NOT NULL,
    parent_checkpoint_id VARCHAR(255),
    checkpoint_type VARCHAR(64) NOT NULL,
    checkpoint_payload BYTEA NOT NULL,
    metadata_type VARCHAR(64) NOT NULL,
    metadata_payload BYTEA NOT NULL,
    source VARCHAR(32),
    step INTEGER,
    run_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE INDEX IF NOT EXISTS ix_tb_graph_checkpoint_run_id
ON tb_graph_checkpoint (run_id);

CREATE TABLE IF NOT EXISTS tb_graph_checkpoint_blob (
    thread_id VARCHAR(255) NOT NULL,
    checkpoint_ns VARCHAR(255) NOT NULL DEFAULT '',
    channel VARCHAR(255) NOT NULL,
    version VARCHAR(255) NOT NULL,
    value_type VARCHAR(64) NOT NULL,
    value_payload BYTEA NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE TABLE IF NOT EXISTS tb_graph_checkpoint_write (
    id INTEGER PRIMARY KEY,
    thread_id VARCHAR(255) NOT NULL,
    checkpoint_ns VARCHAR(255) NOT NULL DEFAULT '',
    checkpoint_id VARCHAR(255) NOT NULL,
    task_id VARCHAR(255) NOT NULL,
    write_idx INTEGER NOT NULL,
    channel VARCHAR(255) NOT NULL,
    value_type VARCHAR(64) NOT NULL,
    value_payload BYTEA NOT NULL,
    task_path VARCHAR(512) NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
);

CREATE INDEX IF NOT EXISTS ix_tb_graph_checkpoint_write_thread_id
ON tb_graph_checkpoint_write (thread_id);

CREATE INDEX IF NOT EXISTS ix_tb_graph_checkpoint_write_checkpoint_id
ON tb_graph_checkpoint_write (checkpoint_id);
