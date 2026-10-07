import uuid
import unittest
from datetime import datetime, timezone

from fastapi import HTTPException

from app.models import Conversation, ConversationMember, Message, User
from app.routes.conversations import (
    add_group_member,
    create_direct,
    create_group,
    get_conversation,
    list_conversations,
    remove_group_member,
    transfer_group_owner,
)
from app.routes.messages import delete_message, mark_read, send_message
from app.schemas import (
    AddConversationMember,
    CreateDirectConversation,
    CreateGroupConversation,
    CreateMessage,
    TransferConversationOwnership,
)


class Result:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values

    def unique(self):
        return self


class CommunicationSession:
    def __init__(self, scalar_values=None, rows=None):
        self.scalar_values = list(scalar_values or [])
        self.rows = list(rows or [])
        self.added = []
        self.deleted = []
        self.committed = False
        self.statements = []

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def scalars(self, statement):
        self.statements.append(statement)
        return Result(self.rows.pop(0) if self.rows else [])

    def add(self, value):
        self.added.append(value)

    def add_all(self, values):
        self.added.extend(values)

    async def flush(self):
        for value in self.added:
            if hasattr(value, "id") and value.id is None:
                value.id = uuid.uuid4()
            now = datetime.now(timezone.utc)
            if hasattr(value, "created_at") and value.created_at is None:
                value.created_at = now
            if hasattr(value, "updated_at") and value.updated_at is None:
                value.updated_at = now

    async def commit(self):
        self.committed = True

    async def refresh(self, _value):
        return None

    async def delete(self, value):
        self.deleted.append(value)


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

    async def test_group_creation_rejects_inactive_members(self):
        inactive_member = User(
            id=uuid.uuid4(),
            username="inactive",
            email="inactive@example.com",
            password_hash="hash",
            is_active=False,
        )
        with self.assertRaises(HTTPException) as error:
            await create_group(
                CreateGroupConversation(name="Team", member_ids=[str(inactive_member.id)]),
                self.user,
                CommunicationSession(rows=[[self.user]]),
            )
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.detail, "One or more users not found")

    async def test_group_creation_caps_members_including_creator(self):
        requested_members = [str(uuid.uuid4()) for _ in range(100)]
        with self.assertRaises(HTTPException) as error:
            await create_group(
                CreateGroupConversation(name="Large", member_ids=requested_members),
                self.user,
                CommunicationSession(),
            )
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(error.exception.detail, "Groups may have at most 100 members")

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

    async def test_send_message_checks_membership_and_commits_recipient_notifications(self):
        conversation = Conversation(
            id=uuid.uuid4(), type="GROUP", name="Group",
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        membership = ConversationMember(conversation_id=conversation.id, user_id=self.user.id)
        session = CommunicationSession([membership, conversation], rows=[[self.target.id]])
        response = await send_message(
            conversation.id,
            CreateMessage(content="Hello group"),
            self.user,
            session,
        )
        self.assertEqual(response["content"], "Hello group")
        notifications = [value for value in session.added if getattr(value, "type", None) == "MESSAGE"]
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].recipient_id, self.target.id)
        self.assertTrue(session.committed)
        self.assertIn("FOR UPDATE", str(session.statements[1].compile(dialect=__import__("sqlalchemy.dialects.postgresql").dialects.postgresql.dialect())))

    async def test_read_state_updates_only_current_membership(self):
        membership = ConversationMember(conversation_id=self.conversation.id, user_id=self.user.id)
        session = CommunicationSession([membership], rows=[[]])
        response = await mark_read(self.conversation.id, self.user, session)
        self.assertEqual(response["conversation_id"], str(self.conversation.id))
        self.assertIsNotNone(membership.last_read_at)

    async def test_group_owner_can_add_remove_members_and_transfer_ownership(self):
        group = Conversation(
            id=uuid.uuid4(), type="GROUP", name="Team", created_by_id=self.user.id,
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        owner_membership = ConversationMember(conversation_id=group.id, user_id=self.user.id)
        target_membership = ConversationMember(conversation_id=group.id, user_id=self.target.id)
        add_session = CommunicationSession([owner_membership, group, self.target, None])
        added = await add_group_member(
            group.id,
            AddConversationMember(user_id=str(self.target.id)),
            self.user,
            add_session,
        )
        self.assertEqual(added["user"]["id"], str(self.target.id))
        self.assertEqual(len(add_session.added), 1)
        self.assertTrue(add_session.committed)

        transfer_session = CommunicationSession(
            [owner_membership, group, target_membership, group, target_membership, None, 0]
        )
        response = await transfer_group_owner(
            group.id,
            TransferConversationOwnership(user_id=str(self.target.id)),
            self.user,
            transfer_session,
        )
        self.assertEqual(group.created_by_id, self.target.id)
        self.assertEqual(response["unread_count"], 0)

        remove_session = CommunicationSession([target_membership, group, owner_membership])
        await remove_group_member(group.id, self.user.id, self.target, remove_session)
        self.assertEqual(remove_session.deleted, [owner_membership])
        self.assertTrue(remove_session.committed)

    async def test_non_owner_cannot_manage_group_and_owner_cannot_leave_without_transfer(self):
        group = Conversation(
            id=uuid.uuid4(), type="GROUP", name="Team", created_by_id=self.user.id,
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        non_owner_membership = ConversationMember(conversation_id=group.id, user_id=self.target.id)
        with self.assertRaises(HTTPException) as add_error:
            await add_group_member(
                group.id,
                AddConversationMember(user_id=str(uuid.uuid4())),
                self.target,
                CommunicationSession([non_owner_membership, group]),
            )
        self.assertEqual(add_error.exception.status_code, 403)

        owner_membership = ConversationMember(conversation_id=group.id, user_id=self.user.id)
        with self.assertRaises(HTTPException) as leave_error:
            await remove_group_member(
                group.id,
                self.user.id,
                self.user,
                CommunicationSession([owner_membership, group]),
            )
        self.assertEqual(leave_error.exception.status_code, 409)

    async def test_conversation_list_populates_latest_message_and_unread_count(self):
        latest = Message(
            id=uuid.uuid4(), conversation_id=self.conversation.id, sender_id=self.target.id,
            sender=self.target, content="latest private message",
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        membership = ConversationMember(conversation_id=self.conversation.id, user_id=self.user.id)
        session = CommunicationSession([membership, latest, 3], rows=[[self.conversation]])
        result = await list_conversations(self.user, session, offset=0, limit=10)
        self.assertEqual(result[0]["last_message_preview"], "latest private message")
        self.assertEqual(result[0]["last_message_at"], latest.created_at)
        self.assertEqual(result[0]["unread_count"], 3)


if __name__ == "__main__":
    unittest.main()
