from dataclasses import dataclass


@dataclass
class SourceLocation:
    """Location in a source file."""
    filename: str
    line: int
    column: int
    source_line: str


@dataclass
class SourceMapEntry:
    """Maps an expanded line to its origin."""
    filename: str
    original_line: int
    source_text: str


class SourceMap:
    """Maps expanded source lines back to original files."""

    def __init__(self, entries: list[SourceMapEntry] | None = None):
        self.entries: list[SourceMapEntry] = entries or []

    def add_entry(self, filename: str, original_line: int, source_text: str) -> None:
        """Add a mapping entry."""
        self.entries.append(SourceMapEntry(filename, original_line, source_text))

    def get_location(self, expanded_line: int, column: int = 0) -> SourceLocation:
        """Get the original location for an expanded line number."""
        idx = expanded_line - 1 # offset for 0-indexing from 1-indexed line nums 
        if 0 <= idx < len(self.entries):
            entry = self.entries[idx]
            return SourceLocation(
                filename=entry.filename,
                line=entry.original_line,
                column=column,
                source_line=entry.source_text,
            )
        return SourceLocation("<unknown>", expanded_line, column, "")


def format_error_context(location: SourceLocation, message: str) -> str:
    """Format an error message with source context."""
    lines = []
    lines.append(f"Error in {location.filename}:{location.line}")
    if location.source_line:
        lines.append(f"  {location.line} | {location.source_line}")
        if location.column > 0: 
            prefix_len = len(str(location.line)) + 3  # "  N | "
            lines.append(" " * (prefix_len + location.column) + "^")
    lines.append(message)
    return "\n".join(lines)
