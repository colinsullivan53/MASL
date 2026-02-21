"""Tests for the MASL lexer."""

from src.lexer import Lexer, TokenType, LexerError


def test_basic_tokens():
    lexer = Lexer("Match { }")
    tokens = lexer.tokenize()
    types = [t.type for t in tokens]
    assert TokenType.MATCH in types
    assert TokenType.LBRACE in types
    assert TokenType.RBRACE in types
    assert types[-1] == TokenType.EOF


def test_player_tokens():
    lexer = Lexer("P1 P2 P3 P4")
    tokens = lexer.tokenize()
    players = [t for t in tokens if t.type == TokenType.PLAYER]
    assert len(players) == 4
    assert [p.value for p in players] == ["P1", "P2", "P3", "P4"]


def test_chain_operator():
    lexer = Lexer("attack :: wait 14 :: hold 3")
    tokens = lexer.tokenize()
    types = [t.type for t in tokens]
    assert types.count(TokenType.CHAIN) == 2


def test_keywords():
    lexer = Lexer("Static Human Def let if else while for in wait hold")
    tokens = lexer.tokenize()
    types = [t.type for t in tokens]
    assert TokenType.STATIC in types
    assert TokenType.HUMAN in types
    assert TokenType.DEF in types
    assert TokenType.WAIT in types
    assert TokenType.HOLD in types


def test_no_bot_keywords():
    lexer = Lexer("Bot func Main extends override super this")
    tokens = lexer.tokenize()
    types = [t.type for t in tokens]
    assert all(t == TokenType.IDENTIFIER for t in types[:-1])


def test_operators():
    lexer = Lexer("+ - * / % < > <= >= == != && || !")
    tokens = lexer.tokenize()
    types = [t.type for t in tokens]
    assert TokenType.LTE in types
    assert TokenType.AND in types
    assert TokenType.OR in types


def test_literals():
    lexer = Lexer('42 3.14 "hello" true false')
    tokens = lexer.tokenize()
    ints = [t for t in tokens if t.type == TokenType.INTEGER]
    floats = [t for t in tokens if t.type == TokenType.FLOAT]
    strings = [t for t in tokens if t.type == TokenType.STRING]
    bools_t = [t for t in tokens if t.type == TokenType.TRUE]
    bools_f = [t for t in tokens if t.type == TokenType.FALSE]
    assert len(ints) == 1 and ints[0].value == 42
    assert len(floats) == 1 and abs(floats[0].value - 3.14) < 0.001
    assert len(strings) == 1 and strings[0].value == "hello"
    assert len(bools_t) == 1
    assert len(bools_f) == 1


def test_include_directive():
    lexer = Lexer('#INCLUDE "path/to/file.masl"')
    tokens = lexer.tokenize()
    assert tokens[0].type == TokenType.INCLUDE
    assert tokens[1].type == TokenType.STRING



def test_comments_skipped():
    lexer = Lexer("attack // this is a comment\nwait 14")
    tokens = lexer.tokenize()
    types = [t.type for t in tokens]
    assert TokenType.IDENTIFIER in types
    assert TokenType.WAIT in types
    assert TokenType.INTEGER in types


def test_source_location_tracking():
    lexer = Lexer("Match {\n    P1 attack\n}")
    tokens = lexer.tokenize()
    p1 = [t for t in tokens if t.type == TokenType.PLAYER][0]
    assert p1.line == 2
    assert p1.column > 0


def test_negative_numbers():
    lexer = Lexer("-1.0 -5")
    tokens = lexer.tokenize()
    # Should produce MINUS then number tokens (parser handles unary minus)
    assert tokens[0].type == TokenType.MINUS
    assert tokens[1].type == TokenType.FLOAT
    assert tokens[2].type == TokenType.MINUS
    assert tokens[3].type == TokenType.INTEGER


def test_unknown_char_error():
    """Unknown characters like ; should raise LexerError."""
    import pytest
    with pytest.raises(LexerError):
        Lexer("button(A) ; wait 14").tokenize()
