"""P4.3B: DNS-Pinned SSRF-Safe Genlook Result Download Tests.

Uses mocked DNS (socket.getaddrinfo) and mocked httpcore NetworkBackend /
httpx MockTransport only. Zero real network requests are performed.
"""

from __future__ import annotations

import io
import socket
import ssl
from typing import Any, Iterable

import httpcore
import httpx
from PIL import Image
import pytest

from app.domain.ports.tryon_provider import (
    CommercialProviderConfigurationError,
    ProviderPayloadError,
)
from app.infrastructure.external.genlook_tryon import (
    GenlookTryOnConfig,
    GenlookTryOnProvider,
    _PinnedSSRFTransport,
    _is_safe_result_url,
)

TEST_API_KEY = "gk_test_secret_genlook_key_9876543210"


def _make_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(30, 140, 90)).save(buf, format="PNG")
    return buf.getvalue()


VALID_PNG = _make_png_bytes()


def _http_200_png_response(body: bytes = VALID_PNG) -> bytes:
    header = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: image/png\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    return header + body


def _http_redirect_response(location: str, status: int = 302) -> bytes:
    return (
        f"HTTP/1.1 {status} Found\r\n"
        f"Location: {location}\r\n"
        "Content-Length: 0\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")


class _MockTLSStream(httpcore.NetworkStream):
    """In-memory httpcore NetworkStream recording TLS SNI/verify and wire bytes."""

    def __init__(self, backend: "_RecordingNetworkBackend", raw_response: bytes) -> None:
        self._backend = backend
        self._response = raw_response
        self._offset = 0
        self.closed = False

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        if self._offset >= len(self._response):
            return b""
        chunk = self._response[self._offset : self._offset + max_bytes]
        self._offset += len(chunk)
        return chunk

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._backend.sent_bytes.extend(buffer)

    def close(self) -> None:
        self.closed = True

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        self._backend.tls_handshakes.append(
            {
                "ssl_context": ssl_context,
                "server_hostname": server_hostname,
                "timeout": timeout,
                "check_hostname": ssl_context.check_hostname,
                "verify_mode": ssl_context.verify_mode,
            }
        )
        return self

    def get_extra_info(self, info: str) -> Any:
        return None


class _RecordingNetworkBackend(httpcore.NetworkBackend):
    """Mock httpcore NetworkBackend recording TCP targets and TLS handshakes."""

    def __init__(self, raw_response: bytes | None = None) -> None:
        self.raw_response = raw_response if raw_response is not None else _http_200_png_response()
        self.tcp_connects: list[dict[str, Any]] = []
        self.tls_handshakes: list[dict[str, Any]] = []
        self.sent_bytes = bytearray()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        self.tcp_connects.append(
            {
                "host": host,
                "port": port,
                "timeout": timeout,
                "local_address": local_address,
            }
        )
        return _MockTLSStream(self, self.raw_response)


def _addrinfo_entries(ips: list[str], port: int = 443) -> list[tuple[Any, ...]]:
    entries: list[tuple[Any, ...]] = []
    for ip in ips:
        clean = ip.split("%", 1)[0]
        family = socket.AF_INET6 if ":" in clean else socket.AF_INET
        sockaddr = (ip, port, 0, 0) if family == socket.AF_INET6 else (ip, port)
        entries.append((family, socket.SOCK_STREAM, 6, "", sockaddr))
    return entries


def _provider(
    *,
    backend: _RecordingNetworkBackend | None = None,
    http_client: Any = None,
    allow_insecure_urls: bool = False,
    is_production: bool = False,
    base_url: str = "https://api.genlook.app/tryon/v1",
) -> GenlookTryOnProvider:
    cfg = GenlookTryOnConfig(
        api_key=TEST_API_KEY,
        base_url=base_url,
        allow_insecure_urls=allow_insecure_urls,
        is_production=is_production,
    )
    return GenlookTryOnProvider(
        cfg,
        http_client=http_client,
        result_network_backend=backend,
    )


