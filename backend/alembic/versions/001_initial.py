"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-07-13

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # Users 表
    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) UNIQUE NOT NULL,
            username VARCHAR(100) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.create_index('idx_users_email', 'users', ['email'])

    # Projects 表
    op.execute("""
        CREATE TABLE projects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
            title VARCHAR(255) NOT NULL,
            core_idea TEXT NOT NULL,
            genre VARCHAR(50),
            tone_style VARCHAR(100),
            target_word_count INT DEFAULT 100000,
            status VARCHAR(20) DEFAULT 'draft',
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.create_index('idx_projects_user_id', 'projects', ['user_id'])

    # Entities 表
    op.execute("""
        CREATE TABLE entities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID REFERENCES projects(id) ON DELETE CASCADE NOT NULL,
            type VARCHAR(50) NOT NULL,
            name VARCHAR(100) NOT NULL,
            display_name VARCHAR(100) NOT NULL,
            description TEXT,
            data JSONB DEFAULT '{}',
            version INT DEFAULT 1,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.create_index('idx_entities_project_id', 'entities', ['project_id'])
    op.create_index('idx_entities_type', 'entities', ['type'])

    # Foreshadowings 表
    op.execute("""
        CREATE TABLE foreshadowings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID REFERENCES projects(id) ON DELETE CASCADE NOT NULL,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            sow_chapter INT,
            reap_chapter INT,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.create_index('idx_foreshadowings_project_id', 'foreshadowings', ['project_id'])

    # Plot Threads 表
    op.execute("""
        CREATE TABLE plot_threads (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID REFERENCES projects(id) ON DELETE CASCADE NOT NULL,
            entity_id UUID REFERENCES entities(id) ON DELETE SET NULL,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            start_chapter INT,
            end_chapter INT,
            priority INT DEFAULT 1,
            status VARCHAR(20) DEFAULT 'active',
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.create_index('idx_plot_threads_project_id', 'plot_threads', ['project_id'])

    # Chapters 表
    op.execute("""
        CREATE TABLE chapters (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID REFERENCES projects(id) ON DELETE CASCADE NOT NULL,
            volume_number INT DEFAULT 1,
            chapter_number INT NOT NULL,
            title VARCHAR(200),
            outline JSONB,
            word_count INT DEFAULT 0,
            status VARCHAR(20) DEFAULT 'planned',
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.create_index('idx_chapters_project_id', 'chapters', ['project_id'])
    op.create_index('idx_chapters_chapter_number', 'chapters', ['project_id', 'chapter_number'])

    # Scenes 表
    op.execute("""
        CREATE TABLE scenes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            chapter_id UUID REFERENCES chapters(id) ON DELETE CASCADE NOT NULL,
            project_id UUID REFERENCES projects(id) ON DELETE CASCADE NOT NULL,
            scene_number INT NOT NULL,
            title VARCHAR(200),
            location VARCHAR(200),
            time_period VARCHAR(100),
            constraint_card JSONB,
            content TEXT,
            word_count INT DEFAULT 0,
            pov_character_id UUID REFERENCES entities(id) ON DELETE SET NULL,
            qdrant_point_id VARCHAR(100),
            status VARCHAR(20) DEFAULT 'planned',
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.create_index('idx_scenes_chapter_id', 'scenes', ['chapter_id'])
    op.create_index('idx_scenes_project_id', 'scenes', ['project_id'])
    op.create_index('idx_scenes_scene_number', 'scenes', ['chapter_id', 'scene_number'])

    # Review Suggestions 表
    op.execute("""
        CREATE TABLE review_suggestions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scene_id UUID REFERENCES scenes(id) ON DELETE CASCADE NOT NULL,
            severity VARCHAR(20),
            category VARCHAR(50),
            description TEXT NOT NULL,
            suggestion TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.create_index('idx_review_suggestions_scene_id', 'review_suggestions', ['scene_id'])


def downgrade() -> None:
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
    op.drop_index('idx_review_suggestions_scene_id')
    op.execute('DROP TABLE IF EXISTS review_suggestions')
    op.drop_index('idx_scenes_scene_number')
    op.drop_index('idx_scenes_project_id')
    op.drop_index('idx_scenes_chapter_id')
    op.execute('DROP TABLE IF EXISTS scenes')
    op.drop_index('idx_chapters_chapter_number')
    op.drop_index('idx_chapters_project_id')
    op.execute('DROP TABLE IF EXISTS chapters')
    op.drop_index('idx_plot_threads_project_id')
    op.execute('DROP TABLE IF EXISTS plot_threads')
    op.drop_index('idx_foreshadowings_project_id')
    op.execute('DROP TABLE IF EXISTS foreshadowings')
    op.drop_index('idx_entities_type')
    op.drop_index('idx_entities_project_id')
    op.execute('DROP TABLE IF EXISTS entities')
    op.drop_index('idx_projects_user_id')
    op.execute('DROP TABLE IF EXISTS projects')
    op.drop_index('idx_users_email')
    op.execute('DROP TABLE IF EXISTS users')
