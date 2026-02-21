"""MASL Lexer - Tokenizes source code into tokens."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.source_map import SourceLocation, SourceMap


class TokenType(Enum):
    """Token types for MASL."""

    # Special
    EOF = auto()
    IDENTIFIER = auto()

    # Literals
    INTEGER = auto()
    FLOAT = auto()
    STRING = auto()

    # Keywords
    MATCH = auto()
    GAME = auto()
    STAGE = auto()
    PLAYERS = auto()
    STOCKS = auto()
    TIME = auto()
    STATIC = auto()
    HUMAN = auto()
    DEF = auto()
    LET = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    IN = auto()
    CONTINUE = auto()
    BREAK = auto()
    TRUE = auto()
    FALSE = auto()
    WAIT = auto()
    HOLD = auto()

    # Delimiters
    LBRACE = auto()
    RBRACE = auto()
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    DOT = auto()
    CHAIN = auto()  # ::

    # Arithmetic operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()

    # Comparison operators
    LT = auto()
    GT = auto()
    LTE = auto()
    GTE = auto()
    EQ = auto()
    NEQ = auto()

    # Logical operators
    AND = auto()
    OR = auto()
    NOT = auto()

    # Assignment
    ASSIGN = auto()

    # Special tokens
    INCLUDE = auto()
    PLAYER = auto()


KEYWORDS = {
    "Match": TokenType.MATCH,
    "Game": TokenType.GAME,
    "Stage": TokenType.STAGE,
    "Players": TokenType.PLAYERS,
    "Stocks": TokenType.STOCKS,
    "Time": TokenType.TIME,
    "Static": TokenType.STATIC,
    "Human": TokenType.HUMAN,
    "Def": TokenType.DEF,
    "let": TokenType.LET,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "for": TokenType.FOR,
    "in": TokenType.IN,
    "continue": TokenType.CONTINUE,
    "break": TokenType.BREAK,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
    "wait": TokenType.WAIT,
    "hold": TokenType.HOLD,
}


@dataclass
class Token:
    """A single token."""

    type: TokenType
    value: Any
    line: int
    column: int
    source_location: SourceLocation | None = field(default=None)


class LexerError(Exception):
    """Error during lexing."""

    def __init__(self, message: str, line: int, column: int):
        self.line = line
        self.column = column
        super().__init__(f"{message} at line {line}, column {column}")


class Lexer:
    """Tokenizer for MASL source code."""

    def __init__(self, source: str, source_map: SourceMap | None = None):
        self.source = source
        self.source_map = source_map
        self.pos = 0
        self.line = 1
        self.column = 1

    def tokenize(self) -> list[Token]:
        """Tokenize the source and return a list of tokens."""
        tokens = []

        while self.pos < len(self.source):
            token = self._next_token()
            if token:
                tokens.append(token)

        tokens.append(Token(TokenType.EOF, "", self.line, self.column,
                           source_location=self._get_source_location(self.line, self.column)))
        return tokens

    def _get_source_location(self, line: int, column: int) -> SourceLocation | None:
        """Get source location for a line/column if source_map is available."""
        if self.source_map is None:
            return None
        return self.source_map.get_location(line, column)

    def _next_token(self) -> Token | None:
        """Read the next token from source."""
        if self.pos >= len(self.source):
            return None

        char = self.source[self.pos]
 
        if char.isspace():
            self._advance()
            return None
        if char == "/" and self._peek() == "/":
            self._skip_comment()
            return None
        if char == '"':
            return self._read_string() 
        if char.isdigit():
            return self._read_number() 
        if char == "#":
            return self._read_directive() 
        if char.isalpha() or char == "_":
            return self._read_identifier()

        # 2-character operators
        if char == ":" and self._peek() == ":":
            return self._read_multi_char(TokenType.CHAIN, "::")
        if char == "<" and self._peek() == "=":
            return self._read_multi_char(TokenType.LTE, "<=")
        if char == ">" and self._peek() == "=":
            return self._read_multi_char(TokenType.GTE, ">=")
        if char == "=" and self._peek() == "=":
            return self._read_multi_char(TokenType.EQ, "==")
        if char == "!" and self._peek() == "=":
            return self._read_multi_char(TokenType.NEQ, "!=")
        if char == "&" and self._peek() == "&":
            return self._read_multi_char(TokenType.AND, "&&")
        if char == "|" and self._peek() == "|":
            return self._read_multi_char(TokenType.OR, "||")

        # 1-character tokens
        single_char_tokens = {
            "{": TokenType.LBRACE,
            "}": TokenType.RBRACE,
            "(": TokenType.LPAREN,
            ")": TokenType.RPAREN,
            ",": TokenType.COMMA,
            ".": TokenType.DOT,
            "+": TokenType.PLUS,
            "-": TokenType.MINUS,
            "*": TokenType.STAR,
            "/": TokenType.SLASH,
            "%": TokenType.PERCENT,
            "<": TokenType.LT,
            ">": TokenType.GT,
            "!": TokenType.NOT,
            "=": TokenType.ASSIGN,
        }

        if char in single_char_tokens:
            return self._make_token(single_char_tokens[char], char)

        # Unknown
        raise LexerError(f"Unexpected character: {char!r}", self.line, self.column)

    def _make_token(self, token_type: TokenType, value: str) -> Token:
        """Create a token and advance."""
        token = Token(token_type, value, self.line, self.column,
                     source_location=self._get_source_location(self.line, self.column))
        self._advance()
        return token

    def _read_multi_char(self, token_type: TokenType, value: str) -> Token:
        """Read a multi-character token."""
        token = Token(token_type, value, self.line, self.column,
                     source_location=self._get_source_location(self.line, self.column))
        for _ in value:
            self._advance()
        return token

    def _read_identifier(self) -> Token:
        """Read an identifier, keyword, or player port."""
        start_line = self.line
        start_col = self.column
        start_pos = self.pos

        while self.pos < len(self.source) and (
            self.source[self.pos].isalnum() or self.source[self.pos] == "_"
        ):
            self._advance()

        value = self.source[start_pos : self.pos]
        source_location = self._get_source_location(start_line, start_col)

        # Check player ports
        if value in ("P1", "P2", "P3", "P4"):
            return Token(TokenType.PLAYER, value, start_line, start_col,
                        source_location=source_location)

        token_type = KEYWORDS.get(value, TokenType.IDENTIFIER)
        return Token(token_type, value, start_line, start_col,
                    source_location=source_location)

    def _read_number(self) -> Token:
        """Read an integer or float."""
        start_line = self.line
        start_col = self.column
        start_pos = self.pos
        has_dot = False

        while self.pos < len(self.source):
            char = self.source[self.pos]
            if char.isdigit():
                self._advance()
            elif char == "." and not has_dot:
                # Check if it's a decimal point (followed by num)
                next_char = self._peek()
                if next_char is not None and next_char.isdigit():
                    has_dot = True
                    self._advance()
                else:
                    break
            else:
                break

        value = self.source[start_pos : self.pos]
        if has_dot:
            return Token(TokenType.FLOAT, float(value), start_line, start_col,
                        source_location=self._get_source_location(start_line, start_col))
        else:
            return Token(TokenType.INTEGER, int(value), start_line, start_col,
                        source_location=self._get_source_location(start_line, start_col))

    def _read_string(self) -> Token:
        """Read a string literal."""
        start_line = self.line
        start_col = self.column
        self._advance()  # Skip start quote
        start_pos = self.pos

        while self.pos < len(self.source) and self.source[self.pos] != '"':
            if self.source[self.pos] == "\n":
                raise LexerError("Unterminated string", self.line, start_col)
            self._advance()

        if self.pos >= len(self.source):
            raise LexerError("Unterminated string", self.line, start_col)

        value = self.source[start_pos : self.pos]
        self._advance()  # Skip end quote
        return Token(TokenType.STRING, value, start_line, start_col,
                    source_location=self._get_source_location(start_line, start_col))

    def _read_directive(self) -> Token:
        """Read a preprocessor directive like #INCLUDE."""
        start_line = self.line
        start_col = self.column
        start_pos = self.pos
        self._advance()  # Skip '#'

        while self.pos < len(self.source) and self.source[self.pos].isalpha():
            self._advance()

        value = self.source[start_pos : self.pos]
        if value == "#INCLUDE":
            return Token(TokenType.INCLUDE, value, start_line, start_col,
                        source_location=self._get_source_location(start_line, start_col))

        raise LexerError(f"Unknown directive: {value}", start_line, start_col)

    def _skip_comment(self) -> None:
        """Skip a single-line comment."""
        while self.pos < len(self.source) and self.source[self.pos] != "\n":
            self._advance()

    def _advance(self) -> None:
        """Advance position by one character."""
        if self.pos < len(self.source):
            if self.source[self.pos] == "\n":
                self.line += 1
                self.column = 1
            else:
                self.column += 1
            self.pos += 1

    def _peek(self) -> str | None:
        """Peek at the next character without advancing."""
        if self.pos + 1 < len(self.source):
            return self.source[self.pos + 1]
        return None
