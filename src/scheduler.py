"""MASL Scheduler - Manages per-player queues of Actions and Barriers, advancing frame by frame."""

from __future__ import annotations

from src.compiler import InputFrame, Action, Barrier

NEUTRAL = InputFrame()

ACTIONABLE_STATES = frozenset([
    "STANDING", "WAIT", "WALK_SLOW", "WALK_MIDDLE", "WALK_FAST",
    "DASH", "RUN", "RUN_BRAKE", "TURN", "TURN_RUN",
    "CROUCH_START", "CROUCHING", "CROUCH_END",
    "LANDING", "LANDING_SPECIAL",
])


class Scheduler:
    def __init__(self):
        self.queues: dict[int, list[Action | Barrier]] = {}
        self.cursors: dict[int, int] = {}

    def load(self, port: int, queue: list[Action | Barrier]) -> None:
        """Load a full action queue for a port."""
        self.queues[port] = list(queue)
        self.cursors[port] = 0

    def push(self, port: int, item: Action | Barrier) -> None:
        """Push a single item to a port's queue (for REPL/bot use)."""
        if port not in self.queues:
            self.queues[port] = []
            self.cursors[port] = 0
        self.queues[port].append(item)

    def step(self, gamestate) -> dict[int, InputFrame]:
        """Advance one frame. Returns InputFrame per port."""
        result: dict[int, InputFrame] = {}
        for port in list(self.queues.keys()):
            result[port] = self._step_port(port, gamestate)
        return result

    def is_idle(self, port: int) -> bool:
        """Check if a port's queue is empty."""
        if port not in self.queues:
            return True
        return len(self.queues[port]) == 0

    def _step_port(self, port, gamestate) -> InputFrame:
        """Step one port forward by one frame."""
        queue = self.queues.get(port, [])
        if not queue:
            return NEUTRAL

        item = queue[0]

        if isinstance(item, Barrier):
            resolved = self._evaluate_barrier(item, port, gamestate)
            if resolved:
                queue.pop(0)
                # Try to start next item 
                if queue:
                    next_item = queue[0]
                    if isinstance(next_item, Action):
                        return self._advance_action(port, next_item)
                    # If next is also barrier, return neutral this frame
                return NEUTRAL
            else:
                return NEUTRAL

        if isinstance(item, Action):
            return self._advance_action(port, item)

        return NEUTRAL

    def _advance_action(self, port, action: Action) -> InputFrame:
        """Advance through an Action's frames."""
        cursor = self.cursors.get(port, 0)
        if cursor < len(action.frames):
            frame = action.frames[cursor]
            self.cursors[port] = cursor + 1
            # Check if action is done
            if self.cursors[port] >= len(action.frames):
                self.queues[port].pop(0)
                self.cursors[port] = 0
            return frame
        else:
            # Action has no frames or cursor past end, pop it
            self.queues[port].pop(0)
            self.cursors[port] = 0
            return NEUTRAL

    def _evaluate_barrier(self, barrier: Barrier, port: int, gamestate) -> bool:
        """Evaluate a barrier. Returns True when resolved."""
        if gamestate is None:
            return False

        players = gamestate.players
        if port not in players:
            return False

        player = players[port]
        condition_met = self._check_condition(barrier.condition, player)

        if not barrier._seen_exit: 
            # First phase: wait for condition to NOT be met 
            if not condition_met:
                barrier._seen_exit = True 
                return False
            else: 
                return False
        else:
            # Second phase: wait for condition to be met again 
            if condition_met:
                return True
            else:
                return False

    def _check_condition(self, condition: str, player) -> bool:
        """Check if a barrier condition is currently met."""
        if condition == "act":
            return player.action.name in ACTIONABLE_STATES
        elif condition == "ground":
            return player.on_ground
        elif condition == "apex":
            return player.speed_y_self <= 0 and not player.on_ground
        return False
