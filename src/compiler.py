"""MASL Compiler - Transforms AST into per-player action queues (IR)."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.parser import (
    Match, Def, StaticBlock, PlayerAction, ActionSegment, WaitSegment, HoldSegment,
    LetStatement, AssignStatement, IfStatement, WhileStatement, ForStatement,
    CallStatement, Expression, IntegerLiteral, FloatLiteral, StringLiteral,
    BoolLiteral, Identifier, BinaryOp, UnaryOp, CallExpr,
)
from src.source_map import SourceLocation


MAX_ITERATIONS = 10000  # Safeguard against infinite loops in compilation

# IR Types 

@dataclass(frozen=True)
class InputFrame:
    buttons: frozenset[str] = frozenset()
    main_stick: tuple[float, float] = (0.0, 0.0)
    c_stick: tuple[float, float] = (0.0, 0.0)
    l_trigger: float = 0.0
    r_trigger: float = 0.0


@dataclass
class Action:
    frames: list[InputFrame]
    source: SourceLocation | None = None


@dataclass
class Barrier:
    condition: str  # "act", "ground", "apex"
    _seen_exit: bool = field(default=False, repr=False)
    source: SourceLocation | None = None


class CompilerError(Exception):
    pass


# Helpers

def _merge_frames(base: InputFrame, overlay: InputFrame) -> InputFrame:
    """Merge overlay onto base. Union buttons, overwrite non-default sticks/triggers."""
    buttons = base.buttons | overlay.buttons
    main_stick = overlay.main_stick if overlay.main_stick != (0.0, 0.0) else base.main_stick
    c_stick = overlay.c_stick if overlay.c_stick != (0.0, 0.0) else base.c_stick
    l_trigger = overlay.l_trigger if overlay.l_trigger != 0.0 else base.l_trigger
    r_trigger = overlay.r_trigger if overlay.r_trigger != 0.0 else base.r_trigger
    return InputFrame(
        buttons=buttons,
        main_stick=main_stick,
        c_stick=c_stick,
        l_trigger=l_trigger,
        r_trigger=r_trigger,
    )


def _port_number(player: str) -> int:
    """Extract port number from player string like 'P1'."""
    return int(player[1:])


# Builtins

BARRIER_CONDITIONS = {"act", "ground", "apex"}

def _builtin_button(args: list, _vars: dict) -> list[Action | Barrier]:
    name = args[0]
    frame = InputFrame(buttons=frozenset([str(name)]))
    return [Action(frames=[frame])]


def _builtin_stick(args: list, _vars: dict) -> list[Action | Barrier]:
    x, y = float(args[0]), float(args[1])
    frame = InputFrame(main_stick=(x, y))
    return [Action(frames=[frame])]


def _builtin_cstick(args: list, _vars: dict) -> list[Action | Barrier]:
    x, y = float(args[0]), float(args[1])
    frame = InputFrame(c_stick=(x, y))
    return [Action(frames=[frame])]


def _builtin_trigger(args: list, _vars: dict) -> list[Action | Barrier]:
    side = str(args[0])
    amount = float(args[1])
    if side == "L":
        frame = InputFrame(l_trigger=amount)
    else:
        frame = InputFrame(r_trigger=amount)
    return [Action(frames=[frame])]


def _builtin_turn(args: list, _vars: dict) -> list[Action | Barrier]:
    frame = InputFrame()
    return [Action(frames=[frame])]


BUILTINS = {
    ("button", 1): _builtin_button,
    ("stick", 2): _builtin_stick,
    ("cstick", 2): _builtin_cstick,
    ("trigger", 2): _builtin_trigger,
    ("turn", 1): _builtin_turn,
}


# Compiler 

class _CompilerContext:
    """Holds state during compilation."""

    def __init__(self, match: Match):
        self.match = match
        self.defs: dict[tuple[str, int], Def] = {}
        self.queues: dict[int, list[Action | Barrier]] = {}
        self.global_vars: dict[str, object] = {}
 
        for d in match.defs:
            self.defs[(d.name, len(d.params))] = d

        self.static_ports: set[int] = set()
        if match.game:
            for p in match.game.players:
                if p.player_type == "Static":
                    port = _port_number(p.port)
                    self.static_ports.add(port)
                    self.queues[port] = []

    def eval_expr(self, expr: Expression, variables: dict[str, object]) -> object:
        if isinstance(expr, IntegerLiteral):
            return expr.value
        if isinstance(expr, FloatLiteral):
            return expr.value
        if isinstance(expr, StringLiteral):
            return expr.value
        if isinstance(expr, BoolLiteral):
            return expr.value
        if isinstance(expr, Identifier):
            if expr.name in variables:
                return variables[expr.name]
            if expr.name in self.global_vars:
                return self.global_vars[expr.name] 
            return expr.name
        if isinstance(expr, BinaryOp):
            left = self.eval_expr(expr.left, variables)
            right = self.eval_expr(expr.right, variables)
            return self._apply_binop(expr.op, left, right)
        if isinstance(expr, UnaryOp):
            operand = self.eval_expr(expr.operand, variables)
            if expr.op == "!":
                return not operand
            if expr.op == "-":
                return -operand
        if isinstance(expr, CallExpr):
            args = [self.eval_expr(a, variables) for a in expr.args]
            key = (expr.name, len(args))
            if key in self.defs:
                return self._exec_def(self.defs[key], args, variables, None)
            raise CompilerError(f"Unknown function: {expr.name}/{len(args)}")
        raise CompilerError(f"Cannot evaluate expression: {type(expr).__name__}")

    def _apply_binop(self, op: str, left, right):
        if op == "+": return left + right
        if op == "-": return left - right
        if op == "*": return left * right
        if op == "/": return left / right
        if op == "%": return left % right
        if op == "==": return left == right
        if op == "!=": return left != right
        if op == "<": return left < right
        if op == ">": return left > right
        if op == "<=": return left <= right
        if op == ">=": return left >= right
        if op == "&&": return left and right
        if op == "||": return left or right
        raise CompilerError(f"Unknown operator: {op}")

    def compile_chain(self, chain: list, variables: dict[str, object], port: int) -> list[Action | Barrier]:
        """Compile a chain of segments into actions/barriers."""
        output: list[Action | Barrier] = []
        hold_active = False

        for segment in chain:
            if isinstance(segment, ActionSegment):
                items = self._resolve_action(segment, variables, port)
                if hold_active and items and output: 
                    last_action = output[-1]
                    if isinstance(last_action, Action) and items and isinstance(items[0], Action):
                        overlay_frame = items[0].frames[0] if items[0].frames else InputFrame() 
                        new_frames = [last_action.frames[0]]
                        for f in last_action.frames[1:]:
                            new_frames.append(_merge_frames(f, overlay_frame))
                        output[-1] = Action(frames=new_frames, source=last_action.source)
                        hold_active = False
                        continue
                hold_active = False
                output.extend(items)

            elif isinstance(segment, WaitSegment):
                hold_active = False
                val = self.eval_expr(segment.condition, variables)
                if isinstance(val, int):
                    frames = [InputFrame() for _ in range(val)]
                    output.append(Action(frames=frames))
                elif isinstance(val, str) and val in BARRIER_CONDITIONS:
                    output.append(Barrier(condition=val))
                else:
                    raise CompilerError(f"Invalid wait condition: {val}")

            elif isinstance(segment, HoldSegment):
                duration = self.eval_expr(segment.duration, variables)
                if not isinstance(duration, int):
                    raise CompilerError(f"Hold duration must be integer, got {type(duration)}")
                if output and isinstance(output[-1], Action) and output[-1].frames:
                    last_frame = output[-1].frames[-1]
                    output[-1].frames.extend([last_frame] * duration)
                hold_active = True

        return output

    def _resolve_action(self, segment: ActionSegment, variables: dict[str, object], port: int) -> list[Action | Barrier]:
        """Resolve an ActionSegment as a def call or builtin."""
        name = segment.name
        arity = len(segment.args)
        key = (name, arity)
 
        eval_args = [self.eval_expr(a, variables) for a in segment.args] 
        if key in self.defs:
            return self._exec_def(self.defs[key], eval_args, variables, port, append_to_queue=False)
 
        if key in BUILTINS:
            return BUILTINS[key](eval_args, variables)

        raise CompilerError(f"Unknown action: {name}/{arity}")

    def _exec_def(self, defn: Def, args: list, caller_vars: dict[str, object], port: int | None, append_to_queue: bool = True) -> list[Action | Barrier]:
        """Execute a def, returning the items it produces.""" 
        local_vars = dict(caller_vars)
        local_vars.update(self.global_vars)
        for param_name, arg_val in zip(defn.params, args):
            local_vars[param_name] = arg_val

        return self._exec_statements(defn.body, local_vars, port, append_to_queue=append_to_queue)

    def _exec_statements(self, statements: list, variables: dict[str, object], port: int | None, append_to_queue: bool = True) -> list[Action | Barrier]:
        """Execute a list of statements, returning produced items."""
        output: list[Action | Barrier] = []

        for stmt in statements:
            if isinstance(stmt, PlayerAction):
                if stmt.player == "implicit":
                    if port is None:
                        raise CompilerError("Implicit player action with no port context")
                    p = port
                else:
                    p = _port_number(stmt.player)
                items = self.compile_chain(stmt.chain, variables, p)
                if append_to_queue:
                    if p not in self.queues:
                        self.queues[p] = []
                    self.queues[p].extend(items)
                output.extend(items)

            elif isinstance(stmt, CallStatement):
                eval_args = [self.eval_expr(a, variables) for a in stmt.args]
                key = (stmt.name, len(eval_args))
                if key in self.defs:
                    items = self._exec_def(self.defs[key], eval_args, variables, port, append_to_queue=append_to_queue)
                    output.extend(items)
                elif key in BUILTINS:
                    items = BUILTINS[key](eval_args, variables)
                    if append_to_queue and port is not None:
                        if port not in self.queues:
                            self.queues[port] = []
                        self.queues[port].extend(items)
                    output.extend(items)
                else:
                    raise CompilerError(f"Unknown def: {stmt.name}/{len(eval_args)}")

            elif isinstance(stmt, LetStatement):
                variables[stmt.name] = self.eval_expr(stmt.value, variables)

            elif isinstance(stmt, AssignStatement):
                variables[stmt.name] = self.eval_expr(stmt.value, variables)

            elif isinstance(stmt, IfStatement):
                cond = self.eval_expr(stmt.condition, variables)
                if cond:
                    items = self._exec_statements(stmt.then_body, variables, port, append_to_queue=append_to_queue)
                    output.extend(items)
                elif stmt.else_body:
                    items = self._exec_statements(stmt.else_body, variables, port, append_to_queue=append_to_queue)
                    output.extend(items)

            elif isinstance(stmt, WhileStatement):
                iterations = 0
                while self.eval_expr(stmt.condition, variables):
                    iterations += 1
                    if iterations > MAX_ITERATIONS:
                        raise CompilerError(f"While loop exceeded {MAX_ITERATIONS} iterations")
                    items = self._exec_statements(stmt.body, variables, port, append_to_queue=append_to_queue)
                    output.extend(items)

            elif isinstance(stmt, ForStatement):
                iterable = self.eval_expr(stmt.iterable, variables)
                if not hasattr(iterable, '__iter__'):
                    raise CompilerError(f"For loop target is not iterable: {iterable}")
                for val in iterable:  # type: ignore[union-attr]
                    variables[stmt.variable] = val
                    items = self._exec_statements(stmt.body, variables, port, append_to_queue=append_to_queue)
                    output.extend(items)

        return output


def compile_match(match: Match) -> dict[int, list[Action | Barrier]]:
    """Compile a parsed Match AST into per-player action queues."""
    ctx = _CompilerContext(match)
 
    for let in match.variables:
        ctx.global_vars[let.name] = ctx.eval_expr(let.value, {})
 
    for block in match.static_blocks:
        block_vars = dict(ctx.global_vars)
        ctx._exec_statements(block.statements, block_vars, None)

    return ctx.queues
