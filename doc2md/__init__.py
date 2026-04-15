"""doc2md — scan a folder for documents and emit clean Markdown for LLM ingest."""
from doc2md.pipeline import BuildResult, build_corpus

__all__ = ["build_corpus", "BuildResult"]
__version__ = "0.2.0"
