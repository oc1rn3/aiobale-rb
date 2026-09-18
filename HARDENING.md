# Hardening fork

This repository is based exactly on
[`aminmadaniofficial/aiobale`](https://github.com/aminmadaniofficial/aiobale)
v0.3.8 commit `94b43b035cba6fe9e7555d210fc391ad32366d7f`.

The fork intentionally changes only two response-handling boundaries:

- strict validation of the unary, uncompressed gRPC-Web data frame and its
  optional single trailer frame before protobuf decoding;
- bounded, chunked reading of HTTP responses, with an 8 MiB default limit.

Malformed, truncated, compressed, or structurally inconsistent unary
gRPC-Web frames fail closed before protobuf decoding.

The existing MIT license and upstream copyright notices are retained unchanged.
No public client, authentication, session, proxy, method, enum, type, message,
listener, or WebSocket contract is intentionally changed.

The release artifacts and their SHA-256 checksums are published with the
corresponding GitHub release.
