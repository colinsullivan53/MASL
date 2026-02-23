"""MASL Parser - Builds AST from tokens."""

from __future__ import annotations

import glob as glob_mod
import os
from dataclasses import dataclass, field
from typing import Any

from src.lexer import Lexer, Token, TokenType
from src.source_map import format_error_context


# --- AST Nodes ---

@dataclass
class Node:
    pass

@dataclass
class Expression(Node):
    pass

@dataclass
class IntegerLiteral(Expression):
    value: int

@dataclass
class FloatLiteral(Expression):
    value: float

@dataclass
class StringLiteral(Expression):
    value: str

@dataclass
class BoolLiteral(Expression):
    value: bool

@dataclass
class Identifier(Expression):
    name: str

@dataclass
class BinaryOp(Expression):
    left: Expression
    op: str
    right: Expression

@dataclass
class UnaryOp(Expression):
    op: str
    operand: Expression

@dataclass
class CallExpr(Expression):
    name: str
    args: list[Expression]

# --- Chain Segments ---

@dataclass
class ChainSegment(Node):
    pass

@dataclass
class ActionSegment(ChainSegment):
    name: str
    args: list[Expression]

@dataclass
class WaitSegment(ChainSegment):
    condition: Expression

@dataclass
class HoldSegment(ChainSegment):
    duration: Expression

# --- Statements ---

@dataclass
class Statement(Node):
    pass

@dataclass
class LetStatement(Statement):
    name: str
    value: Expression

@dataclass
class AssignStatement(Statement):
    name: str
    value: Expression

@dataclass
class PlayerAction(Statement):
    player: str  # "P1"-"P4" or "implicit"
    chain: list[ChainSegment]

@dataclass
class IfStatement(Statement):
    condition: Expression
    then_body: list[Statement]
    else_body: list[Statement] | None

@dataclass
class WhileStatement(Statement):
    condition: Expression
    body: list[Statement]

@dataclass
class CallStatement(Statement):
    name: str
    args: list[Expression]

# --- Top Level ---

@dataclass
class Def(Node):
    name: str
    params: list[str]
    body: list[Statement]

@dataclass
class PlayerConfig(Node):
    port: str
    character: str | None
    player_type: str  # "Static" or "Human"

@dataclass
class Game(Node):
    stage: str
    players: list[PlayerConfig] = field(default_factory=list)

@dataclass
class StaticBlock(Node):
    name: str
    statements: list[Statement] = field(default_factory=list)

@dataclass
class Match(Node):
    game: Game | None = None
    includes: list[str] = field(default_factory=list)
    defs: list[Def] = field(default_factory=list)
    variables: list[LetStatement] = field(default_factory=list)
    static_blocks: list[StaticBlock] = field(default_factory=list)


# --- Parser Error ---

class ParseError(Exception):
    """Error during parsing."""

    def __init__(self, message: str, token: Token | None = None):
        self.token = token

        if token is not None and token.source_location is not None:
            error_msg = format_error_context(token.source_location, message)
        elif token is not None:
            error_msg = f"{message} at line {token.line}, column {token.column}"
        else:
            error_msg = message

        super().__init__(error_msg)


# --- Parser ---

