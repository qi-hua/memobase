import pytest
from unittest.mock import AsyncMock, Mock, patch
from memobase_server import controllers
from memobase_server.models import response as res
from memobase_server.models.blob import BlobType
from memobase_server.models.utils import Promise


GD_FACTS = {
    "facts": [
        {"topic": "basic_info", "sub_topic": "Name", "memo": "Gus", "cites": [0, 1]},
        {
            "topic": "interest",
            "sub_topic": "foods",
            "memo": "Chinese food",
            "cites": [1],
        },
        {
            "topic": "education",
            "sub_topic": "level",
            "memo": "High School",
            "cites": [1],
        },
        {
            "topic": "psychological",
            "sub_topic": "emotional_state",
            "memo": "Feels bored with high school",
            "cites": [1],
        },
    ]
}
PROFILES = [
    "user likes to play basketball",
    "user is a junior school student",
    "user likes japanese food",
    "user is 23 years old",
]

PROFILE_ATTRS = [
    {"topic": "interest", "sub_topic": "sports"},
    {"topic": "education", "sub_topic": "level"},
    {"topic": "interest", "sub_topic": "foods"},
    {"topic": "basic_info", "sub_topic": "age"},
]


MERGE_FACTS = [
    {"action": "MERGE", "memo": "user likes Chinese and Japanese food"},
    {"action": "REPLACE", "memo": "High School"},
]


@pytest.fixture
def mock_llm_complete():
    with patch("memobase_server.controllers.modal.chat.llm_complete") as mock_llm:
        mock_client1 = AsyncMock()
        mock_client1.ok = Mock(return_value=True)
        mock_client1.data = Mock(return_value=GD_FACTS)

        mock_client2 = AsyncMock()
        mock_client2.ok = Mock(return_value=True)
        mock_client2.data = Mock(return_value=MERGE_FACTS[0])

        mock_client3 = AsyncMock()
        mock_client3.ok = Mock(return_value=True)
        mock_client3.data = Mock(return_value=MERGE_FACTS[1])

        mock_llm.side_effect = [mock_client1, mock_client2, mock_client3]
        yield mock_llm


@pytest.mark.asyncio
async def test_chat_buffer_modal(db_env, mock_llm_complete):
    p = await controllers.user.create_user(res.UserData())
    assert p.ok()
    u_id = p.data().id

    p = await controllers.blob.insert_blob(
        u_id,
        res.BlobData(
            blob_type=BlobType.chat,
            blob_data={
                "messages": [
                    {"role": "user", "content": "Hello, this is Gus, how are you?"},
                    {"role": "assistant", "content": "I am fine, thank you!"},
                ]
            },
        ),
    )
    assert p.ok()
    b_id = p.data().id
    p = await controllers.blob.insert_blob(
        u_id,
        res.BlobData(
            blob_type=BlobType.chat,
            blob_data={
                "messages": [
                    {"role": "user", "content": "Hi, nice to meet you, I am Gus"},
                    {
                        "role": "assistant",
                        "content": "Great! I'm MemoBase Assistant, how can I help you?",
                    },
                    {"role": "user", "content": "I really dig into Chinese food"},
                    {"role": "assistant", "content": "Got it, Gus!"},
                    {
                        "role": "user",
                        "content": "write me a homework letter about my final exam, high school is really boring.",
                    },
                ]
            },
            fields={"from": "happy"},
        ),
    )
    assert p.ok()
    b_id2 = p.data().id

    p = await controllers.buffer.get_buffer_capacity(u_id, BlobType.chat)
    assert p.ok() and p.data() == 2

    await controllers.buffer.flush_buffer(u_id, BlobType.chat)

    p = await controllers.user.get_user_profiles(u_id)
    assert p.ok()

    p = await controllers.buffer.get_buffer_capacity(u_id, BlobType.chat)
    assert p.ok() and p.data() == 0

    p = await controllers.user.delete_user(u_id)
    assert p.ok()

    mock_llm_complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_merge_modal(db_env, mock_llm_complete):
    p = await controllers.user.create_user(res.UserData())
    assert p.ok()
    u_id = p.data().id

    p = await controllers.blob.insert_blob(
        u_id,
        res.BlobData(
            blob_type=BlobType.chat,
            blob_data={
                "messages": [
                    {"role": "user", "content": "Hello, this is Gus, how are you?"},
                    {"role": "assistant", "content": "I am fine, thank you!"},
                    {"role": "user", "content": "I'm 25 now, how time flies!"},
                ]
            },
        ),
    )
    assert p.ok()
    b_id = p.data().id
    p = await controllers.blob.insert_blob(
        u_id,
        res.BlobData(
            blob_type=BlobType.chat,
            blob_data={
                "messages": [
                    {"role": "user", "content": "I really dig into Chinese food"},
                    {"role": "assistant", "content": "Got it, Gus!"},
                    {
                        "role": "user",
                        "content": "write me a homework letter about my final exam, high school is really boring.",
                    },
                ]
            },
            fields={"from": "happy"},
        ),
    )
    assert p.ok()
    b_id2 = p.data().id

    p = await controllers.user.add_user_profiles(
        u_id,
        PROFILES,
        PROFILE_ATTRS,
        [[] for _ in range(len(PROFILES))],
    )
    assert p.ok()
    await controllers.buffer.flush_buffer(u_id, BlobType.chat)

    p = await controllers.user.get_user_profiles(u_id)
    assert p.ok() and len(p.data().profiles) == len(PROFILES) + 2
    profiles = p.data().profiles
    assert profiles[-2].attributes == {"topic": "interest", "sub_topic": "foods"}
    assert profiles[-2].content == "user likes Chinese and Japanese food"
    assert profiles[-2].related_blobs == [b_id2]
    assert profiles[-1].attributes == {"topic": "education", "sub_topic": "level"}
    assert profiles[-1].content == "High School"
    assert profiles[-1].related_blobs == [b_id2]

    p = await controllers.user.delete_user(u_id)
    assert p.ok()

    assert mock_llm_complete.await_count == 3
