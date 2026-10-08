"""initial schema (generated from metadata, no live DB)."""

revision = "f2e21130cdc8"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    # pg_trgm not available in embedded PG; search uses LIKE
    pass  # op.execute("""CREATE EXTENSION IF NOT EXISTS pg_trgm;""")
    op.execute("""CREATE SEQUENCE IF NOT EXISTS change_set_seq;""")
    op.execute("""CREATE TABLE actors (
	id UUID NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	display_name VARCHAR(200) NOT NULL, 
	password_hash VARCHAR(255), 
	active BOOLEAN DEFAULT true NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_actors_kind CHECK (kind IN ('owner', 'agent'))
);""")
    op.execute("""CREATE TABLE api_tokens (
	id UUID NOT NULL, 
	actor_id UUID NOT NULL, 
	public_id VARCHAR(64) NOT NULL, 
	secret_digest VARCHAR(255) NOT NULL, 
	scopes JSONB DEFAULT '[]'::jsonb NOT NULL, 
	last_used_at TIMESTAMP WITH TIME ZONE, 
	revoked_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_id) REFERENCES actors (id), 
	UNIQUE (public_id)
);""")
    op.execute("""CREATE TABLE bibliographic_records (
	record_type VARCHAR(32) NOT NULL, 
	title TEXT NOT NULL, 
	year INTEGER, 
	language VARCHAR(16), 
	doi_normalized VARCHAR(255), 
	publication JSONB NOT NULL, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	is_verified BOOLEAN NOT NULL, 
	verified_by UUID, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	verified_revision BIGINT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_bib_records_record_type CHECK (record_type IN ('journal', 'book', 'chapter', 'thesis')), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id), 
	FOREIGN KEY(verified_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE UNIQUE INDEX uq_bib_records_active_doi ON bibliographic_records (doi_normalized) WHERE archived_at IS NULL AND doi_normalized IS NOT NULL;""")
    op.execute("""CREATE TABLE categories (
	parent_id UUID, 
	name VARCHAR(200) NOT NULL, 
	description TEXT, 
	sort_key VARCHAR(64) DEFAULT '' NOT NULL, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	is_verified BOOLEAN NOT NULL, 
	verified_by UUID, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	verified_revision BIGINT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(parent_id) REFERENCES categories (id), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id), 
	FOREIGN KEY(verified_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE TABLE change_sets (
	id UUID NOT NULL, 
	sequence_no BIGINT NOT NULL, 
	actor_id UUID NOT NULL, 
	operation VARCHAR(64) NOT NULL, 
	summary TEXT NOT NULL, 
	request_id VARCHAR(128), 
	reverts_change_set_id UUID, 
	root_effect_change_set_id UUID NOT NULL, 
	effect_direction VARCHAR(16) NOT NULL, 
	snapshot_schema_version INTEGER DEFAULT 1 NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_change_sets_effect_direction CHECK (effect_direction IN ('forward', 'inverse')), 
	UNIQUE (sequence_no), 
	FOREIGN KEY(actor_id) REFERENCES actors (id), 
	FOREIGN KEY(reverts_change_set_id) REFERENCES change_sets (id), 
	FOREIGN KEY(root_effect_change_set_id) REFERENCES change_sets (id)
);""")
    op.execute("""CREATE TABLE dimension_kinds (
	code VARCHAR(64) NOT NULL, 
	name_cn VARCHAR(200) NOT NULL, 
	description TEXT, 
	sort_order INTEGER DEFAULT 0 NOT NULL, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE TABLE field_definitions (
	key VARCHAR(128) NOT NULL, 
	label VARCHAR(200) NOT NULL, 
	entity_kind VARCHAR(64) NOT NULL, 
	value_type VARCHAR(32) NOT NULL, 
	description TEXT, 
	options JSONB DEFAULT '[]'::jsonb NOT NULL, 
	is_system BOOLEAN DEFAULT false NOT NULL, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_field_definitions_value_type CHECK (value_type IN ('text', 'long_text', 'number', 'boolean', 'single_select', 'multi_select')), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE UNIQUE INDEX uq_field_definitions_active_key ON field_definitions (entity_kind, key) WHERE archived_at IS NULL;""")
    op.execute("""CREATE TABLE idempotency_records (
	id UUID NOT NULL, 
	actor_id UUID NOT NULL, 
	key VARCHAR(128) NOT NULL, 
	request_digest VARCHAR(128) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	response_body JSONB, 
	response_headers JSONB, 
	change_set_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_idempotency_records_actor_key UNIQUE (actor_id, key), 
	FOREIGN KEY(actor_id) REFERENCES actors (id)
);""")
    op.execute("""CREATE TABLE issues (
	title VARCHAR(300) NOT NULL, 
	summary TEXT, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	is_verified BOOLEAN NOT NULL, 
	verified_by UUID, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	verified_revision BIGINT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id), 
	FOREIGN KEY(verified_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE TABLE persons (
	primary_name VARCHAR(300) NOT NULL, 
	aliases JSONB NOT NULL, 
	note TEXT, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	is_verified BOOLEAN NOT NULL, 
	verified_by UUID, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	verified_revision BIGINT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id), 
	FOREIGN KEY(verified_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE TABLE relation_kinds (
	code VARCHAR(64) NOT NULL, 
	name_cn VARCHAR(200) NOT NULL, 
	description TEXT, 
	sort_order INTEGER DEFAULT 0 NOT NULL, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE TABLE sessions (
	id UUID NOT NULL, 
	session_digest VARCHAR(255) NOT NULL, 
	actor_id UUID NOT NULL, 
	csrf_digest VARCHAR(255) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	revoked_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (session_digest), 
	FOREIGN KEY(actor_id) REFERENCES actors (id)
);""")
    op.execute("""CREATE TABLE anchor_adjustments (
	id UUID NOT NULL, 
	change_set_id UUID NOT NULL, 
	anchor_id UUID NOT NULL, 
	old_start_order INTEGER, 
	old_end_order INTEGER, 
	new_start_order INTEGER, 
	new_end_order INTEGER, 
	content_changed BOOLEAN DEFAULT false NOT NULL, 
	display_range_changed BOOLEAN DEFAULT false NOT NULL, 
	validity_changed BOOLEAN DEFAULT false NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(change_set_id) REFERENCES change_sets (id) ON DELETE CASCADE
);""")
    op.execute("""CREATE TABLE bibliographic_contributors (
	record_id UUID NOT NULL, 
	person_id UUID, 
	literal_name VARCHAR(300), 
	role VARCHAR(32) DEFAULT 'author' NOT NULL, 
	ordinal INTEGER NOT NULL, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(record_id) REFERENCES bibliographic_records (id), 
	FOREIGN KEY(person_id) REFERENCES persons (id), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE UNIQUE INDEX uq_bib_contrib_active ON bibliographic_contributors (record_id, role, ordinal) WHERE archived_at IS NULL;""")
    op.execute("""CREATE TABLE change_effect_states (
	root_effect_change_set_id UUID NOT NULL, 
	is_applied BOOLEAN DEFAULT true NOT NULL, 
	last_toggle_change_set_id UUID NOT NULL, 
	PRIMARY KEY (root_effect_change_set_id), 
	FOREIGN KEY(root_effect_change_set_id) REFERENCES change_sets (id) ON DELETE CASCADE, 
	FOREIGN KEY(last_toggle_change_set_id) REFERENCES change_sets (id)
);""")
    op.execute("""CREATE TABLE change_items (
	id UUID NOT NULL, 
	change_set_id UUID NOT NULL, 
	entity_kind VARCHAR(64) NOT NULL, 
	entity_id UUID NOT NULL, 
	before_revision BIGINT, 
	after_revision BIGINT, 
	before JSONB, 
	after JSONB, 
	changed_fields JSONB DEFAULT '[]'::jsonb NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(change_set_id) REFERENCES change_sets (id) ON DELETE CASCADE
);""")
    op.execute("""CREATE TABLE discourses (
	bibliographic_record_id UUID, 
	title VARCHAR(500) NOT NULL, 
	source_locator JSONB NOT NULL, 
	attribution_note TEXT, 
	paragraph_revision BIGINT NOT NULL, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(bibliographic_record_id) REFERENCES bibliographic_records (id), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE TABLE issue_categories (
	issue_id UUID NOT NULL, 
	category_id UUID NOT NULL, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(issue_id) REFERENCES issues (id), 
	FOREIGN KEY(category_id) REFERENCES categories (id), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE UNIQUE INDEX uq_issue_categories_active ON issue_categories (issue_id, category_id) WHERE archived_at IS NULL;""")
    op.execute("""CREATE TABLE paragraph_lineage (
	id UUID NOT NULL, 
	change_set_id UUID NOT NULL, 
	step_index INTEGER NOT NULL, 
	command_type VARCHAR(32) NOT NULL, 
	discourse_id UUID NOT NULL, 
	source_ids JSONB DEFAULT '[]'::jsonb NOT NULL, 
	source_orders JSONB DEFAULT '[]'::jsonb NOT NULL, 
	target_ids JSONB DEFAULT '[]'::jsonb NOT NULL, 
	target_orders JSONB DEFAULT '[]'::jsonb NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(change_set_id) REFERENCES change_sets (id) ON DELETE CASCADE
);""")
    op.execute("""CREATE TABLE anchor_adjustment_relations (
	adjustment_id UUID NOT NULL, 
	relation_id UUID NOT NULL, 
	PRIMARY KEY (adjustment_id, relation_id), 
	FOREIGN KEY(adjustment_id) REFERENCES anchor_adjustments (id) ON DELETE CASCADE
);""")
    op.execute("""CREATE TABLE issue_discourses (
	issue_id UUID NOT NULL, 
	discourse_id UUID NOT NULL, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(issue_id) REFERENCES issues (id), 
	FOREIGN KEY(discourse_id) REFERENCES discourses (id), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE UNIQUE INDEX uq_issue_discourses_active ON issue_discourses (issue_id, discourse_id) WHERE archived_at IS NULL;""")
    op.execute("""CREATE TABLE paragraphs (
	discourse_id UUID NOT NULL, 
	text TEXT NOT NULL, 
	current_order INTEGER, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_paragraphs_discourse_order UNIQUE (discourse_id, current_order) DEFERRABLE INITIALLY DEFERRED, 
	FOREIGN KEY(discourse_id) REFERENCES discourses (id), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE TABLE anchors (
	discourse_id UUID NOT NULL, 
	start_paragraph_id UUID, 
	end_paragraph_id UUID, 
	title VARCHAR(300), 
	note TEXT, 
	is_valid BOOLEAN NOT NULL, 
	invalid_reason VARCHAR(64), 
	last_known_range JSONB, 
	is_verified BOOLEAN NOT NULL, 
	verified_by UUID, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	verified_revision BIGINT, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(discourse_id) REFERENCES discourses (id), 
	FOREIGN KEY(start_paragraph_id) REFERENCES paragraphs (id), 
	FOREIGN KEY(end_paragraph_id) REFERENCES paragraphs (id), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE TABLE relations (
	issue_id UUID NOT NULL, 
	source_anchor_id UUID NOT NULL, 
	target_anchor_id UUID NOT NULL, 
	relation_kind_id UUID NOT NULL, 
	basis VARCHAR(32) NOT NULL, 
	reason TEXT NOT NULL, 
	source_anchor_revision_at_creation BIGINT NOT NULL, 
	target_anchor_revision_at_creation BIGINT NOT NULL, 
	source_anchor_revision_at_verification BIGINT, 
	target_anchor_revision_at_verification BIGINT, 
	is_verified BOOLEAN DEFAULT false NOT NULL, 
	verified_by UUID, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	verified_revision BIGINT, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_relations_basis CHECK (basis IN ('author_explicit', 'analyst_inferred')), 
	FOREIGN KEY(issue_id) REFERENCES issues (id), 
	FOREIGN KEY(source_anchor_id) REFERENCES anchors (id), 
	FOREIGN KEY(target_anchor_id) REFERENCES anchors (id), 
	FOREIGN KEY(relation_kind_id) REFERENCES relation_kinds (id), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE TABLE annotations (
	anchor_id UUID, 
	relation_id UUID, 
	body TEXT NOT NULL, 
	is_verified BOOLEAN DEFAULT false NOT NULL, 
	verified_by UUID, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	verified_revision BIGINT, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_annotation_single_target CHECK ((anchor_id IS NOT NULL)::int + (relation_id IS NOT NULL)::int = 1), 
	FOREIGN KEY(anchor_id) REFERENCES anchors (id), 
	FOREIGN KEY(relation_id) REFERENCES relations (id), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE TABLE relation_dimensions (
	relation_id UUID NOT NULL, 
	dimension_kind_id UUID NOT NULL, 
	id UUID NOT NULL, 
	revision BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_by UUID NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	archived_by UUID, 
	attributes JSONB NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(relation_id) REFERENCES relations (id), 
	FOREIGN KEY(dimension_kind_id) REFERENCES dimension_kinds (id), 
	FOREIGN KEY(created_by) REFERENCES actors (id), 
	FOREIGN KEY(updated_by) REFERENCES actors (id), 
	FOREIGN KEY(archived_by) REFERENCES actors (id)
);""")
    op.execute("""CREATE UNIQUE INDEX uq_relation_dimensions_active ON relation_dimensions (relation_id, dimension_kind_id) WHERE archived_at IS NULL;""")
    op.execute("""ALTER TABLE change_sets ALTER COLUMN sequence_no SET DEFAULT nextval('change_set_seq');""")


def downgrade() -> None:
    op.execute("""DROP TABLE IF EXISTS "relation_dimensions" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "annotations" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "relations" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "anchors" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "paragraphs" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "issue_discourses" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "anchor_adjustment_relations" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "paragraph_lineage" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "issue_categories" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "discourses" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "change_items" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "change_effect_states" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "bibliographic_contributors" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "anchor_adjustments" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "sessions" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "relation_kinds" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "persons" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "issues" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "idempotency_records" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "field_definitions" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "dimension_kinds" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "change_sets" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "categories" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "bibliographic_records" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "api_tokens" CASCADE;""")
    op.execute("""DROP TABLE IF EXISTS "actors" CASCADE;""")
    op.execute("""DROP SEQUENCE IF EXISTS change_set_seq;""")