class Parser:
    """Recursive descent parser for MASL."""

    def __init__(self, tokens: list[Token], base_path: str | None = None,
                 _included: set | None = None, _stack: set | None = None):
        self.tokens = tokens
        self.pos = 0
        self.base_path = base_path
        self._included = _included if _included is not None else set()
        self._stack = _stack if _stack is not None else set()

    def parse(self) -> Match:
        """Parse tokens into an AST."""
        result = Match()

        # Handle top-level includes and defs 
        while not self._check(TokenType.EOF):
            if self._check(TokenType.MATCH):
                match = self._parse_match()
                if match.game is not None:
                    if result.game is not None:
                        raise ParseError(
                            "Multiple Game blocks found - only one allowed",
                            self._current(),
                        )
                    result.game = match.game

                result.defs.extend(match.defs)
                result.variables.extend(match.variables)
                result.static_blocks.extend(match.static_blocks)
                result.includes.extend(match.includes)
            elif self._check(TokenType.DEF):
                result.defs.append(self._parse_def())
            elif self._check(TokenType.LET):
                result.variables.append(self._parse_let())
            elif self._check(TokenType.INCLUDE):
                defs, lets = self._handle_include()
                result.defs.extend(defs)
                result.variables.extend(lets)
            else:
                raise ParseError(
                    f"Unexpected token at top level: {self._current().type.name}",
                    self._current(),
                )

        # Validate: each static player only appear in one Static block
        self._validate_static_player_uniqueness(result)

        return result

    def _validate_static_player_uniqueness(self, ast: Match) -> None:
        """Validate that each static player only appears in one Static block."""
        if ast.game is None:
            return

        static_players = {
            p.port for p in ast.game.players if p.player_type == "Static"
        }

        if not static_players:
            return

        player_to_block: dict[str, str] = {}

        for static in ast.static_blocks:
            players_in_block = self._extract_players_from_statements(static.statements)

            for player in players_in_block:
                if player in static_players:
                    if player in player_to_block:
                        raise ParseError(
                            f"Static player '{player}' appears in multiple Static blocks "
                            f"('{player_to_block[player]}' and '{static.name}'). "
                            f"Each static player can only appear in one Static block.",
                            self._current(),
                        )
                    player_to_block[player] = static.name

    def _extract_players_from_statements(self, statements: list) -> set[str]:
        """Extract all player references from a list of statements."""
        players = set()

        for stmt in statements:
            if isinstance(stmt, PlayerAction):
                players.add(stmt.player)
            elif isinstance(stmt, IfStatement):
                players.update(self._extract_players_from_statements(stmt.then_body))
                if stmt.else_body:
                    players.update(self._extract_players_from_statements(stmt.else_body))
            elif isinstance(stmt, WhileStatement):
                players.update(self._extract_players_from_statements(stmt.body))

        return players

    def _parse_match(self) -> Match:
        """Parse a Match block."""
        self._expect(TokenType.MATCH)
        self._expect(TokenType.LBRACE)

        match = Match()

        while not self._check(TokenType.RBRACE):
            if self._check(TokenType.GAME):
                match.game = self._parse_game()
            elif self._check(TokenType.DEF):
                match.defs.append(self._parse_def())
            elif self._check(TokenType.LET):
                match.variables.append(self._parse_let())
            elif self._check(TokenType.STATIC):
                match.static_blocks.append(self._parse_static_block())
            elif self._check(TokenType.INCLUDE):
                defs, lets = self._handle_include()
                match.defs.extend(defs)
                match.variables.extend(lets)
            else:
                raise ParseError(
                    f"Unexpected token in Match: {self._current().type.name}",
                    self._current(),
                )

        self._expect(TokenType.RBRACE)
        return match

    def _handle_include(self) -> tuple[list[Def], list[LetStatement]]:
        """Handle #INCLUDE directive. Returns (defs, lets) extracted."""
        self._expect(TokenType.INCLUDE)
        path_token = self._expect(TokenType.STRING)
        raw_path = path_token.value

        if not os.path.isabs(raw_path) and self.base_path:
            raw_path = os.path.join(self.base_path, raw_path)

        files = sorted(glob_mod.glob(raw_path))
        if not files and not glob_mod.has_magic(raw_path):
            files = [raw_path]

        all_defs: list[Def] = []
        all_lets: list[LetStatement] = []

        for file_path in files:
            resolved = os.path.realpath(file_path)

            if resolved in self._stack:
                raise ParseError(
                    f"Circular include detected: {file_path}",
                    path_token,
                )

            if resolved in self._included:
                continue

            self._included.add(resolved)
            self._stack.add(resolved)

            try:
                with open(file_path, "r") as f:
                    source = f.read()

                tokens = Lexer(source).tokenize()
                sub_parser = Parser(
                    tokens,
                    base_path=os.path.dirname(os.path.realpath(file_path)),
                    _included=self._included,
                    _stack=self._stack,
                )
                sub_result = sub_parser.parse()

                all_defs.extend(sub_result.defs)
                all_lets.extend(sub_result.variables)
            finally:
                self._stack.discard(resolved)

        return all_defs, all_lets

    def _parse_game(self) -> Game:
        """Parse a Game block."""
        self._expect(TokenType.GAME)
        self._expect(TokenType.LBRACE)

        game = Game(stage="")

        while not self._check(TokenType.RBRACE):
            if self._check(TokenType.STAGE):
                self._advance()
                game.stage = self._expect(TokenType.IDENTIFIER).value
            elif self._check(TokenType.PLAYERS):
                game.players = self._parse_players()
            else:
                raise ParseError(
                    f"Unexpected token in Game: {self._current().type.name}",
                    self._current(),
                )

        self._expect(TokenType.RBRACE)
        return game

    def _parse_players(self) -> list[PlayerConfig]:
        """Parse Players block."""
        self._expect(TokenType.PLAYERS)
        self._expect(TokenType.LBRACE)

        players = []

        while not self._check(TokenType.RBRACE):
            if self._check(TokenType.STATIC):
                self._advance()
                port = self._expect(TokenType.PLAYER).value
                character = self._expect(TokenType.IDENTIFIER).value
                players.append(
                    PlayerConfig(port=port, character=character, player_type="Static")
                )
            elif self._check(TokenType.HUMAN):
                self._advance()
                port = self._expect(TokenType.PLAYER).value
                players.append(
                    PlayerConfig(port=port, character=None, player_type="Human")
                )
            else:
                raise ParseError("Expected Static or Human", self._current())

        self._expect(TokenType.RBRACE)
        return players

    def _parse_def(self) -> Def:
        """Parse a Def definition."""
        self._expect(TokenType.DEF)
        name = self._expect(TokenType.IDENTIFIER).value
        params = self._parse_params()
        self._expect(TokenType.LBRACE)
        body = self._parse_statement_list()
        self._expect(TokenType.RBRACE)

        return Def(name=name, params=params, body=body)

    def _parse_let(self) -> LetStatement:
        """Parse let statement."""
        self._expect(TokenType.LET)
        name = self._expect(TokenType.IDENTIFIER).value
        self._expect(TokenType.ASSIGN)
        value = self._parse_expression()

        return LetStatement(name=name, value=value)

    def _parse_static_block(self) -> StaticBlock:
        """Parse Static block."""
        self._expect(TokenType.STATIC)
        name = self._expect(TokenType.IDENTIFIER).value
        self._expect(TokenType.LBRACE)
        statements = self._parse_statement_list()
        self._expect(TokenType.RBRACE)

        return StaticBlock(name=name, statements=statements)

    def _parse_params(self) -> list[str]:
        """Parse parameter list: (a, b, c)."""
        self._expect(TokenType.LPAREN)
        params = []

        if not self._check(TokenType.RPAREN):
            params.append(self._expect(TokenType.IDENTIFIER).value)
            while self._check(TokenType.COMMA):
                self._advance()
                params.append(self._expect(TokenType.IDENTIFIER).value)

        self._expect(TokenType.RPAREN)
        return params

    def _parse_statement_list(self) -> list[Statement]:
        """Parse a list of statements until RBRACE."""
        statements = []

        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            stmt = self._parse_statement()
            if stmt:
                statements.append(stmt)

        return statements

    def _parse_statement(self) -> Statement | None:
        """Parse a single statement."""
        if self._check(TokenType.LET):
            return self._parse_let()
        if self._check(TokenType.IF):
            return self._parse_if()
        if self._check(TokenType.WHILE):
            return self._parse_while()
        if self._check(TokenType.PLAYER):
            return self._parse_player_action()
        if self._check(TokenType.WAIT) or self._check(TokenType.HOLD):
            return self._parse_standalone_chain_segment()
        if self._check(TokenType.IDENTIFIER):
            return self._parse_identifier_statement()

        return None

    def _parse_standalone_chain_segment(self) -> PlayerAction:
        """Parse standalone wait/hold/action as implicit player action."""
        segment = self._parse_chain_segment()
        chain = [segment]
        while self._check(TokenType.CHAIN):
            self._advance()
            chain.append(self._parse_chain_segment())
        return PlayerAction(player="implicit", chain=chain)

    def _parse_if(self) -> IfStatement:
        """Parse if statement."""
        self._expect(TokenType.IF)
        self._expect(TokenType.LPAREN)
        condition = self._parse_expression()
        self._expect(TokenType.RPAREN)
        self._expect(TokenType.LBRACE)
        then_body = self._parse_statement_list()
        self._expect(TokenType.RBRACE)

        else_body: list[Statement] | None = None
        if self._check(TokenType.ELSE):
            self._advance()
            if self._check(TokenType.IF):
                else_body = [self._parse_if()]
            else:
                self._expect(TokenType.LBRACE)
                else_body = self._parse_statement_list()
                self._expect(TokenType.RBRACE)

        return IfStatement(
            condition=condition, then_body=then_body, else_body=else_body
        )

    def _parse_while(self) -> WhileStatement:
        """Parse while statement."""
        self._expect(TokenType.WHILE)
        self._expect(TokenType.LPAREN)
        condition = self._parse_expression()
        self._expect(TokenType.RPAREN)
        self._expect(TokenType.LBRACE)
        body = self._parse_statement_list()
        self._expect(TokenType.RBRACE)

        return WhileStatement(condition=condition, body=body)

    def _parse_player_action(self) -> PlayerAction:
        """Parse player action with chain."""
        player = self._advance().value
        chain = self._parse_chain()
        return PlayerAction(player=player, chain=chain)

    def _parse_chain(self) -> list[ChainSegment]:
        """Parse chain of segments: action :: wait :: hold."""
        segments = [self._parse_chain_segment()]

        while self._check(TokenType.CHAIN):
            self._advance()
            segments.append(self._parse_chain_segment())

        return segments

    def _parse_chain_segment(self) -> ChainSegment:
        """Parse a single chain segment."""
        if self._check(TokenType.WAIT):
            self._advance()
            condition = self._parse_expression()
            return WaitSegment(condition=condition)

        if self._check(TokenType.HOLD):
            self._advance()
            duration = self._parse_expression()
            return HoldSegment(duration=duration)

        name = self._expect(TokenType.IDENTIFIER).value
        args: list[Expression] = []

        if self._check(TokenType.LPAREN):
            self._advance()
            if not self._check(TokenType.RPAREN):
                args.append(self._parse_expression())
                while self._check(TokenType.COMMA):
                    self._advance()
                    args.append(self._parse_expression())
            self._expect(TokenType.RPAREN)

        return ActionSegment(name=name, args=args)

    def _parse_identifier_statement(self) -> Statement:
        """Parse statement starting with identifier."""
        name = self._advance().value

        if self._check(TokenType.ASSIGN):
            self._advance()
            value = self._parse_expression()
            return AssignStatement(name=name, value=value)

        args: list[Expression] = []
        if self._check(TokenType.LPAREN):
            self._advance()
            if not self._check(TokenType.RPAREN):
                args.append(self._parse_expression())
                while self._check(TokenType.COMMA):
                    self._advance()
                    args.append(self._parse_expression())
            self._expect(TokenType.RPAREN)

        if self._check(TokenType.CHAIN):
            first_segment = ActionSegment(name=name, args=args)
            chain: list[ChainSegment] = [first_segment]
            while self._check(TokenType.CHAIN):
                self._advance()
                chain.append(self._parse_chain_segment())
            return PlayerAction(player="implicit", chain=chain)

        return CallStatement(name=name, args=args)

    # --- Expression parsing (precedence climbing) ---

    def _parse_expression(self) -> Expression:
        """Parse an expression."""
        return self._parse_or()

    def _parse_or(self) -> Expression:
        """Parse || expression."""
        left = self._parse_and()

        while self._check(TokenType.OR):
            self._advance()
            right = self._parse_and()
            left = BinaryOp(left=left, op="||", right=right)

        return left

    def _parse_and(self) -> Expression:
        """Parse && expression."""
        left = self._parse_equality()

        while self._check(TokenType.AND):
            self._advance()
            right = self._parse_equality()
            left = BinaryOp(left=left, op="&&", right=right)

        return left

    def _parse_equality(self) -> Expression:
        """Parse == and != expressions."""
        left = self._parse_comparison()

        while self._check(TokenType.EQ) or self._check(TokenType.NEQ):
            op = "==" if self._check(TokenType.EQ) else "!="
            self._advance()
            right = self._parse_comparison()
            left = BinaryOp(left=left, op=op, right=right)

        return left

    def _parse_comparison(self) -> Expression:
        """Parse <, >, <=, >= expressions."""
        left = self._parse_additive()

        while self._check(TokenType.LT) or self._check(TokenType.GT) or \
              self._check(TokenType.LTE) or self._check(TokenType.GTE):
            if self._check(TokenType.LT):
                op = "<"
            elif self._check(TokenType.GT):
                op = ">"
            elif self._check(TokenType.LTE):
                op = "<="
            else:
                op = ">="
            self._advance()
            right = self._parse_additive()
            left = BinaryOp(left=left, op=op, right=right)

        return left

    def _parse_additive(self) -> Expression:
        """Parse + and - expressions."""
        left = self._parse_multiplicative()

        while self._check(TokenType.PLUS) or self._check(TokenType.MINUS):
            op = "+" if self._check(TokenType.PLUS) else "-"
            self._advance()
            right = self._parse_multiplicative()
            left = BinaryOp(left=left, op=op, right=right)

        return left

    def _parse_multiplicative(self) -> Expression:
        """Parse *, /, % expressions."""
        left = self._parse_unary()

        while self._check(TokenType.STAR) or self._check(TokenType.SLASH) or \
              self._check(TokenType.PERCENT):
            if self._check(TokenType.STAR):
                op = "*"
            elif self._check(TokenType.SLASH):
                op = "/"
            else:
                op = "%"
            self._advance()
            right = self._parse_unary()
            left = BinaryOp(left=left, op=op, right=right)

        return left

    def _parse_unary(self) -> Expression:
        """Parse unary expressions: !, -."""
        if self._check(TokenType.NOT):
            self._advance()
            return UnaryOp(op="!", operand=self._parse_unary())

        if self._check(TokenType.MINUS):
            self._advance()
            return UnaryOp(op="-", operand=self._parse_unary())

        return self._parse_primary()

    def _parse_primary(self) -> Expression:
        """Parse primary expressions."""
        # Literals
        if self._check(TokenType.INTEGER):
            return IntegerLiteral(value=int(self._advance().value))

        if self._check(TokenType.FLOAT):
            return FloatLiteral(value=float(self._advance().value))

        if self._check(TokenType.STRING):
            return StringLiteral(value=self._advance().value)

        if self._check(TokenType.TRUE):
            self._advance()
            return BoolLiteral(value=True)

        if self._check(TokenType.FALSE):
            self._advance()
            return BoolLiteral(value=False)

        # Parenthesis expression
        if self._check(TokenType.LPAREN):
            self._advance()
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN)
            return expr

        # Identifier (variable or function)
        if self._check(TokenType.IDENTIFIER):
            name = self._advance().value
            expr: Expression = Identifier(name=name)

            # Check for function
            if self._check(TokenType.LPAREN):
                self._advance()
                call_args: list[Expression] = []
                if not self._check(TokenType.RPAREN):
                    call_args.append(self._parse_expression())
                    while self._check(TokenType.COMMA):
                        self._advance()
                        call_args.append(self._parse_expression())
                self._expect(TokenType.RPAREN)
                expr = CallExpr(name=name, args=call_args)

            return expr

        # Player port as expression
        if self._check(TokenType.PLAYER):
            return Identifier(name=self._advance().value)

        raise ParseError(
            f"Unexpected token: {self._current().type.name}",
            self._current(),
        )

    # --- Helper methods ---

    def _current(self) -> Token:
        """Get current token."""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]  # EOF

    def _check(self, token_type: TokenType) -> bool:
        """Check if current token is of given type."""
        return self._current().type == token_type

    def _advance(self) -> Token:
        """Advance and return current token."""
        token = self._current()
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return token

    def _expect(self, token_type: TokenType) -> Token:
        """Expect current token to be of given type, advance."""
        if not self._check(token_type):
            raise ParseError(
                f"Expected {token_type.name}, got {self._current().type.name}",
                self._current(),
            )
        return self._advance()