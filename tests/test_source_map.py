from src.source_map import SourceLocation, SourceMap, SourceMapEntry, format_error_context

def test_source_location_creation():
    loc = SourceLocation("test.masl", 5, 10, "P1 attack :: wait 14")
    assert loc.filename == "test.masl"
    assert loc.line == 5
    assert loc.column == 10
    assert loc.source_line == "P1 attack :: wait 14"

def test_source_map_lookup():
    entries = [
        SourceMapEntry("a.masl", 1, "line one"),
        SourceMapEntry("a.masl", 2, "line two"),
        SourceMapEntry("b.masl", 1, "other file"),
    ]
    sm = SourceMap(entries)
    loc = sm.get_location(2, 5)  # expanded line 2 -> a.masl:2
    assert loc.filename == "a.masl"
    assert loc.line == 2
    assert loc.column == 5

def test_format_error_context():
    loc = SourceLocation("test.masl", 3, 14, "P1 attack :: wiat 14")
    result = format_error_context(loc, "Unknown keyword 'wiat'")
    assert "test.masl:3" in result
    assert "wiat" in result
