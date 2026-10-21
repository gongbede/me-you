from app.mentions import mentioned_usernames


def test_mentions_match_unique_username_tokens_case_insensitively():
    assert mentioned_usernames("Hi @Ada_1, not email@site.com or @@double @ada_1.") == {
        "ada_1"
    }