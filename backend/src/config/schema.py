from sqlalchemy import inspect, text

# 没有在线版本迁移执行器；对已有库补上新增列，新表由 create_all 建立。
COLUMNS = {
    'outreaches': {
        'parent_outreach_id': 'INTEGER REFERENCES outreaches(id)',
        'root_outreach_id': 'INTEGER REFERENCES outreaches(id)',
        'resend_for_batch_id': 'INTEGER',
        'created': 'VARCHAR(40) DEFAULT \'\'',
        'receipt_watermark': 'INTEGER DEFAULT 0',
    },
}


def ensure_columns(engine):
    if engine.dialect.name != 'postgresql':
        return
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns in COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {column['name'] for column in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in present:
                    connection.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {ddl}'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS ix_outreaches_root_outreach_id ON outreaches (root_outreach_id)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS ix_outreaches_resend_for_batch_id ON outreaches (resend_for_batch_id)'))
