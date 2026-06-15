"""Regression tests — ad-hoc rendering preview client (no network).

Covers: multipart form-data encoding (all fields travel in the body, mirroring
the known-working Postman call), request URL/header construction (urlopen
mocked), HTTP error mapping to RenderPreviewError, .env.ai-documents parsing,
and env-var precedence over the file.
"""

from __future__ import annotations

import io
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from velocity_converter.render_preview import (
    DEFAULT_DOCUMENT_CONFIG,
    ENV_FILE,
    ENV_PREFIX,
    RenderPreviewError,
    _encode_multipart,
    load_env,
    render_template,
    require_settings,
)


class TestMultipartEncoding(unittest.TestCase):
    def test_fields_encoded(self):
        body, content_type = _encode_multipart(
            {"template": "Hello $data.name", "referenceType": "quote"}
        )
        self.assertIn("multipart/form-data; boundary=", content_type)
        boundary = content_type.split("boundary=")[1]
        text = body.decode("utf-8")
        self.assertIn('Content-Disposition: form-data; name="template"', text)
        self.assertIn("Hello $data.name\r\n", text)
        self.assertIn('Content-Disposition: form-data; name="referenceType"', text)
        self.assertIn("quote\r\n", text)
        self.assertTrue(text.endswith(f"--{boundary}--\r\n"))


class TestRenderTemplate(unittest.TestCase):
    def _call(self, urlopen_mock, **overrides):
        kwargs = dict(
            api_url="https://api.example.socotra.com/",
            tenant_locator="tenant-123",
            token="tok",
            template_text="$data.x",
            reference_type="quote",
            reference_locator="loc-1",
        )
        kwargs.update(overrides)
        with mock.patch("urllib.request.urlopen", urlopen_mock):
            return render_template(**kwargs)

    @staticmethod
    def _response(payload: bytes, content_type: str = "application/pdf"):
        response = mock.MagicMock()
        response.read.return_value = payload
        response.headers.get.return_value = content_type
        response.__enter__ = lambda s: response
        response.__exit__ = lambda s, *a: False
        return response

    def test_request_url_headers_and_form_fields(self):
        urlopen = mock.MagicMock(return_value=self._response(b"%PDF-1.7 ok"))

        rendered, content_type = self._call(urlopen, product_name="ZenCover")
        self.assertEqual(rendered, b"%PDF-1.7 ok")
        self.assertEqual(content_type, "application/pdf")

        request = urlopen.call_args[0][0]
        self.assertEqual(request.method, "POST")
        # Everything rides in the form-data body — the URL carries no query.
        self.assertEqual(
            request.full_url,
            "https://api.example.socotra.com/document/tenant-123/documents/render",
        )
        self.assertEqual(request.get_header("Authorization"), "Bearer tok")

        body = request.data.decode("utf-8")
        for field, value in [
            ("referenceType", "quote"),
            ("referenceLocator", "loc-1"),
            ("templateFormat", "velocity"),
            ("productName", "ZenCover"),
        ]:
            self.assertIn(f'name="{field}"', body)
            self.assertIn(value, body)
        # The template MUST ride as a file part (filename present), not a plain
        # text field — the endpoint rejects a bare `template` string with
        # "template name or template file must be provided" (errorCode 216042).
        self.assertIn('name="template"; filename="template.vm"', body)
        self.assertIn("$data.x", body)
        # Default documentConfig JSON is inlined — no deployed config needed.
        self.assertIn('name="documentConfig"', body)
        self.assertIn(f'"name": "{DEFAULT_DOCUMENT_CONFIG["name"]}"', body)
        self.assertIn('"rendering": "dynamic"', body)

    def test_custom_document_config_overrides_default(self):
        urlopen = mock.MagicMock(return_value=self._response(b"x"))
        self._call(urlopen, document_config={"name": "Custom", "format": "html"})
        body = urlopen.call_args[0][0].data.decode("utf-8")
        self.assertIn('"name": "Custom"', body)
        self.assertNotIn('"pageSize"', body)

    def test_invalid_reference_type(self):
        with self.assertRaises(ValueError):
            self._call(mock.MagicMock(), reference_type="banana")

    def test_http_error_maps_to_render_preview_error(self):
        err = urllib.error.HTTPError(
            url="u", code=403, msg="forbidden", hdrs=None,
            fp=io.BytesIO(b"missing render-external permission"),
        )
        urlopen = mock.MagicMock(side_effect=err)
        with self.assertRaises(RenderPreviewError) as ctx:
            self._call(urlopen)
        self.assertEqual(ctx.exception.status, 403)
        self.assertIn("render-external", ctx.exception.body)

    def test_url_error_maps_to_render_preview_error(self):
        urlopen = mock.MagicMock(
            side_effect=urllib.error.URLError("connection refused")
        )
        with self.assertRaises(RenderPreviewError):
            self._call(urlopen)


class TestEnvLoading(unittest.TestCase):
    def test_env_file_parsed_and_process_env_wins(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ENV_FILE).write_text(
                "# comment\n"
                f"{ENV_PREFIX}API_URL=https://file.example/\n"
                f"{ENV_PREFIX}TENANT_LOCATOR='t-file'\n"
                "UNRELATED=ignored\n",
                encoding="utf-8",
            )
            with mock.patch.dict(
                "os.environ", {f"{ENV_PREFIX}API_URL": "https://env.example/"},
                clear=True,
            ):
                env = load_env(root)
        self.assertEqual(env[f"{ENV_PREFIX}API_URL"], "https://env.example/")
        self.assertEqual(env[f"{ENV_PREFIX}TENANT_LOCATOR"], "t-file")
        self.assertNotIn("UNRELATED", env)

    def test_require_settings_names_missing_keys(self):
        with self.assertRaises(RenderPreviewError) as ctx:
            require_settings({f"{ENV_PREFIX}API_URL": "https://x/"})
        message = str(ctx.exception)
        self.assertIn(f"{ENV_PREFIX}TENANT_LOCATOR", message)
        self.assertIn(f"{ENV_PREFIX}PAT", message)

        env = {
            f"{ENV_PREFIX}API_URL": "https://x/",
            f"{ENV_PREFIX}TENANT_LOCATOR": "t",
            f"{ENV_PREFIX}PAT": "tok",
        }
        self.assertEqual(require_settings(env), ("https://x/", "t", "tok"))


if __name__ == "__main__":
    unittest.main()
