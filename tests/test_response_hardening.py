import pytest

from aiobale import Client
from aiobale.client.session.aiohttp import (
    AiohttpSession,
    DEFAULT_MAX_RESPONSE_BYTES,
)
from aiobale.exceptions import AiobaleError
from aiobale.types import MessageContent, MessageData, TextMessage
from aiobale.utils.grpc_post import add_header, clean_grpc


def _frame(flag: int, payload: bytes) -> bytes:
    return bytes([flag]) + len(payload).to_bytes(4, byteorder="big") + payload


def test_valid_data_frame():
    assert clean_grpc(add_header(b"payload")) == b"payload"


def test_valid_data_frame_without_trailer():
    assert clean_grpc(_frame(0x00, b"payload")) == b"payload"


def test_valid_data_frame_with_trailer():
    response = _frame(0x00, b"payload") + _frame(0x80, b"grpc-status: 0\r\n")
    assert clean_grpc(response) == b"payload"


@pytest.mark.parametrize("data", [b"", b"\x00", b"\x00\x00\x00\x00"])
def test_rejects_short_data_header(data):
    with pytest.raises(AiobaleError, match="Incomplete gRPC-Web data frame header"):
        clean_grpc(data)


@pytest.mark.parametrize("flag", [0x01, 0x80, 0x81])
def test_rejects_wrong_or_compressed_data_flag(flag):
    with pytest.raises(AiobaleError, match="data frame flag"):
        clean_grpc(_frame(flag, b"payload"))


def test_rejects_inconsistent_declared_payload_length():
    response = bytes([0x00]) + (3).to_bytes(4, byteorder="big") + b"payload"
    with pytest.raises(AiobaleError, match="trailer frame header"):
        clean_grpc(response)


def test_rejects_truncated_payload():
    response = bytes([0x00]) + (8).to_bytes(4, byteorder="big") + b"short"
    with pytest.raises(AiobaleError, match="data frame payload"):
        clean_grpc(response)


def test_rejects_truncated_trailer():
    response = _frame(0x00, b"payload") + bytes([0x80]) + (8).to_bytes(
        4, byteorder="big"
    ) + b"short"
    with pytest.raises(AiobaleError, match="trailer frame payload"):
        clean_grpc(response)


def test_rejects_wrong_trailer_flag():
    response = _frame(0x00, b"payload") + _frame(0x00, b"grpc-status: 0\r\n")
    with pytest.raises(AiobaleError, match="trailer frame flag"):
        clean_grpc(response)


def test_rejects_unexplained_bytes_after_trailer():
    response = _frame(0x00, b"payload") + _frame(0x80, b"") + b"extra"
    with pytest.raises(AiobaleError, match="Unexpected bytes"):
        clean_grpc(response)


class _FakeContent:
    def __init__(self, chunks):
        self._chunks = chunks

    async def iter_chunked(self, _chunk_size):
        for chunk in self._chunks:
            yield chunk


class _FakeResponse:
    def __init__(self, chunks):
        self.content = _FakeContent(chunks)
        self.closed = False

    def close(self):
        self.closed = True


def test_default_response_budget_is_eight_mibibytes():
    assert DEFAULT_MAX_RESPONSE_BYTES == 8 * 1024 * 1024
    assert AiohttpSession().max_response_bytes == DEFAULT_MAX_RESPONSE_BYTES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chunks", "expected"),
    [([b"123", b"456"], b"123456"), ([b"1234", b"5678"], b"12345678")],
)
async def test_response_at_or_under_limit(chunks, expected):
    session = AiohttpSession()
    session.max_response_bytes = 8
    response = _FakeResponse(chunks)
    assert await session._read_response(response) == expected
    assert response.closed is False


@pytest.mark.asyncio
async def test_response_over_limit_is_rejected_and_closed():
    session = AiohttpSession()
    session.max_response_bytes = 8
    response = _FakeResponse([b"1234", b"5678", b"9"])
    with pytest.raises(AiobaleError, match="exceeds configured size limit"):
        await session._read_response(response)
    assert response.closed is True


def test_negative_message_id_is_preserved():
    message = MessageData(
        sender_id=1,
        message_id=-9223372036854775807,
        date=1700000000000,
        content=MessageContent(text=TextMessage(value="test")),
    )
    assert message.message_id == -9223372036854775807
    assert isinstance(message.message_id, int)


@pytest.mark.asyncio
async def test_missing_session_remains_fail_closed(tmp_path, monkeypatch):
    client = Client(session_file=tmp_path / "missing.bale")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(AiobaleError, match="Authentication token is required"):
        await client._ensure_token_exists()


def test_invalid_session_remains_fail_closed(tmp_path, capsys, caplog):
    session_path = tmp_path / "invalid.bale"
    secret = "invalid-session-secret-marker"
    session_path.write_bytes(secret.encode())
    with pytest.raises(AiobaleError) as exc_info:
        Client(session_file=session_path)

    output = capsys.readouterr()
    combined = str(exc_info.value) + output.out + output.err + caplog.text
    assert secret not in combined


def test_frame_error_does_not_disclose_payload_or_credentials():
    secret = b"token=session-secret&proxy=user:password"
    response = bytes([0x00]) + (len(secret) + 1).to_bytes(4, byteorder="big") + secret
    with pytest.raises(AiobaleError) as exc_info:
        clean_grpc(response)
    assert "session-secret" not in str(exc_info.value)
    assert "user:password" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_response_limit_error_does_not_disclose_content(capsys, caplog):
    secret = b"token=session-secret&proxy=user:password"
    session = AiohttpSession()
    session.max_response_bytes = 8
    response = _FakeResponse([secret])
    with pytest.raises(AiobaleError) as exc_info:
        await session._read_response(response)

    output = capsys.readouterr()
    combined = str(exc_info.value) + output.out + output.err + caplog.text
    assert "session-secret" not in combined
    assert "user:password" not in combined
