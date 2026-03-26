ALTER TABLE validator_status_current ADD COLUMN annual_provisions_raw TEXT;
ALTER TABLE validator_status_current ADD COLUMN apr_percent FLOAT;

ALTER TABLE validator_status_history ADD COLUMN annual_provisions_raw TEXT;
ALTER TABLE validator_status_history ADD COLUMN apr_percent FLOAT;

CREATE INDEX IF NOT EXISTS ix_validator_status_current_apr_percent
ON validator_status_current (apr_percent);

CREATE INDEX IF NOT EXISTS ix_validator_status_history_apr_percent
ON validator_status_history (apr_percent);