class TestP43BDNSPinnedSSRFResultDownloads:
    def test_1_public_dns_ipv4_and_ipv6_succeed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for public_ip in ("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"):
            backend = _RecordingNetworkBackend()
            monkeypatch.setattr(
                socket,
                "getaddrinfo",
                lambda host, port, _ip=public_ip: _addrinfo_entries([_ip], port or 443),
            )
            data = _provider(backend=backend).download_result_image(
                "https://cdn.genlook-results.example/job1/out.png"
            )
            assert data == VALID_PNG
            assert len(backend.tcp_connects) == 1
            assert backend.tcp_connects[0]["host"] == public_ip
            assert backend.tcp_connects[0]["port"] == 443

    @pytest.mark.parametrize(
        "unsafe_ip",
        [
            "127.0.0.1",
            "127.255.255.254",
            "10.0.0.1",
            "172.16.0.5",
            "192.168.1.10",
            "169.254.169.254",
            "0.0.0.0",
        ],
    )
    def test_2_private_and_loopback_dns_answers_rejected(
        self, monkeypatch: pytest.MonkeyPatch, unsafe_ip: str
    ) -> None:
        backend = _RecordingNetworkBackend()
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: _addrinfo_entries([unsafe_ip], port or 443),
        )
        with pytest.raises(ProviderPayloadError) as exc_info:
            _provider(backend=backend).download_result_image(
                "https://cdn.genlook-results.example/out.png"
            )
        assert getattr(exc_info.value, "provider_error_code", None) == "RESULT_DOWNLOAD_REJECTED"
        assert backend.tcp_connects == []

    @pytest.mark.parametrize(
        "mixed_ips",
        [
            ["93.184.216.34", "10.0.0.1"],
            ["127.0.0.1", "93.184.216.34"],
            ["93.184.216.34", "169.254.169.254"],
            ["2606:2800:220:1:248:1893:25c8:1946", "::1"],
        ],
    )
    def test_3_mixed_public_and_private_dns_answers_reject_entire_set(
        self, monkeypatch: pytest.MonkeyPatch, mixed_ips: list[str]
    ) -> None:
        backend = _RecordingNetworkBackend()
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: _addrinfo_entries(mixed_ips, port or 443),
        )
        with pytest.raises(ProviderPayloadError) as exc_info:
            _provider(backend=backend).download_result_image(
                "https://cdn.genlook-results.example/out.png"
            )
        assert getattr(exc_info.value, "provider_error_code", None) == "RESULT_DOWNLOAD_REJECTED"
        assert backend.tcp_connects == []

    @pytest.mark.parametrize("cgnat_ip", ["100.64.0.1", "100.127.255.254"])
    def test_4_ipv4_cgnat_rejected_in_dns_and_literal(
        self, monkeypatch: pytest.MonkeyPatch, cgnat_ip: str
    ) -> None:
        backend = _RecordingNetworkBackend()
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: _addrinfo_entries([cgnat_ip], port or 443),
        )
        with pytest.raises(ProviderPayloadError):
            _provider(backend=backend).download_result_image(
                "https://cdn.genlook-results.example/out.png"
            )
        with pytest.raises(ProviderPayloadError):
            _provider(backend=backend).download_result_image(f"https://{cgnat_ip}/out.png")
        assert backend.tcp_connects == []

    @pytest.mark.parametrize(
        "ipv6_addr",
        [
            "::1",
            "::",
            "fc00::1",
            "fd12:3456:789a::1",
            "fe80::1",
            "fe80::1%eth0",
            "::ffff:127.0.0.1",
            "::ffff:10.0.0.1",
            "::ffff:100.64.0.1",
            "::ffff:169.254.169.254",
            "::ffff:93.184.216.34",
        ],
    )
    def test_5_ipv6_loopback_private_and_ipv4_mapped_rejected(
        self, monkeypatch: pytest.MonkeyPatch, ipv6_addr: str
    ) -> None:
        backend = _RecordingNetworkBackend()
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: _addrinfo_entries([ipv6_addr], port or 443),
        )
        with pytest.raises(ProviderPayloadError):
            _provider(backend=backend).download_result_image(
                "https://cdn.genlook-results.example/out.png"
            )
        if "%" not in ipv6_addr:
            with pytest.raises(ProviderPayloadError):
                _provider(backend=backend).download_result_image(f"https://[{ipv6_addr}]/out.png")
        assert backend.tcp_connects == []

    def test_6_dns_rebinding_between_precheck_and_tcp_connect_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = _RecordingNetworkBackend()
        calls: list[tuple[str, Any]] = []

        def _rebinding_getaddrinfo(host: str, port: Any) -> list[tuple[Any, ...]]:
            calls.append((host, port))
            if len(calls) == 1:
                # Preliminary validation sees a public IP
                return _addrinfo_entries(["93.184.216.34"], port or 443)
            # At TCP connect boundary, DNS rebinds to AWS metadata / loopback
            return _addrinfo_entries(["169.254.169.254"], port or 443)

        monkeypatch.setattr(socket, "getaddrinfo", _rebinding_getaddrinfo)
        with pytest.raises(ProviderPayloadError) as exc_info:
            _provider(backend=backend).download_result_image(
                "https://rebind-attack.example/out.png"
            )
        assert getattr(exc_info.value, "provider_error_code", None) == "RESULT_DOWNLOAD_REJECTED"
        assert len(calls) == 2
        assert backend.tcp_connects == []

    def test_7_tcp_connect_receives_validated_ip_not_hostname_and_no_second_dns_lookup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = _RecordingNetworkBackend()
        dns_queries: list[tuple[str, Any]] = []

        def _getaddrinfo(host: str, port: Any) -> list[tuple[Any, ...]]:
            dns_queries.append((host, port))
            assert host == "cdn.genlook-results.example"
            return _addrinfo_entries(["93.184.216.34"], port or 443)

        monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo)

        # Verify both via delegate backend AND via real httpcore.SyncBackend.connect_tcp path
        data = _provider(backend=backend).download_result_image(
            "https://cdn.genlook-results.example/out.png"
        )
        assert data == VALID_PNG
        assert backend.tcp_connects == [
            {
                "host": "93.184.216.34",
                "port": 443,
                "timeout": 10.0,
                "local_address": None,
            }
        ]
        # Only 1 pre-check DNS call (port=None) + 1 connection-boundary DNS call (port=443)
        assert dns_queries == [
            ("cdn.genlook-results.example", None),
            ("cdn.genlook-results.example", 443),
        ]

        # Also verify when result_network_backend=None (real SyncBackend.connect_tcp inheritance)
        super_calls: list[tuple[str, int]] = []

        def _fake_super_connect_tcp(
            self_backend: httpcore.SyncBackend,
            host: str,
            port: int,
            timeout: float | None = None,
            local_address: str | None = None,
            socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
        ) -> httpcore.NetworkStream:
            super_calls.append((host, port))
            return _MockTLSStream(backend, _http_200_png_response())

        monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", _fake_super_connect_tcp)
        dns_queries.clear()
        data2 = _provider(backend=None).download_result_image(
            "https://cdn.genlook-results.example/out.png"
        )
        assert data2 == VALID_PNG
        assert super_calls == [("93.184.216.34", 443)]

    def test_8_tls_uses_original_hostname_sni_and_cert_verification(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = _RecordingNetworkBackend()
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: _addrinfo_entries(["93.184.216.34"], port or 443),
        )
        data = _provider(backend=backend).download_result_image(
            "https://cdn.genlook-results.example/path/result.png?sig=abc"
        )
        assert data == VALID_PNG
        assert backend.tcp_connects[0]["host"] == "93.184.216.34"
        assert len(backend.tls_handshakes) == 1
        tls = backend.tls_handshakes[0]
        assert tls["server_hostname"] == "cdn.genlook-results.example"
        assert tls["check_hostname"] is True
        assert tls["verify_mode"] == ssl.CERT_REQUIRED
        wire_request = bytes(backend.sent_bytes).decode("ascii", errors="replace")
        assert "Host: cdn.genlook-results.example\r\n" in wire_request
        assert "x-api-key" not in wire_request.lower()

    def test_9_redirect_to_private_address_not_followed_and_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = _RecordingNetworkBackend(
            raw_response=_http_redirect_response("https://169.254.169.254/latest/meta-data/")
        )
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: _addrinfo_entries(["93.184.216.34"], port or 443),
        )
        with pytest.raises(ProviderPayloadError) as exc_info:
            _provider(backend=backend).download_result_image(
                "https://cdn.genlook-results.example/redirect.png"
            )
        assert getattr(exc_info.value, "provider_error_code", None) == "RESULT_DOWNLOAD_REJECTED"
        assert len(backend.tcp_connects) == 1

        # Also verify mock http_client path cannot follow redirects even if follow_redirects=True
        seen_urls: list[str] = []

        def _mock_handler(request: httpx.Request) -> httpx.Response:
            seen_urls.append(str(request.url))
            return httpx.Response(302, headers={"Location": "http://127.0.0.1:8080/admin"})

        mock_client = httpx.Client(
            transport=httpx.MockTransport(_mock_handler),
            follow_redirects=True,
        )
        with pytest.raises(ProviderPayloadError) as exc_info2:
            _provider(http_client=mock_client).download_result_image(
                "https://cdn.genlook-results.example/redirect.png"
            )
        assert getattr(exc_info2.value, "provider_error_code", None) == "RESULT_DOWNLOAD_REJECTED"
        assert seen_urls == ["https://cdn.genlook-results.example/redirect.png"]

    def test_10_env_proxy_variables_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            monkeypatch.setenv(var, "http://127.0.0.1:9999")

        backend = _RecordingNetworkBackend()
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: _addrinfo_entries(["93.184.216.34"], port or 443),
        )
        data = _provider(backend=backend).download_result_image(
            "https://cdn.genlook-results.example/out.png"
        )
        assert data == VALID_PNG
        assert len(backend.tcp_connects) == 1
        assert backend.tcp_connects[0]["host"] == "93.184.216.34"
        assert backend.tcp_connects[0]["port"] == 443

    @pytest.mark.parametrize(
        "bad_url",
        [
            "ftp://cdn.genlook-results.example/out.png",
            "file:///etc/passwd",
            "http://cdn.genlook-results.example/out.png",
            "https://user:pass@cdn.genlook-results.example/out.png",
            "https://user@cdn.genlook-results.example/out.png",
            "https://@cdn.genlook-results.example/out.png",
            "https://cdn.genlook-results.example\\@127.0.0.1/out.png",
            "https://cdn.genlook-results.example:abc/out.png",
            "https://cdn.genlook-results.example:/out.png",
            "https://cdn.genlook-results.example:0/out.png",
            "https://cdn.genlook-results.example:65536/out.png",
            "https://cdn.genlook-results.example:8443/out.png",
            "https://cdn.genlook-results.example:80/out.png",
            "https://localhost/out.png",
            "https://sub.localhost/out.png",
            "https://internal.service.local/out.png",
            "https://metadata.internal/out.png",
            "https://2130706433/out.png",
            "https://0177.0.0.1/out.png",
        ],
    )
    def test_11_invalid_scheme_credentials_malformed_and_unexpected_ports_rejected(
        self, monkeypatch: pytest.MonkeyPatch, bad_url: str
    ) -> None:
        backend = _RecordingNetworkBackend()
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: _addrinfo_entries(["93.184.216.34"], port or 443),
        )
        with pytest.raises(ProviderPayloadError) as exc_info:
            _provider(backend=backend).download_result_image(bad_url)
        assert getattr(exc_info.value, "provider_error_code", None) == "RESULT_DOWNLOAD_REJECTED"
        assert backend.tcp_connects == []

    def test_11b_allow_http_cannot_bypass_host_ip_or_https_443_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tcp_connects: list[tuple[str, int]] = []
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: _addrinfo_entries(["169.254.169.254"], port or 443),
        )
        monkeypatch.setattr(
            httpcore.SyncBackend,
            "connect_tcp",
            lambda self_b, host, port, timeout=None, local_address=None, socket_options=None: (
                tcp_connects.append((host, port)),
                _MockTLSStream(_RecordingNetworkBackend(), _http_200_png_response()),
            )[1],
        )
        # Production ignores allow_insecure_urls / http:// base_url and uses zero test injection
        prod_provider = _provider(
            allow_insecure_urls=True,
            is_production=True,
            base_url="http://genlook.internal/tryon/v1",
        )
        with pytest.raises(ProviderPayloadError):
            prod_provider.download_result_image("http://cdn.genlook-results.example/out.png")
        with pytest.raises(ProviderPayloadError):
            prod_provider.download_result_image("https://cdn.genlook-results.example:8443/out.png")
        with pytest.raises(ProviderPayloadError):
            prod_provider.download_result_image("https://127.0.0.1/out.png")
        assert _is_safe_result_url("http://cdn.genlook-results.example/out.png", allow_http=True, is_production=True) is False
        assert _is_safe_result_url("https://127.0.0.1/out.png", allow_http=True, is_production=False) is False
        assert _is_safe_result_url("https://metadata-rebind.example/out.png", allow_http=True, is_production=False) is False
        assert tcp_connects == []

    def test_12_dns_failure_and_empty_dns_results_fail_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = _RecordingNetworkBackend()

        # DNS resolution raises gaierror (OSError)
        def _fail_dns(host: str, port: Any) -> list[tuple[Any, ...]]:
            raise socket.gaierror("Temporary failure in name resolution")

        monkeypatch.setattr(socket, "getaddrinfo", _fail_dns)
        with pytest.raises(ProviderPayloadError) as exc_info:
            _provider(backend=backend).download_result_image(
                "https://cdn.genlook-results.example/out.png"
            )
        assert getattr(exc_info.value, "provider_error_code", None) == "RESULT_DOWNLOAD_REJECTED"
        assert backend.tcp_connects == []

        # DNS resolution returns empty list []
        monkeypatch.setattr(socket, "getaddrinfo", lambda host, port: [])
        with pytest.raises(ProviderPayloadError) as exc_info2:
            _provider(backend=backend).download_result_image(
                "https://cdn.genlook-results.example/out.png"
            )
        assert getattr(exc_info2.value, "provider_error_code", None) == "RESULT_DOWNLOAD_REJECTED"
        assert backend.tcp_connects == []


