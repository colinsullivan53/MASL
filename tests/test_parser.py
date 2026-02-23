"""Tests for MASL Parser."""

import pytest
from src.lexer import Lexer
from src.parser import (
    Parser, Match, StaticBlock, PlayerAction, Def, LetStatement,
    IfStatement, WhileStatement, ParseError,
    ActionSegment, WaitSegment, HoldSegment, Identifier,
    BinaryOp, IntegerLiteral, CallStatement
)

def parse(source: str, base_path: str | None = None) -> Match:
    tokens = Lexer(source).tokenize()
    return Parser(tokens, base_path=base_path).parse()

def test_minimal_match():
    ast = parse("Match { Game { Stage FinalDestination Players { Static P1 Fox } } }")
    assert ast.game.stage == "FinalDestination"
    assert len(ast.game.players) == 1
    assert ast.game.players[0].port == "P1"
    assert ast.game.players[0].character == "Fox"
    assert ast.game.players[0].player_type == "Static"

def test_human_player():
    ast = parse("Match { Game { Stage FinalDestination Players { Static P1 Fox Human P3 } } }")
    human = [p for p in ast.game.players if p.player_type == "Human"]
    assert len(human) == 1
    assert human[0].port == "P3"
    assert human[0].character is None

def test_static_block():
    ast = parse("""
    Match {
        Game { Stage FinalDestination Players { Static P1 Fox } }
        Static test {
            P1 attack :: wait 14
            P1 button(A) :: hold 3
        }
    }
    """)
    assert len(ast.static_blocks) == 1
    block = ast.static_blocks[0]
    assert block.name == "test"
    assert len(block.statements) == 2

def test_chain_parsing():
    ast = parse("""
    Match {
        Game { Stage FinalDestination Players { Static P1 Fox } }
        Static test {
            P1 attack :: wait 14 :: hold 3
        }
    }
    """)
    stmt = ast.static_blocks[0].statements[0]
    assert isinstance(stmt, PlayerAction)
    assert len(stmt.chain) == 3
    assert isinstance(stmt.chain[0], ActionSegment)
    assert isinstance(stmt.chain[1], WaitSegment)
    assert isinstance(stmt.chain[2], HoldSegment)

def test_def_with_params():
    ast = parse("""
    Match {
        Game { Stage FinalDestination Players { Static P1 Fox } }
        Def attack(dir) {
            button(A)
        }
    }
    """)
    assert len(ast.defs) == 1
    assert ast.defs[0].name == "attack"
    assert ast.defs[0].params == ["dir"]

def test_arity_overloading():
    ast = parse("""
    Match {
        Game { Stage FinalDestination Players { Static P1 Fox } }
        Def attack() { button(A) }
        Def attack(dir) { button(A) }
    }
    """)
    attacks = [d for d in ast.defs if d.name == "attack"]
    assert len(attacks) == 2
    assert len(attacks[0].params) == 0
    assert len(attacks[1].params) == 1

def test_if_else():
    ast = parse("""
    Match {
        Game { Stage FinalDestination Players { Static P1 Fox } }
        Def test(dir) {
            if (dir == L) { button(A) } else { button(B) }
        }
    }
    """)
    body = ast.defs[0].body
    assert len(body) == 1
    assert isinstance(body[0], IfStatement)
    assert body[0].else_body is not None

def test_while_loop():
    ast = parse("""
    Match {
        Game { Stage FinalDestination Players { Static P1 Fox } }
        Def test() {
            let i = 0
            while (i < 3) {
                button(A)
                i = i + 1
            }
        }
    }
    """)
    body = ast.defs[0].body
    assert isinstance(body[1], WhileStatement)

def test_let_statement():
    ast = parse("""
    Match {
        Game { Stage FinalDestination Players { Static P1 Fox } }
        let x = 5
    }
    """)
    assert len(ast.variables) == 1
    assert ast.variables[0].name == "x"

def test_expressions():
    ast = parse("""
    Match {
        Game { Stage FinalDestination Players { Static P1 Fox } }
        Def test() {
            if (3 + 4 * 2 > 10 && true) { button(A) }
        }
    }
    """)
    assert ast is not None

