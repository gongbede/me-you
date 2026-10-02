import uuid
import unittest
from datetime import datetime, timezone

from fastapi import HTTPException

from app.models import Activity, Comment, Follow, Notification, Post, PostLike, User
from app.routes.comments import create_comment, update_comment
from app.routes.follows import follow_user
from app.routes.likes import like_post
from app.routes.notifications import get_recipient_notification, mark_all_notifications_read
from app.routes.posts import create_post, get_feed, update_post
from app.schemas import CreateComment, CreatePost, UpdateComment


class ScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class ExecuteResult:
    rowcount = 2


class SocialSession:
    def __init__(self, scalar_values=None, scalar_rows=None):
        self.scalar_values = list(scalar_values or [])
        self.scalar_rows = list(scalar_rows or [])
        self.added = []
        self.deleted = []
        self.committed = False

    async def scalar(self, _statement):
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def scalars(self, _statement):
        return ScalarResult(self.scalar_rows.pop(0) if self.scalar_rows else [])

    async def flush(self):
        for value in self.added:
            if hasattr(value, "id") and getattr(value, "id", None) is None:
                value.id = uuid.uuid4()

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True
        now = datetime.now(timezone.utc)
        for value in self.added:
            if hasattr(value, "id") and getattr(value, "id", None) is None:
                value.id = uuid.uuid4()
            if hasattr(value, "created_at") and getattr(value, "created_at", None) is None:
                value.created_at = now
            if hasattr(value, "updated_at") and getattr(value, "updated_at", None) is None:
                value.updated_at = now

    async def refresh(self, _value):
        return None

    async def delete(self, value):
        self.deleted.append(value)

    async def execute(self, _statement):
        return ExecuteResult()


class SocialCoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.author = User(id=uuid.uuid4(), username="author", email="author@example.com", password_hash="hash")
        self.other = User(id=uuid.uuid4(), username="other", email="other@example.com", password_hash="hash")
        self.post = Post(
            id=uuid.uuid4(),
            author_id=self.author.id,
            author=self.author,
            content="hello",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    async def test_post_create_and_unauthorized_update(self):
        session = SocialSession()
        created = await create_post(CreatePost(content="  new post  "), self.author, session)
        self.assertEqual(created["content"], "new post")
        self.assertIsInstance(session.added[0], Post)
        activities = [value for value in session.added if isinstance(value, Activity)]
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0].event_type, "social.post.created")
        self.assertEqual(activities[0].actor_id, self.author.id)
        self.assertEqual(activities[0].target_type, "post")
        self.assertEqual(activities[0].target_id, uuid.UUID(created["id"]))
        self.assertIsNone(activities[0].payload)
        self.assertNotIn("hello", str(activities[0].payload))

        with self.assertRaises(HTTPException) as error:
            await update_post(
                self.post.id,
                CreatePost(content="changed"),
                self.other,
                SocialSession([self.post]),
            )
        self.assertEqual(error.exception.status_code, 403)

    async def test_comment_create_and_unauthorized_update(self):
        session = SocialSession([self.post])
        created = await create_comment(
            self.post.id,
            CreateComment(content="useful comment"),
            self.other,
            session,
        )
        self.assertEqual(created["content"], "useful comment")
        self.assertTrue(any(isinstance(value, Notification) for value in session.added))

        comment = Comment(
            id=uuid.uuid4(),
            post_id=self.post.id,
            author_id=self.author.id,
            author=self.author,
            content="original",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        with self.assertRaises(HTTPException) as error:
            await update_comment(comment.id, UpdateComment(content="changed"), self.other, SocialSession([comment]))
        self.assertEqual(error.exception.status_code, 403)

    async def test_like_duplicate_and_follow_self_are_rejected(self):
        duplicate_like = PostLike(post_id=self.post.id, user_id=self.other.id)
        with self.assertRaises(HTTPException) as like_error:
            await like_post(self.post.id, self.other, SocialSession([self.post, duplicate_like]))
        self.assertEqual(like_error.exception.status_code, 409)

        with self.assertRaises(HTTPException) as follow_error:
            await follow_user(self.author.id, self.author, SocialSession([self.author]))
        self.assertEqual(follow_error.exception.status_code, 400)

    async def test_feed_returns_database_order_and_pagination_shape(self):
        newer = Post(
            id=uuid.uuid4(),
            author_id=self.author.id,
            author=self.author,
            content="newer",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        older = Post(
            id=uuid.uuid4(),
            author_id=self.other.id,
            author=self.other,
            content="older",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        response = await get_feed(self.author, SocialSession(scalar_rows=[[newer, older]]), offset=0, limit=1)
        self.assertEqual(response["items"][0]["content"], "newer")
        self.assertTrue(response["has_more"])

    async def test_notification_recipient_isolation_and_read_all(self):
        with self.assertRaises(HTTPException) as error:
            await get_recipient_notification(uuid.uuid4(), self.author, SocialSession([None]))
        self.assertEqual(error.exception.status_code, 404)

        response = await mark_all_notifications_read(self.author, SocialSession())
        self.assertEqual(response, {"updated": 2})


if __name__ == "__main__":
    unittest.main()