class TestP43CProductionTransportBypassAudit:
    def test_13_production_rejects_all_injected_clients_and_backends_regardless_of_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg_prod = GenlookTryOnConfig(api_key=TEST_API_KEY, is_production=True)
        for pytest_env in ("test-node", None):
            if pytest_env is None:
                monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
            else:
                monkeypatch.setenv("PYTEST_CURRENT_TEST", pytest_env)

            with httpx.Client() as ordinary_client:
                with pytest.raises(CommercialProviderConfigurationError, match="forbidden when is_production=True"):
                    GenlookTryOnProvider(cfg_prod, http_client=ordinary_client)
            with pytest.raises(CommercialProviderConfigurationError, match="forbidden when is_production=True"):
                GenlookTryOnProvider(cfg_prod, http_client=object())
            with pytest.raises(CommercialProviderConfigurationError, match="forbidden when is_production=True"):
                GenlookTryOnProvider(cfg_prod, result_network_backend=_RecordingNetworkBackend())

            # Default construction without test hooks succeeds in any environment
            provider = GenlookTryOnProvider(cfg_prod)
            assert provider._http_client is None
            assert provider._result_network_backend is None

    def test_14_production_rejects_mock_transport_and_pinned_client_injection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg_prod = GenlookTryOnConfig(api_key=TEST_API_KEY, is_production=True)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_14_mock_transport_rejected")

        with httpx.Client() as ordinary_client:
            with pytest.raises(CommercialProviderConfigurationError):
                GenlookTryOnProvider(cfg_prod, http_client=ordinary_client)

        with httpx.Client(
            transport=httpx.MockTransport(lambda req: httpx.Response(200)),
            mounts={"https://": httpx.HTTPTransport()},
        ) as mounted_client:
            with pytest.raises(CommercialProviderConfigurationError):
                GenlookTryOnProvider(cfg_prod, http_client=mounted_client)

        # MockTransport and _PinnedSSRFTransport clients are ALSO rejected when is_production=True
        with httpx.Client(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, content=VALID_PNG))
        ) as mock_client:
            with pytest.raises(CommercialProviderConfigurationError, match="forbidden when is_production=True"):
                GenlookTryOnProvider(cfg_prod, http_client=mock_client)
            with pytest.raises(CommercialProviderConfigurationError, match="for_tests requires"):
                GenlookTryOnProvider.for_tests(cfg_prod, http_client=mock_client)

        with httpx.Client(transport=_PinnedSSRFTransport(is_production=True)) as pinned_client:
            with pytest.raises(CommercialProviderConfigurationError, match="forbidden when is_production=True"):
                GenlookTryOnProvider(cfg_prod, http_client=pinned_client)

    def test_15_post_init_attribute_mutation_blocked_and_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: _addrinfo_entries(["93.184.216.34"], port or 443),
        )
        cfg_prod = GenlookTryOnConfig(api_key=TEST_API_KEY, is_production=True)
        provider = GenlookTryOnProvider(cfg_prod)

        # Direct attribute mutation after construction is blocked
        with httpx.Client() as ordinary_client:
            with pytest.raises(AttributeError, match="immutable"):
                provider._http_client = ordinary_client  # type: ignore[misc]
            with pytest.raises(AttributeError, match="immutable"):
                provider._result_network_backend = _RecordingNetworkBackend()  # type: ignore[misc]
            with pytest.raises(AttributeError, match="immutable"):
                provider.config = GenlookTryOnConfig(api_key=TEST_API_KEY, is_production=False)  # type: ignore[misc]
            with pytest.raises(AttributeError, match="immutable"):
                provider._is_production = False  # type: ignore[misc]

            # Even bypassing __setattr__ via object.__setattr__ fails closed without network I/O
            object.__setattr__(provider, "_http_client", ordinary_client)
            with pytest.raises(ProviderPayloadError) as exc_info:
                provider.download_result_image("https://cdn.genlook-results.example/out.png")
            assert getattr(exc_info.value, "provider_error_code", None) == "RESULT_DOWNLOAD_REJECTED"

        # Mutated result_network_backend via object.__setattr__ also fails closed without network I/O
        backend = _RecordingNetworkBackend()
        object.__setattr__(provider, "_http_client", None)
        object.__setattr__(provider, "_result_network_backend", backend)
        with pytest.raises(ProviderPayloadError) as exc_info2:
            provider.download_result_image("https://cdn.genlook-results.example/out.png")
        assert getattr(exc_info2.value, "provider_error_code", None) == "RESULT_DOWNLOAD_REJECTED"
        assert backend.tcp_connects == []

    def test_16_production_execute_tryon_inference_propagates_is_production_and_uses_pinned_transport(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import asyncio
        from datetime import datetime, timezone
        from uuid import uuid4
        import app.application.tryon as tryon_app
        from app.config.settings import Settings
        from app.domain.ports.repositories import WardrobeItemRecord
        from tests.fakes.fake_storage import FakeStorageAdapter

        prod_settings = Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://prod_user:StrongProdPass123!@db.internal:5432/prod_db",
            auth_secret="x" * 40,
            allow_dev_token=False,
            media_storage_provider="r2",
            r2_bucket_name="prod-bucket",
            r2_account_id="acc-prod",
            r2_access_key_id="key-prod",
            r2_secret_access_key="sec-prod",
            media_upload_hmac_secret="y" * 40,
            operator_api_key="z" * 40,
            tryon_provider="genlook",
            genlook_api_key=TEST_API_KEY,
            genlook_poll_interval_s=0.01,
            genlook_poll_timeout_s=1.0,
        )
        assert prod_settings.is_production is True

        monkeypatch.setattr(tryon_app, "get_settings", lambda: prod_settings)
        # Ensure production injection fails closed outside pytest during provider construction
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        observed_init: list[dict[str, Any]] = []
        pinned_calls: list[dict[str, Any]] = []
        orig_init = GenlookTryOnProvider.__init__

        def _spy_init(self_p, config, *, http_client=None, result_network_backend=None):
            observed_init.append(
                {
                    "is_production": config.is_production,
                    "http_client": http_client,
                    "result_network_backend": result_network_backend,
                }
            )
            orig_init(
                self_p,
                config,
                http_client=http_client,
                result_network_backend=result_network_backend,
            )

        monkeypatch.setattr(GenlookTryOnProvider, "__init__", _spy_init)
        monkeypatch.setattr(
            GenlookTryOnProvider,
            "upload_person_image",
            lambda self_p, **kw: type("Up", (), {"image_id": "img-1", "keep_for_days": 1, "request_id": "r1"})(),
        )
        monkeypatch.setattr(
            GenlookTryOnProvider,
            "create_tryon",
            lambda self_p, **kw: type(
                "Cr",
                (),
                {
                    "generation_id": "gen-1",
                    "status": "PENDING",
                    "product_external_ids": ("g1",),
                    "request_id": "r2",
                    "idempotency_replayed": False,
                },
            )(),
        )
        monkeypatch.setattr(
            GenlookTryOnProvider,
            "poll_generation",
            lambda self_p, gid, **kw: type(
                "St",
                (),
                {"generation_id": gid, "status": "COMPLETED", "result_image_url": "https://cdn.genlook-results.example/out.png"},
            )(),
        )
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: _addrinfo_entries(["93.184.216.34"], port or 443),
        )

        orig_transport_init = _PinnedSSRFTransport.__init__

        def _spy_transport_init(self_t, **kw):
            pinned_calls.append(dict(kw))
            orig_transport_init(self_t, **kw)

        monkeypatch.setattr(_PinnedSSRFTransport, "__init__", _spy_transport_init)
        monkeypatch.setattr(
            httpcore.SyncBackend,
            "connect_tcp",
            lambda self_b, host, port, timeout=None, local_address=None, socket_options=None: _MockTLSStream(
                _RecordingNetworkBackend(), _http_200_png_response()
            ),
        )

        storage = FakeStorageAdapter()
        repo = tryon_app.InMemoryTryOnJobRepository()
        user_id = uuid4()
        gid = uuid4()
        job_id = uuid4()
        garment_key = f"users/{user_id}/wardrobe/{gid}/garment.png"
        person_key = f"users/{user_id}/tryon/{job_id}/person.png"
        asyncio.run(storage.put_object(garment_key, VALID_PNG, content_type="image/png"))
        asyncio.run(storage.put_object(person_key, VALID_PNG, content_type="image/png"))

        class _StubWardrobeRepo:
            def get_by_id(self, *, user_id, item_id):
                now = datetime.now(timezone.utc)
                return WardrobeItemRecord(
                    id=item_id,
                    user_id=user_id,
                    name="Test Shirt",
                    category="tops",
                    color="blue",
                    material="cotton",
                    is_favorite=False,
                    image_ref={"key": garment_key},
                    created_at=now,
                    updated_at=now,
                    fit="regular",
                )

        repo.create(
            job_id=job_id,
            user_id=user_id,
            outfit_source="wardrobe",
            garment_id=gid,
            garment_ids=[str(gid)],
            provider="genlook",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
            person_media_ref={"key": person_key, "contentHash": "hash-1"},
        )

        asyncio.run(
            tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=user_id,
                job_repo=repo,
                storage=storage,
                wardrobe_repo=_StubWardrobeRepo(),
            )
        )

        assert observed_init == [
            {
                "is_production": True,
                "http_client": None,
                "result_network_backend": None,
            }
        ]
        assert pinned_calls == [
            {
                "allow_http": False,
                "is_production": True,
                "network_backend": None,
            }
        ]
        done = repo.get_by_id(user_id=user_id, job_id=job_id)
        assert done is not None
        assert done.status == "completed"


