"""Add custom vocabulary tables

Revision ID: 003_custom_vocabulary
Revises: 002
Create Date: 2025-01-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers
revision = '003_custom_vocabulary'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    """Add custom vocabulary tables for acronym expansion"""
    
    # Create custom_vocabulary table
    op.create_table(
        'custom_vocabulary',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('term', sa.String(100), nullable=False, index=True),
        sa.Column('expansion', sa.String(500), nullable=False),
        sa.Column('category', sa.String(50), nullable=True),  # defense, medical, finance, etc.
        sa.Column('industry', sa.String(50), nullable=True),
        sa.Column('priority', sa.Integer(), default=0),  # Higher priority = prefer this expansion
        sa.Column('context_hints', postgresql.ARRAY(sa.Text), nullable=True),  # Words that suggest this meaning
        sa.Column('case_sensitive', sa.Boolean(), default=False),
        sa.Column('regex_pattern', sa.String(200), nullable=True),  # Optional regex for complex matching
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('usage_count', sa.Integer(), default=0),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    
    # Create unique constraint on term + category
    op.create_unique_constraint(
        'uq_vocabulary_term_category',
        'custom_vocabulary',
        ['term', 'category']
    )
    
    # Create vocabulary_sets table
    op.create_table(
        'vocabulary_sets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_default', sa.Boolean(), default=False),  # Auto-apply to all sessions
        sa.Column('industry', sa.String(50), nullable=True),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('vocab_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column('settings', postgresql.JSONB, nullable=True),  # Additional configuration
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    
    # Create session_vocabulary table (link sessions to vocabulary sets)
    op.create_table(
        'session_vocabulary',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('vocabulary_set_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('applied_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('applied_to_live', sa.Boolean(), default=False),
        sa.Column('applied_to_final', sa.Boolean(), default=False),
    )
    
    # Add foreign key constraints
    op.create_foreign_key(
        'fk_session_vocabulary_set',
        'session_vocabulary',
        'vocabulary_sets',
        ['vocabulary_set_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Create indexes for performance
    op.create_index('idx_vocabulary_term', 'custom_vocabulary', ['term'])
    op.create_index('idx_vocabulary_category', 'custom_vocabulary', ['category'])
    op.create_index('idx_vocabulary_active', 'custom_vocabulary', ['is_active'])
    op.create_index('idx_vocabulary_sets_active', 'vocabulary_sets', ['is_active'])
    op.create_index('idx_session_vocabulary_session', 'session_vocabulary', ['session_id'])
    
    # Insert default vocabulary for defense sector
    op.execute("""
        INSERT INTO vocabulary_sets (id, name, description, industry, category, is_active, is_default)
        VALUES 
        (gen_random_uuid(), 'Defense Acronyms', 'Common defense and military acronyms', 'defense', 'military', true, true)
    """)
    
    # Insert sample defense acronyms
    op.execute("""
        INSERT INTO custom_vocabulary (id, term, expansion, category, industry, priority, context_hints)
        VALUES
        (gen_random_uuid(), 'DOD', 'Department of Defense', 'military', 'defense', 100, ARRAY['military', 'pentagon', 'defense']),
        (gen_random_uuid(), 'DARPA', 'Defense Advanced Research Projects Agency', 'military', 'defense', 100, ARRAY['research', 'defense', 'agency']),
        (gen_random_uuid(), 'NATO', 'North Atlantic Treaty Organization', 'military', 'defense', 100, ARRAY['alliance', 'military', 'treaty']),
        (gen_random_uuid(), 'ROE', 'Rules of Engagement', 'military', 'defense', 90, ARRAY['combat', 'military', 'rules']),
        (gen_random_uuid(), 'IED', 'Improvised Explosive Device', 'military', 'defense', 90, ARRAY['explosive', 'bomb', 'device']),
        (gen_random_uuid(), 'UAV', 'Unmanned Aerial Vehicle', 'military', 'defense', 90, ARRAY['drone', 'aircraft', 'unmanned']),
        (gen_random_uuid(), 'C2', 'Command and Control', 'military', 'defense', 85, ARRAY['command', 'control', 'military']),
        (gen_random_uuid(), 'ISR', 'Intelligence, Surveillance, and Reconnaissance', 'military', 'defense', 85, ARRAY['intelligence', 'surveillance', 'recon']),
        (gen_random_uuid(), 'OPSEC', 'Operations Security', 'military', 'defense', 85, ARRAY['operations', 'security', 'military']),
        (gen_random_uuid(), 'SITREP', 'Situation Report', 'military', 'defense', 80, ARRAY['situation', 'report', 'status']),
        (gen_random_uuid(), 'EOD', 'Explosive Ordnance Disposal', 'military', 'defense', 80, ARRAY['explosive', 'disposal', 'bomb']),
        (gen_random_uuid(), 'QRF', 'Quick Reaction Force', 'military', 'defense', 80, ARRAY['quick', 'reaction', 'force']),
        (gen_random_uuid(), 'AOR', 'Area of Responsibility', 'military', 'defense', 75, ARRAY['area', 'responsibility', 'region']),
        (gen_random_uuid(), 'FOB', 'Forward Operating Base', 'military', 'defense', 75, ARRAY['forward', 'base', 'operating']),
        (gen_random_uuid(), 'MEDEVAC', 'Medical Evacuation', 'military', 'defense', 75, ARRAY['medical', 'evacuation', 'casualty'])
    """)


def downgrade():
    """Remove custom vocabulary tables"""
    op.drop_index('idx_session_vocabulary_session')
    op.drop_index('idx_vocabulary_sets_active')
    op.drop_index('idx_vocabulary_active')
    op.drop_index('idx_vocabulary_category')
    op.drop_index('idx_vocabulary_term')
    
    op.drop_table('session_vocabulary')
    op.drop_table('vocabulary_sets')
    op.drop_table('custom_vocabulary')