def test_duplicate_static_player_error():
    with pytest.raises(ParseError):
        parse("""
        Match {
            Game { Stage FinalDestination Players { Static P1 Fox } }
            Static a { P1 wait 10 }
            Static b { P1 wait 10 }
        }
        """)

def test_include_extracts_defs(tmp_path):
    lib = tmp_path / "lib.masl"
    lib.write_text('Def foo() { button(A) }')
    source = f"""
    Match {{
        #INCLUDE "{lib}"
        Game {{ Stage FinalDestination Players {{ Static P1 Fox }} }}
        Static test {{ P1 foo }}
    }}
    """
    ast = parse(source, base_path=str(tmp_path))
    assert len(ast.defs) == 1
    assert ast.defs[0].name == "foo"

def test_include_extracts_lets(tmp_path):
    lib = tmp_path / "lib.masl"
    lib.write_text('let fox_js = 2\nDef wd(dir) { button(A) }')
    source = f"""
    Match {{
        #INCLUDE "{lib}"
        Game {{ Stage FinalDestination Players {{ Static P1 Fox }} }}
    }}
    """
    ast = parse(source, base_path=str(tmp_path))
    assert len(ast.variables) == 1
    assert ast.variables[0].name == "fox_js"
    assert len(ast.defs) == 1

def test_include_skips_match(tmp_path):
    lib = tmp_path / "lib.masl"
    lib.write_text("""
    Def foo() { button(A) }
    Match {
        Game { Stage Battlefield Players { Static P1 Marth } }
    }
    """)
    source = f"""
    Match {{
        #INCLUDE "{lib}"
        Game {{ Stage FinalDestination Players {{ Static P1 Fox }} }}
    }}
    """
    ast = parse(source, base_path=str(tmp_path))
    assert ast.game.stage == "FinalDestination"  # main file's game, not included
    assert len(ast.defs) == 1  # foo was imported

def test_include_diamond_dedup(tmp_path):
    shared = tmp_path / "shared.masl"
    shared.write_text('Def shared() { button(A) }')
    a = tmp_path / "a.masl"
    a.write_text(f'#INCLUDE "{shared}"\nDef a_func() {{ button(B) }}')
    b = tmp_path / "b.masl"
    b.write_text(f'#INCLUDE "{shared}"\nDef b_func() {{ button(B) }}')
    source = f"""
    Match {{
        #INCLUDE "{a}"
        #INCLUDE "{b}"
        Game {{ Stage FinalDestination Players {{ Static P1 Fox }} }}
    }}
    """
    ast = parse(source, base_path=str(tmp_path))
    shared_defs = [d for d in ast.defs if d.name == "shared"]
    assert len(shared_defs) == 1  # included only once

def test_include_circular_error(tmp_path):
    a = tmp_path / "a.masl"
    b = tmp_path / "b.masl"
    a.write_text(f'#INCLUDE "{b}"\nDef a_func() {{ button(A) }}')
    b.write_text(f'#INCLUDE "{a}"\nDef b_func() {{ button(B) }}')
    source = f"""
    Match {{
        #INCLUDE "{a}"
        Game {{ Stage FinalDestination Players {{ Static P1 Fox }} }}
    }}
    """
    with pytest.raises(ParseError, match="[Cc]ircular"):
        parse(source, base_path=str(tmp_path))

def test_include_glob(tmp_path):
    (tmp_path / "one.masl").write_text('Def one() { button(A) }')
    (tmp_path / "two.masl").write_text('Def two() { button(B) }')
    source = f"""
    Match {{
        #INCLUDE "{tmp_path}/*.masl"
        Game {{ Stage FinalDestination Players {{ Static P1 Fox }} }}
    }}
    """
    ast = parse(source, base_path=str(tmp_path))
    names = [d.name for d in ast.defs]
    assert "one" in names
    assert "two" in names

def test_standalone_wait():
    ast = parse("""
    Match {
        Game { Stage FinalDestination Players { Static P1 Fox } }
        Static test {
            P1 wait 60
        }
    }
    """)
    stmt = ast.static_blocks[0].statements[0]
    assert isinstance(stmt, PlayerAction)
    assert isinstance(stmt.chain[0], WaitSegment)

