import pytest
from pydantic import ValidationError

from app.providers.storage import sniff_content_type
from app.routes.video_music import MUSIC_CATEGORIES, VIDEO_CATEGORIES, TrackCreate, VideoCreate


def test_video_categories_and_field_limits():
    valid = VideoCreate(
        media_asset_id="df85b4fc-697f-4591-a68e-1f4c584b6cb7",
        title="A video",
        category="Education",
    )
    assert valid.category in VIDEO_CATEGORIES
    with pytest.raises(ValidationError):
        VideoCreate(
            media_asset_id="df85b4fc-697f-4591-a68e-1f4c584b6cb7",
            title=" ",
            category="not-a-category",
        )


def test_track_requires_rights_checkbox_and_known_category():
    with pytest.raises(ValidationError):
        TrackCreate(
            media_asset_id="df85b4fc-697f-4591-a68e-1f4c584b6cb7",
            title="Track",
            artist_name="Artist",
            category="Afrobeats",
        )
    track = TrackCreate(
        media_asset_id="df85b4fc-697f-4591-a68e-1f4c584b6cb7",
        title="Track",
        artist_name="Artist",
        category="Afrobeats",
        rights_confirmed=True,
    )
    assert track.category in MUSIC_CATEGORIES


@pytest.mark.parametrize(
    ("signature", "content_type"),
    [
        (b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00", "audio/mp4"),
        (b"RIFF\x00\x00\x00\x00WAVEfmt ", "audio/wav"),
        (b"\xff\xf1\x50\x80", "audio/aac"),
        (b"OggS\x00", "audio/ogg"),
        (b"ID3\x04\x00\x00", "audio/mpeg"),
    ],
)
def test_audio_upload_signature_detection(signature, content_type):
    assert sniff_content_type(signature) == content_type
