from weasyprint import HTML

from .exceptions import PDFRenderException


class PdfRenderer:
    """Renders HTML content into PDF bytes."""

    def render(self, html: str) -> bytes:
        try:
            pdf_bytes = HTML(string=html).write_pdf()
            # write_pdf() only returns None when called with a `target` (e.g. a file path);
            # we never pass one, so this always yields bytes in practice.
            assert pdf_bytes is not None
            return pdf_bytes
        except Exception as e:
            raise PDFRenderException(str(e)) from e
