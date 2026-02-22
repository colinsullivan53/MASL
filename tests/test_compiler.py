import pytest
from src.lexer import Lexer
from src.parser import Parser
from src.compiler import compile_match, InputFrame, Action, Barrier, CompilerError

GAME_HEADER = "Game { Stage FinalDestination Players { Static P1 Fox } Stocks 4 Time 8 }"

def compile_source(source: str) -> dict[int, list[Action | Barrier]]:
    tokens = Lexer(source).tokenize()
    ast = Parser(tokens).parse()
    return compile_match(ast)

def test_input_frame_defaults():
    frame = InputFrame()
    assert frame.buttons == frozenset()
    assert frame.main_stick == (0.0, 0.0)
    assert frame.c_stick == (0.0, 0.0)
    assert frame.l_trigger == 0.0
    assert frame.r_trigger == 0.0

def test_button_action():
    queues = compile_source(f"Match {{ {GAME_HEADER} Static test {{ P1 button(A) }} }}")
    items = queues[1]
    assert len(items) == 1
    assert isinstance(items[0], Action)
    assert len(items[0].frames) == 1
    assert "A" in items[0].frames[0].buttons

def test_stick_action():
    queues = compile_source(f"Match {{ {GAME_HEADER} Static test {{ P1 stick(0.5, -1.0) }} }}")
    items = queues[1]
    action = items[0]
    assert action.frames[0].main_stick == (0.5, -1.0)

def test_cstick_action():
    queues = compile_source(f"Match {{ {GAME_HEADER} Static test {{ P1 cstick(1.0, 0.0) }} }}")
    items = queues[1]
    assert items[0].frames[0].c_stick == (1.0, 0.0)

def test_trigger_analog():
    queues = compile_source(f"Match {{ {GAME_HEADER} Static test {{ P1 trigger(L, 0.4) }} }}")
    items = queues[1]
    assert items[0].frames[0].l_trigger == pytest.approx(0.4)

def test_trigger_right():
    queues = compile_source(f"Match {{ {GAME_HEADER} Static test {{ P1 trigger(R, 0.7) }} }}")
    items = queues[1]
    assert items[0].frames[0].r_trigger == pytest.approx(0.7)

def test_wait_fixed():
    queues = compile_source(f"Match {{ {GAME_HEADER} Static test {{ P1 button(A) :: wait 3 }} }}")
    items = queues[1]
    assert isinstance(items[0], Action)  # button press
    assert isinstance(items[1], Action)  # wait (3 neutral frames)
    assert len(items[1].frames) == 3
    assert all(f == InputFrame() for f in items[1].frames)

def test_wait_named_becomes_barrier():
    queues = compile_source(f"Match {{ {GAME_HEADER} Static test {{ P1 button(A) :: wait act }} }}")
    items = queues[1]
    assert isinstance(items[0], Action)
    assert isinstance(items[1], Barrier)
    assert items[1].condition == "act"

def test_wait_ground_barrier():
    queues = compile_source(f"Match {{ {GAME_HEADER} Static test {{ P1 button(A) :: wait ground }} }}")
    items = queues[1]
    assert isinstance(items[1], Barrier)
    assert items[1].condition == "ground"

def test_wait_apex_barrier():
    queues = compile_source(f"Match {{ {GAME_HEADER} Static test {{ P1 button(A) :: wait apex }} }}")
    items = queues[1]
    assert isinstance(items[1], Barrier)
    assert items[1].condition == "apex"

def test_hold_baked_into_action():
    queues = compile_source(f"Match {{ {GAME_HEADER} Static test {{ P1 button(A) :: hold 3 }} }}")
    items = queues[1]
    assert len(items) == 1
    action = items[0]
    assert len(action.frames) == 4  # 1 original + 3 hold
    assert all("A" in f.buttons for f in action.frames)

def test_hold_with_layering():
    queues = compile_source(f"Match {{ {GAME_HEADER} Static test {{ P1 button(A) :: hold 5 :: stick(1.0, 0.0) }} }}")
    items = queues[1]
    action = items[0]
    # Frame 0: button A only
    assert "A" in action.frames[0].buttons
    assert action.frames[0].main_stick == (0.0, 0.0)
    # Frame 1+: button A + stick (layered on hold)
    assert "A" in action.frames[1].buttons
    assert action.frames[1].main_stick == (1.0, 0.0)

