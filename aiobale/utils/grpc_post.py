from ..exceptions import AiobaleError


GRPC_WEB_HEADER_SIZE = 5
GRPC_WEB_DATA_FLAG = 0x00
GRPC_WEB_TRAILER_FLAG = 0x80


def _read_frame_header(data: bytes, offset: int, frame_name: str):
    if len(data) - offset < GRPC_WEB_HEADER_SIZE:
        raise AiobaleError(f"Incomplete gRPC-Web {frame_name} frame header")

    flag = data[offset]
    length = int.from_bytes(data[offset + 1 : offset + 5], byteorder="big")
    return flag, length


def clean_grpc(data: bytes):
    """Return the payload from one unary, uncompressed gRPC-Web response."""
    data_flag, payload_length = _read_frame_header(data, 0, "data")
    if data_flag != GRPC_WEB_DATA_FLAG:
        raise AiobaleError("Unsupported gRPC-Web data frame flag")

    payload_start = GRPC_WEB_HEADER_SIZE
    payload_end = payload_start + payload_length
    if payload_end > len(data):
        raise AiobaleError("Incomplete gRPC-Web data frame payload")

    payload = data[payload_start:payload_end]
    if payload_end == len(data):
        return payload

    trailer_flag, trailer_length = _read_frame_header(data, payload_end, "trailer")
    if trailer_flag != GRPC_WEB_TRAILER_FLAG:
        raise AiobaleError("Unsupported gRPC-Web trailer frame flag")

    trailer_end = payload_end + GRPC_WEB_HEADER_SIZE + trailer_length
    if trailer_end > len(data):
        raise AiobaleError("Incomplete gRPC-Web trailer frame payload")
    if trailer_end < len(data):
        raise AiobaleError("Unexpected bytes after gRPC-Web trailer frame")

    return payload


def add_header(payload: bytes):
    compressed_flag = 0x00
    length = len(payload)
    header = bytes([compressed_flag]) + length.to_bytes(4, byteorder='big')
    
    return header + payload
