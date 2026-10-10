import importlib.util
import unittest
from pathlib import Path

from app.database import Base
from app.models import (
    Activity,
    AuthIdentity,
    Comment,
    Assessment,
    AssessmentResult,
    AssessmentSubmission,
    Conversation,
    ConversationMember,
    CourseTeacher,
    Course,
    Department,
    Enrollment,
    Exercise,
    ExerciseSubmission,
    Faculty,
    Follow,
    Message,
    Notification,
    Post,
    PostLike,
    PhoneLoginCode,
    Profile,
    Institution,
    InstitutionMembership,
    Lesson,
    LessonProgress,
    LoginThrottle,
    MediaAsset,
    Student,
    Teacher,
    User,
)


ROOT = Path(__file__).parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MigrationFoundationTests(unittest.TestCase):
    def test_alembic_environment_imports_without_database_connection(self):
        environment = load_module("me_you_alembic_env", ROOT / "alembic" / "env.py")
        self.assertIs(environment.target_metadata, Base.metadata)

    def test_metadata_contains_only_current_postgres_models(self):
        self.assertEqual(
            set(Base.metadata.tables),
            {
                "users", "profiles", "posts", "comments", "post_likes", "follows",
                "notifications", "conversations", "conversation_members", "messages",
                "institutions", "institution_memberships", "faculties", "departments",
                "courses", "teachers", "students", "enrollments",
                "course_teachers", "lessons", "exercises", "exercise_submissions", "assessments",
                "assessment_submissions", "assessment_results", "lesson_progress", "activities", "login_throttles", "media_assets",
                "rate_limit_counters",
                "security_events",
                "institution_membership_requests",
                "account_email_tokens",
                "auth_identities",
                "phone_login_codes",
            },
        )
        self.assertIs(User.__table__, Base.metadata.tables["users"])
        self.assertIs(Profile.__table__, Base.metadata.tables["profiles"])
        self.assertIs(Post.__table__, Base.metadata.tables["posts"])
        self.assertIs(Comment.__table__, Base.metadata.tables["comments"])
        self.assertIs(PostLike.__table__, Base.metadata.tables["post_likes"])
        self.assertIs(Follow.__table__, Base.metadata.tables["follows"])
        self.assertIs(Notification.__table__, Base.metadata.tables["notifications"])
        self.assertIs(Conversation.__table__, Base.metadata.tables["conversations"])
        self.assertIn(
            "ix_conversations_created_by_id",
            {index.name for index in Conversation.__table__.indexes},
        )
        self.assertIs(ConversationMember.__table__, Base.metadata.tables["conversation_members"])
        self.assertIs(Message.__table__, Base.metadata.tables["messages"])
        self.assertIs(Institution.__table__, Base.metadata.tables["institutions"])
        self.assertIs(InstitutionMembership.__table__, Base.metadata.tables["institution_memberships"])
        self.assertIs(Faculty.__table__, Base.metadata.tables["faculties"])
        self.assertIs(Department.__table__, Base.metadata.tables["departments"])
        self.assertIs(Course.__table__, Base.metadata.tables["courses"])
        self.assertIs(Teacher.__table__, Base.metadata.tables["teachers"])
        self.assertIs(Student.__table__, Base.metadata.tables["students"])
        self.assertIs(Enrollment.__table__, Base.metadata.tables["enrollments"])
        self.assertIs(CourseTeacher.__table__, Base.metadata.tables["course_teachers"])
        self.assertIs(Lesson.__table__, Base.metadata.tables["lessons"])
        self.assertIs(Exercise.__table__, Base.metadata.tables["exercises"])
        self.assertIs(ExerciseSubmission.__table__, Base.metadata.tables["exercise_submissions"])
        self.assertIs(Assessment.__table__, Base.metadata.tables["assessments"])
        self.assertIs(AssessmentSubmission.__table__, Base.metadata.tables["assessment_submissions"])
        self.assertIs(AssessmentResult.__table__, Base.metadata.tables["assessment_results"])
        self.assertIs(LessonProgress.__table__, Base.metadata.tables["lesson_progress"])
        self.assertIs(LoginThrottle.__table__, Base.metadata.tables["login_throttles"])
        self.assertIs(MediaAsset.__table__, Base.metadata.tables["media_assets"])
        self.assertIs(Activity.__table__, Base.metadata.tables["activities"])
        self.assertIs(AuthIdentity.__table__, Base.metadata.tables["auth_identities"])
        self.assertIs(PhoneLoginCode.__table__, Base.metadata.tables["phone_login_codes"])
        self.assertIn(
            "uq_auth_identities_provider_subject",
            {constraint.name for constraint in AuthIdentity.__table__.constraints},
        )

    def test_initial_migration_has_upgrade_and_downgrade(self):
        migration = load_module(
            "me_you_initial_migration",
            ROOT / "alembic" / "versions" / "0001_initial_schema.py",
        )
        self.assertIsNone(migration.down_revision)
        self.assertTrue(callable(migration.upgrade))
        self.assertTrue(callable(migration.downgrade))

    def test_social_core_migration_follows_identity_migration(self):
        migration = load_module(
            "me_you_social_core_migration",
            ROOT / "alembic" / "versions" / "0002_social_core.py",
        )
        self.assertEqual(migration.down_revision, "0001_initial_schema")
        self.assertTrue(callable(migration.upgrade))
        self.assertTrue(callable(migration.downgrade))

    def test_communication_core_migration_follows_social_core(self):
        migration = load_module(
            "me_you_communication_core_migration",
            ROOT / "alembic" / "versions" / "0003_communication_core.py",
        )
        self.assertEqual(migration.down_revision, "0002_social_core")
        self.assertTrue(callable(migration.upgrade))
        self.assertTrue(callable(migration.downgrade))

    def test_education_migration_follows_communication_core(self):
        migration = load_module(
            "me_you_education_core_migration",
            ROOT / "alembic" / "versions" / "0004_education_core.py",
        )
        self.assertEqual(migration.down_revision, "0003_communication_core")
        self.assertTrue(callable(migration.upgrade))
        self.assertTrue(callable(migration.downgrade))

    def test_education_learning_migration_follows_education_core(self):
        migration = load_module(
            "me_you_education_learning_migration",
            ROOT / "alembic" / "versions" / "0005_education_learning_core.py",
        )
        self.assertEqual(migration.down_revision, "0004_education_core")
        self.assertTrue(callable(migration.upgrade))
        self.assertTrue(callable(migration.downgrade))

    def test_platform_infrastructure_migration_follows_institution_memberships(self):
        migration = load_module(
            "me_you_platform_infrastructure_migration",
            ROOT / "alembic" / "versions" / "0007_platform_infrastructure.py",
        )
        self.assertEqual(migration.down_revision, "0006_institution_memberships")
        self.assertTrue(callable(migration.upgrade))
        self.assertTrue(callable(migration.downgrade))

    def test_exercise_submissions_migration_follows_platform_infrastructure(self):
        migration = load_module(
            "me_you_exercise_submissions_migration",
            ROOT / "alembic" / "versions" / "0008_exercise_submissions.py",
        )
        self.assertEqual(migration.down_revision, "0007_platform_infrastructure")
        self.assertTrue(callable(migration.upgrade))
        self.assertTrue(callable(migration.downgrade))

    def test_account_security_migration_follows_exercise_submissions(self):
        migration = load_module(
            "me_you_account_security_migration",
            ROOT / "alembic" / "versions" / "0009_account_security.py",
        )
        self.assertEqual(migration.down_revision, "0008_exercise_submissions")
        self.assertTrue(callable(migration.upgrade))
        self.assertTrue(callable(migration.downgrade))

    def test_conversation_ownership_migration_follows_account_security(self):
        migration = load_module(
            "me_you_conversation_ownership_migration",
            ROOT / "alembic" / "versions" / "0010_conversation_ownership.py",
        )
        self.assertEqual(migration.down_revision, "0009_account_security")
        self.assertTrue(callable(migration.upgrade))
        self.assertTrue(callable(migration.downgrade))

    def test_media_assets_migration_follows_conversation_ownership(self):
        migration = load_module(
            "me_you_media_assets_migration",
            ROOT / "alembic" / "versions" / "0011_media_assets.py",
        )
        self.assertEqual(migration.down_revision, "0010_conversation_ownership")
        self.assertTrue(callable(migration.upgrade))
        self.assertTrue(callable(migration.downgrade))

    def test_foundation_hardening_migrations_form_a_linear_chain(self):
        revisions = (
            ("0012_rate_limit_counters.py", "0012_rate_limit_counters", "0011_media_assets"),
            ("0013_security_events.py", "0013_security_events", "0012_rate_limit_counters"),
            ("0014_privacy_membership_requests.py", "0014_privacy_membership_requests", "0013_security_events"),
            ("0015_education_integrity.py", "0015_education_integrity", "0014_privacy_membership_requests"),
            ("0016_account_email_tokens.py", "0016_account_email_tokens", "0015_education_integrity"),
            ("0017_media_storage.py", "0017_media_storage", "0016_account_email_tokens"),
            ("0018_auth_identities.py", "0018_auth_identities", "0017_media_storage"),
            ("0019_phone_login_codes.py", "0019_phone_login_codes", "0018_auth_identities"),
            ("0020_exercise_publication.py", "0020_exercise_publication", "0019_phone_login_codes"),
        )
        for filename, revision, down_revision in revisions:
            migration = load_module(
                f"me_you_{revision}", ROOT / "alembic" / "versions" / filename
            )
            self.assertEqual(migration.revision, revision)
            self.assertEqual(migration.down_revision, down_revision)
            self.assertTrue(callable(migration.upgrade))
            self.assertTrue(callable(migration.downgrade))

    def test_application_does_not_create_tables_at_startup(self):
        main_source = (ROOT / "app" / "main.py").read_text()
        self.assertNotIn("create_all(", main_source)
        self.assertNotIn("init_db()", main_source)


if __name__ == "__main__":
    unittest.main()
