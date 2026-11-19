"""PyMuPDF import that works with old ('fitz') and new ('pymupdf') package names."""
try:
    import pymupdf as fitz  # PyMuPDF >= 1.24
except ImportError:  # pragma: no cover
    import fitz  # noqa: F401
