import uuid
import unittest
from datetime import datetime, timezone

from fastapi import HTTPException

from app.models import Conversation, ConversationMember, Message, User
from app.routes.conversations import create_direct, create_group, get_conversation
from app.routes.messages import delete_message, mark_read
from app.schemas import CreateDirectConversation, CreateGroupConversation


class Result:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class CommunicationSession:
    def __init__(self, scalar_values=None, rows=None):
        self.scalar_values = list(scalar_values or [])
        self.rows = list(rows or [])
        self.added = []
        self.committed = False

    async def scalar(self, _statement):
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def scalars(self, _statement):
        return Result(self.rows.pop(0) if self.rows else [])

    def add(self, value):
        self.added.append(value)

    def add_all(self, values):
        self.added.extend(values)

    async def flush(self):
        for value in self.added:
            if hasattr(value, "id") and value.id is None:
                value.id = uuid.uuid4()

    async def commit(self):
        self.committed = True

    async def refresh(self, _value):
        return None

    async def delete(self, _value):
        return None


class CommunicationCoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = User(id=uuid.uuid4(), username="one", email="one@example.com", password_hash="hash")
        self.target = User(id=uuid.uuid4(), username="two", email="two@example.com", password_hash="hash")
        self.conversation = Conversation(
            id=uuid.uuid4(), type="DIRECT", direct_key="a:b",
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        self.conversation.members = [
            ConversationMember(conversation_id=self.conversation.id, user_id=self.user.id, user=self.user),
            ConversationMember(conversation_id=self.conversation.id, user_id=self.target.id, user=self.target),
        ]

    async def test_direct_conversation_reuses_existing_and_rejects_self(self):
        session = CommunicationSession([self.target, self.conversation, self.conversation])
        response = await create_direct(CreateDirectConversation(target_user_id=str(self.target.id)), self.user, session)
        self.assertEqual(response["id"], str(self.conversation.id))

        with self.assertRaises(HTTPException) as error:
            await create_direct(CreateDirectConversation(target_user_id=str(self.user.id)), self.user, CommunicationSession())
        self.assertEqual(error.exception.status_code, 400)

    async def test_group_creator_is_added_and_unknown_member_is_rejected(self):
        group = Conversation(type="GROUP", name="Team", created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
        group.members = [ConversationMember(conversation_id=group.id, user_id=self.user.id, user=self.user)]
        session = CommunicationSession([group], rows=[[self.user]])
        response = await create_group(CreateGroupConversation(name="Team"), self.user, session)
        self.assertEqual(response["name"], "Team")
        self.assertEqual(len(session.added), 2)

        with self.assertRaises(HTTPException) as error:
            await create_group(CreateGroupConversation(name="Team", member_ids=[str(uuid.uuid4())]), self.user, CommunicationSession(rows=[[self.user]]))
        self.assertEqual(error.exception.status_code, 404)

    async def test_non_member_cannot_view_conversation(self):
        with self.assertRaises(HTTPException) as error:
            await get_conversation(self.conversation.id, self.target, CommunicationSession([None, self.conversation.id]))
        self.assertEqual(error.exception.status_code, 403)

    async def test_message_delete_is_soft_delete(self):
        message = Message(
            id=uuid.uuid4(), conversation_id=self.conversation.id, sender_id=self.user.id,
            sender=self.user, content="secret", created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session = CommunicationSession([message, ConversationMember(conversation_id=self.conversation.id, user_id=self.user.id)])
        await delete_message(message.id, self.user, session)
        self.assertIsNotNone(message.deleted_at)
        self.assertFalse(session.committed is False)

    async def test_read_state_updates_only_current_membership(self):
        membership = ConversationMember(conversation_id=self.conversation.id, user_id=self.user.id)
        session = CommunicationSession([membership], rows=[[]])
        response = await mark_read(self.conversation.id, self.user, session)
        self.assertEqual(response["conversation_id"], str(self.conversation.id))
        self.assertIsNotNone(membership.last_read_at)


if __name__ == "__main__":
    unittest.main()
