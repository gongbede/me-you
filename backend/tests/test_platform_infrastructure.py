import unittest
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from app.activity import list_actor_activities, record_activity
from app.models import Activity, Notification, User
from app.routes.notifications import (
    count_unread_notifications,
    get_recipient_notification,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)
from app.routes.search import global_search


class Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values

    def mappings(self):
        return self


class Result:
    def __init__(self, rowcount=0, rows=None):
        self.rowcount = rowcount
        self.rows = list(rows or [])

    def mappings(self):
        return Rows(self.rows)


class PlatformSession:
    def __init__(self, *, scalar_values=None, scalar_rows=None, result_rows=None, scalar_result=None):
        self.scalar_values = list(scalar_values or [])
        self.scalar_rows = list(scalar_rows or [])
        self.result_rows = list(result_rows or [])
        self.scalar_result = scalar_result
        self.statements = []
        self.added = []
        self.committed = False

    async def scalar(self, statement):
        self.statements.append(statement)
        if self.scalar_values:
            return self.scalar_values.pop(0)
        return self.scalar_result

    async def scalars(self, statement):
        self.statements.append(statement)
        return Rows(self.scalar_rows.pop(0) if self.scalar_rows else [])

    async def execute(self, statement):
        self.statements.append(statement)
        return Result(rowcount=2, rows=self.result_rows)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True

    async def refresh(self, _value):
        return None


def make_notification(recipient_id, *, read_at=None):
    return Notification(
        id=uuid.uuid4(),
        recipient_id=recipient_id,
        type="COURSE_UPDATE",
        title="Course updated",
        payload={"course_id": str(uuid.uuid4())},
        target_type="course",
        target_id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
        read_at=read_at,
    )


class PlatformInfrastructureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = User(id=uuid.uuid4(), username="alice", email="alice@example.com", password_hash="hash")
        self.other = User(id=uuid.uuid4(), username="bob", email="bob@example.com", password_hash="hash")

    async def test_notifications_are_owner_scoped_and_unread_list_is_paged(self):
        notification = make_notification(self.user.id)
        session = PlatformSession(scalar_rows=[[notification]])
        response = await list_notifications(
            self.user,
            session,
            offset=2,
            limit=1,
            unread_only=True,
        )
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0]["title"], "Course updated")
        self.assertIsNone(response[0]["read_at"])
        statement = session.statements[0]
        compiled = statement.compile()
        sql = str(compiled)
        self.assertIn("notifications.recipient_id", sql)
        self.assertIn("notifications.read_at IS NULL", sql)
        self.assertIn(2, compiled.params.values())
        self.assertIn(1, compiled.params.values())
        self.assertIn(self.user.id, compiled.params.values())

    async def test_notification_owner_cannot_read_or_mark_another_users_notification(self):
        session = PlatformSession(scalar_values=[None, None])
        with self.assertRaises(HTTPException) as read_error:
            await get_recipient_notification(uuid.uuid4(), self.user, session)
        self.assertEqual(read_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as mark_error:
            await mark_notification_read(uuid.uuid4(), self.user, session)
        self.assertEqual(mark_error.exception.status_code, 404)
        self.assertEqual(len(session.statements), 2)
        for statement in session.statements:
            self.assertIn("notifications.recipient_id", str(statement.compile()))
            self.assertIn(self.user.id, statement.compile().params.values())
        self.assertFalse(session.committed)

    async def test_notification_mark_read_and_unread_count_are_scoped(self):
        notification = make_notification(self.user.id)
        mark_session = PlatformSession(scalar_values=[notification])
        response = await mark_notification_read(notification.id, self.user, mark_session)
        self.assertIsNotNone(response["read_at"])
        self.assertTrue(mark_session.committed)

        count_session = PlatformSession(scalar_result=4)
        count = await count_unread_notifications(self.user, count_session)
        self.assertEqual(count, {"unread_count": 4})
        compiled = count_session.statements[0].compile()
        self.assertIn("notifications.recipient_id", str(compiled))
        self.assertIn("notifications.read_at IS NULL", str(compiled))
        self.assertIn(self.user.id, compiled.params.values())

    async def test_mark_all_notifications_read_is_recipient_scoped(self):
        session = PlatformSession()
        response = await mark_all_notifications_read(self.user, session)
        self.assertEqual(response, {"updated": 2})
        compiled = session.statements[0].compile()
        self.assertIn("notifications.recipient_id", str(compiled))
        self.assertIn(self.user.id, compiled.params.values())
        self.assertTrue(session.committed)

    async def test_activity_creation_scopes_actor_and_validates_metadata(self):
        session = PlatformSession()
        target_id = uuid.uuid4()
        activity = await record_activity(
            session,
            actor_id=self.user.id,
            event_type="institution.joined",
            target_type="institution",
            target_id=target_id,
            metadata={"role": "STUDENT", "member_count": 12},
        )
        self.assertIsInstance(activity, Activity)
        self.assertEqual(activity.actor_id, self.user.id)
        self.assertEqual(activity.target_id, target_id)
        self.assertEqual(activity.payload, {"role": "STUDENT", "member_count": 12})
        self.assertIsNotNone(activity.created_at)
        self.assertIn(activity, session.added)

        with self.assertRaises(ValueError):
            await record_activity(session, event_type="message.sent", metadata={"message": "private text"})
        with self.assertRaises(ValueError):
            await record_activity(session, event_type="assessment.graded", metadata={"grade": "A"})

    async def test_activity_reads_are_actor_scoped_and_paginated(self):
        activity = Activity(
            id=uuid.uuid4(),
            actor_id=self.user.id,
            event_type="course.created",
            created_at=datetime.now(timezone.utc),
        )
        session = PlatformSession(scalar_rows=[[activity], []])
        values = await list_actor_activities(self.user.id, session, offset=3, limit=5)
        self.assertEqual(values, [activity])
        compiled = session.statements[0].compile()
        self.assertIn("activities.actor_id", str(compiled))
        self.assertIn("ORDER BY activities.created_at DESC, activities.id DESC", str(compiled))
        self.assertIn(self.user.id, compiled.params.values())
        self.assertIn(3, compiled.params.values())
        self.assertIn(5, compiled.params.values())

        other_values = await list_actor_activities(self.other.id, session, limit=5)
        self.assertEqual(other_values, [])
        other_compiled = session.statements[1].compile()
        self.assertIn("activities.actor_id", str(other_compiled))
        self.assertIn(self.other.id, other_compiled.params.values())

        with self.assertRaises(ValueError):
            await list_actor_activities(self.other.id, session, offset=-1)

    async def test_search_is_normalized_authorized_and_paginated(self):
        first_id = uuid.uuid4()
        second_id = uuid.uuid4()
        session = PlatformSession(
            result_rows=[
                {"resource_type": "course", "id": first_id, "name": "Science", "code": "SCI101", "institution_id": uuid.uuid4()},
                {"resource_type": "institution", "id": second_id, "name": "Science Academy", "code": None, "institution_id": None},
            ]
        )
        response = await global_search("  SCI   ", self.user, session, offset=0, limit=1)
        self.assertEqual(response["query"], "sci")
        self.assertEqual(len(response["items"]), 1)
        self.assertEqual(response["items"][0]["id"], str(first_id))
        self.assertTrue(response["has_more"])
        self.assertNotIn("description", response["items"][0])

        statement = session.statements[0]
        compiled = statement.compile()
        sql = str(compiled)
        self.assertIn("institution_memberships.user_id", sql)
        self.assertGreaterEqual(sql.count("institution_memberships"), 2)
        self.assertIn("ORDER BY lower", sql)
        self.assertIn(self.user.id, compiled.params.values())
        self.assertIn("%sci%", compiled.params.values())

    async def test_search_rejects_short_and_empty_normalized_queries(self):
        session = PlatformSession()
        for query in ("", "  ", "x"):
            with self.subTest(query=query):
                with self.assertRaises(HTTPException) as error:
                    await global_search(query, self.user, session)
                self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(session.statements, [])


if __name__ == "__main__":
    unittest.main()