def test_def_resolution():
    queues = compile_source(f"""
    Match {{
        {GAME_HEADER}
        Def jab() {{ button(A) }}
        Static test {{ P1 jab :: wait 14 }}
    }}
    """)
    items = queues[1]
    assert isinstance(items[0], Action)
    assert "A" in items[0].frames[0].buttons

def test_def_arity_overload():
    queues = compile_source(f"""
    Match {{
        {GAME_HEADER}
        Def foo() {{ button(A) }}
        Def foo(x) {{ button(B) }}
        Static test {{ P1 foo :: wait 1 :: foo(1) }}
    }}
    """)
    items = queues[1]
    assert "A" in items[0].frames[0].buttons
    b_action = [i for i in items if isinstance(i, Action) and any("B" in f.buttons for f in i.frames)]
    assert len(b_action) == 1

def test_def_with_params():
    queues = compile_source(f"""
    Match {{
        {GAME_HEADER}
        Def press(btn) {{ button(btn) }}
        Static test {{ P1 press(A) }}
    }}
    """)
    items = queues[1]
    assert "A" in items[0].frames[0].buttons

def test_if_branching():
    queues = compile_source(f"""
    Match {{
        {GAME_HEADER}
        Def test(dir) {{
            if (dir == R) {{ stick(1.0, 0.0) }}
            else {{ stick(-1.0, 0.0) }}
        }}
        Static test {{ P1 test(R) }}
    }}
    """)
    items = queues[1]
    assert items[0].frames[0].main_stick == (1.0, 0.0)

def test_if_false_branch():
    queues = compile_source(f"""
    Match {{
        {GAME_HEADER}
        Def test(dir) {{
            if (dir == R) {{ stick(1.0, 0.0) }}
            else {{ stick(-1.0, 0.0) }}
        }}
        Static test {{ P1 test(L) }}
    }}
    """)
    items = queues[1]
    assert items[0].frames[0].main_stick == (-1.0, 0.0)

def test_while_loop():
    queues = compile_source(f"""
    Match {{
        {GAME_HEADER}
        Static test {{
            let i = 0
            while (i < 3) {{
                P1 button(A) :: wait 1
                i = i + 1
            }}
        }}
    }}
    """)
    items = queues[1]
    actions = [i for i in items if isinstance(i, Action)]
    assert len(actions) == 6  # 3 button + 3 wait

def test_let_variable():
    queues = compile_source(f"""
    Match {{
        {GAME_HEADER}
        let frames = 5
        Static test {{ P1 button(A) :: wait frames }}
    }}
    """)
    items = queues[1]
    wait_action = items[1]
    assert len(wait_action.frames) == 5

def test_arithmetic_expressions():
    queues = compile_source(f"""
    Match {{
        {GAME_HEADER}
        let x = 2 + 3
        Static test {{ P1 button(A) :: wait x }}
    }}
    """)
    items = queues[1]
    assert len(items[1].frames) == 5

def test_human_player_no_queue():
    queues = compile_source("""
    Match {
        Game { Stage FinalDestination Players { Static P1 Fox Human P3 } Stocks 4 Time 8 }
        Static test { P1 button(A) }
    }
    """)
    assert 1 in queues
    assert 3 not in queues

def test_multiple_players():
    queues = compile_source("""
    Match {
        Game { Stage FinalDestination Players { Static P1 Fox Static P2 Falco } Stocks 4 Time 8 }
        Static test {
            P1 button(A)
            P2 button(B)
        }
    }
    """)
    assert 1 in queues
    assert 2 in queues
    assert "A" in queues[1][0].frames[0].buttons
    assert "B" in queues[2][0].frames[0].buttons

def test_chain_button_wait_button():
    queues = compile_source(f"Match {{ {GAME_HEADER} Static test {{ P1 button(A) :: wait 5 :: button(B) }} }}")
    items = queues[1]
    assert isinstance(items[0], Action)  # button A
    assert isinstance(items[1], Action)  # wait 5
    assert isinstance(items[2], Action)  # button B
    assert "A" in items[0].frames[0].buttons
    assert len(items[1].frames) == 5
    assert "B" in items[2].frames[0].buttons

def test_nested_def_calls():
    queues = compile_source(f"""
    Match {{
        {GAME_HEADER}
        Def inner() {{ button(A) }}
        Def outer() {{ inner :: wait 5 }}
        Static test {{ P1 outer }}
    }}
    """)
    items = queues[1]
    assert "A" in items[0].frames[0].buttons
    assert len(items[1].frames) == 5