class TestP43DNoPytestEnvSecurityBoundary:
    def test_17_non_production_test_config_and_for_tests_support_mocked_transports(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Works even with PYTEST_CURRENT_TEST removed, proving env var is not the boundary
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        cfg_test = GenlookTryOnConfig(api_key=TEST_API_KEY, is_production=False)

        with httpx.Client(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, content=VALID_PNG))
        ) as mock_client:
            provider = GenlookTryOnProvider.for_tests(cfg_test, http_client=mock_client)
            assert (
                provider.download_result_image("https://cdn.genlook-results.example/out.png")
                == VALID_PNG
            )

        backend = _RecordingNetworkBackend()
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: _addrinfo_entries(["93.184.216.34"], port or 443),
        )
        provider_backend = GenlookTryOnProvider.for_tests(
            cfg_test, result_network_backend=backend
        )
        assert (
            provider_backend.download_result_image("https://cdn.genlook-results.example/out.png")
            == VALID_PNG
        )
        assert len(backend.tcp_connects) == 1
        assert backend.tcp_connects[0]["host"] == "93.184.216.34"

    def test_18_production_cannot_switch_to_injected_client_via_config_or_attr_mutation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: _addrinfo_entries(["93.184.216.34"], port or 443),
        )
        cfg_prod = GenlookTryOnConfig(api_key=TEST_API_KEY, is_production=True)
        provider = GenlookTryOnProvider(cfg_prod)
        called: list[str] = []

        with httpx.Client(
            transport=httpx.MockTransport(
                lambda req: (called.append(str(req.url)), httpx.Response(200, content=VALID_PNG))[1]
            )
        ) as mock_client:
            # Attempt to downgrade config AND inject mock_client via object.__setattr__
            object.__setattr__(
                provider,
                "_config",
                GenlookTryOnConfig(api_key=TEST_API_KEY, is_production=False),
            )
            object.__setattr__(provider, "_http_client", mock_client)
            with pytest.raises(ProviderPayloadError) as exc_info:
                provider.download_result_image("https://cdn.genlook-results.example/out.png")
            assert getattr(exc_info.value, "provider_error_code", None) == "RESULT_DOWNLOAD_REJECTED"
            assert called == []

            # _send also refuses injected client when _is_production was True at construction
            with pytest.raises(CommercialProviderConfigurationError):
                provider._send(
                    "GET",
                    "https://api.genlook.app/tryon/v1/account/credits",
                    timeout=httpx.Timeout(5.0),
                )
            assert called == []

    def test_19_no_real_network_connection_can_use_unpinned_transport_in_any_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Unpinned httpx.Client() is rejected even when is_production=False
        cfg_non_prod = GenlookTryOnConfig(api_key=TEST_API_KEY, is_production=False)
        with httpx.Client() as ordinary_client:
            with pytest.raises(CommercialProviderConfigurationError, match="unpinned httpx.Client"):
                GenlookTryOnProvider(cfg_non_prod, http_client=ordinary_client)
            with pytest.raises(CommercialProviderConfigurationError, match="BaseTransport"):
                GenlookTryOnProvider(cfg_non_prod, http_client=httpx.HTTPTransport())

        # Both is_production=False and is_production=True with http_client=None route real
        # downloads exclusively through _PinnedSSRFTransport and _PinnedDNSBackend
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: _addrinfo_entries(["93.184.216.34"], port or 443),
        )
        pinned_inits: list[bool] = []
        super_connects: list[tuple[str, int]] = []
        orig_transport_init = _PinnedSSRFTransport.__init__

        def _spy_transport(self_t, **kw):
            pinned_inits.append(bool(kw.get("is_production")))
            orig_transport_init(self_t, **kw)

        monkeypatch.setattr(_PinnedSSRFTransport, "__init__", _spy_transport)
        monkeypatch.setattr(
            httpcore.SyncBackend,
            "connect_tcp",
            lambda self_b, host, port, timeout=None, local_address=None, socket_options=None: (
                super_connects.append((host, port)),
                _MockTLSStream(_RecordingNetworkBackend(), _http_200_png_response()),
            )[1],
        )

        for is_prod in (False, True):
            provider = GenlookTryOnProvider(
                GenlookTryOnConfig(api_key=TEST_API_KEY, is_production=is_prod)
            )
            assert (
                provider.download_result_image("https://cdn.genlook-results.example/out.png")
                == VALID_PNG
            )

        assert pinned_inits == [False, True]
        assert super_connects == [("93.184.216.34", 443), ("93.184.216.34", 443)]


