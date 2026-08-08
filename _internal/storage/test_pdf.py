from unittest.mock import patch

import pytest

from .exceptions import PDFRenderException
from .pdf import PdfRenderer


class TestRender:
    @patch("_internal.storage.pdf.HTML")
    def test_returns_the_pdf_bytes_produced_by_weasyprint(self, mock_html):
        mock_html.return_value.write_pdf.return_value = b"%PDF-1.7 fake content"
        renderer = PdfRenderer()

        result = renderer.render("<html><body>relatório</body></html>")

        mock_html.assert_called_once_with(string="<html><body>relatório</body></html>")
        assert result == b"%PDF-1.7 fake content"

    @patch("_internal.storage.pdf.HTML")
    def test_wraps_weasyprint_failures_in_pdf_render_exception(self, mock_html):
        mock_html.side_effect = Exception("invalid markup")
        renderer = PdfRenderer()

        with pytest.raises(PDFRenderException):
            renderer.render("<html>")
