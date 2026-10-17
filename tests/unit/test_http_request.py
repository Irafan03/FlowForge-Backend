"""
Unit tests for the HTTP request integration, focusing on SSRF protection.
These tests do NOT make real network calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.engine.node_executor import NodeExecutionError
from app.integrations.http_request import _check_ssrf, execute_http_request


class TestSSRFProtection:
    def test_localhost_blocked(self):
        with pytest.raises(NodeExecutionError, match="SSRF"):
            _check_ssrf("http://localhost/admin")

    def test_127_blocked(self):
        with pytest.raises(NodeExecutionError, match="SSRF"):
            _check_ssrf("http://127.0.0.1/")

    def test_private_range_blocked(self):
        with pytest.raises(NodeExecutionError, match="SSRF"):
            _check_ssrf("http://192.168.1.1/")

    def test_10_range_blocked(self):
        with pytest.raises(NodeExecutionError, match="SSRF"):
            _check_ssrf("http://10.0.0.1/api")

    def test_172_16_range_blocked(self):
        with pytest.raises(NodeExecutionError, match="SSRF"):
            _check_ssrf("http://172.16.0.1/")

    def test_link_local_blocked(self):
        with pytest.raises(NodeExecutionError, match="SSRF"):
            _check_ssrf("http://169.254.169.254/latest/meta-data/")

    def test_ftp_scheme_blocked(self):
        with pytest.raises(NodeExecutionError, match="scheme"):
            _check_ssrf("ftp://example.com/file")

    def test_file_scheme_blocked(self):
        with pytest.raises(NodeExecutionError, match="scheme"):
            _check_ssrf("file:///etc/passwd")

    def test_public_ip_allowed(self):
        """1.1.1.1 is a public Cloudflare DNS server — should not raise."""
        # Patch socket.getaddrinfo so we don't need real DNS
        import socket
        with patch("app.integrations.http_request.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(socket.AF_INET, None, None, None, ("1.1.1.1", 0))]
            _check_ssrf("https://cloudflare.com/")  # Should not raise

    def test_no_scheme_raises(self):
        with pytest.raises(NodeExecutionError):
            _check_ssrf("//example.com")

    def test_missing_hostname_raises(self):
        with pytest.raises(NodeExecutionError, match="hostname"):
            _check_ssrf("http:///path")


class TestExecuteHttpRequest:
    def _mock_response(self, status_code=200, json_body=None, text_body=None):
        """Build a mock httpx.Response."""
        import httpx

        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code
        resp.is_success = 200 <= status_code < 300
        resp.headers = {"content-type": "application/json"}
        resp.content = b'{"ok": true}'
        if json_body is not None:
            resp.json.return_value = json_body
        else:
            resp.json.side_effect = ValueError("not json")
            resp.text = text_body or ""
        return resp

    def test_successful_get(self):
        with patch("app.integrations.http_request._check_ssrf"), \
             patch("httpx.Client") as MockClient:
            mock_resp = self._mock_response(json_body={"hello": "world"})
            MockClient.return_value.__enter__.return_value.request.return_value = mock_resp

            result = execute_http_request({"url": "https://example.com/api", "method": "GET"})

        assert result["status_code"] == 200
        assert result["ok"] is True
        assert result["body"] == {"hello": "world"}

    def test_post_with_json_body(self):
        with patch("app.integrations.http_request._check_ssrf"), \
             patch("httpx.Client") as MockClient:
            mock_resp = self._mock_response(json_body={"created": True})
            MockClient.return_value.__enter__.return_value.request.return_value = mock_resp

            result = execute_http_request({
                "url": "https://example.com/api",
                "method": "POST",
                "body": {"key": "value"},
            })

        assert result["status_code"] == 200

    def test_invalid_method_raises(self):
        with pytest.raises(NodeExecutionError, match="method"):
            execute_http_request({"url": "https://example.com", "method": "FAKEMETHOD"})

    def test_missing_url_raises(self):
        with pytest.raises(NodeExecutionError, match="url"):
            execute_http_request({"method": "GET"})

    def test_timeout_raises_node_error(self):
        import httpx

        with patch("app.integrations.http_request._check_ssrf"), \
             patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__.return_value.request.side_effect = (
                httpx.TimeoutException("timeout")
            )

            with pytest.raises(NodeExecutionError, match="timed out"):
                execute_http_request({"url": "https://example.com", "method": "GET"})

    def test_network_error_raises_node_error(self):
        import httpx

        with patch("app.integrations.http_request._check_ssrf"), \
             patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__.return_value.request.side_effect = (
                httpx.ConnectError("refused")
            )

            with pytest.raises(NodeExecutionError, match="network error"):
                execute_http_request({"url": "https://example.com", "method": "GET"})
