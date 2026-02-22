"""Tests for the MASL Scheduler."""

from src.compiler import InputFrame, Action, Barrier
from src.scheduler import Scheduler, ACTIONABLE_STATES, NEUTRAL
from unittest.mock import MagicMock


def make_gamestate(port, action_name, on_ground=True, speed_y=0.0):
    gs = MagicMock()
    player = MagicMock()
    player.action.name = action_name
    player.on_ground = on_ground
    player.speed_y_self = speed_y
    gs.players = {port: player}
    return gs


def make_multi_gamestate(port_configs):
    """Create a gamestate with multiple players.
    port_configs: dict of port -> (action_name, on_ground, speed_y)
    """
    gs = MagicMock()
    players = {}
    for port, (action_name, on_ground, speed_y) in port_configs.items():
        player = MagicMock()
        player.action.name = action_name
        player.on_ground = on_ground
        player.speed_y_self = speed_y
        players[port] = player
    gs.players = players
    return gs


# 1. Empty scheduler returns neutral for all ports
class TestEmptyScheduler:
    def test_step_returns_empty_dict(self):
        sched = Scheduler()
        result = sched.step(None)
        assert result == {}

    def test_is_idle_unknown_port(self):
        sched = Scheduler()
        assert sched.is_idle(1) is True

    def test_load_empty_queue(self):
        sched = Scheduler()
        sched.load(1, [])
        result = sched.step(None)
        assert result[1] == NEUTRAL


# 2. Load and step through a single Action
class TestSingleAction:
    def test_two_frame_action(self):
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        frame_b = InputFrame(buttons=frozenset(["B"]))
        action = Action(frames=[frame_a, frame_b])
        sched.load(1, [action])

        # Frame 1: get A
        result = sched.step(None)
        assert result[1] == frame_a

        # Frame 2: get B
        result = sched.step(None)
        assert result[1] == frame_b

        # Frame 3: action exhausted, neutral
        result = sched.step(None)
        assert result[1] == NEUTRAL
        assert sched.is_idle(1) is True

    def test_single_frame_action(self):
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        action = Action(frames=[frame_a])
        sched.load(1, [action])

        result = sched.step(None)
        assert result[1] == frame_a

        # Now idle
        assert sched.is_idle(1) is True


# 3. Multiple Actions executed sequentially
class TestSequentialActions:
    def test_two_actions_back_to_back(self):
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        frame_b = InputFrame(buttons=frozenset(["B"]))
        a1 = Action(frames=[frame_a, frame_a])
        a2 = Action(frames=[frame_b])
        sched.load(1, [a1, a2])

        # Frames from a1
        result = sched.step(None)
        assert result[1] == frame_a
        result = sched.step(None)
        assert result[1] == frame_a

        # Frame from a2
        result = sched.step(None)
        assert result[1] == frame_b

        # Done
        assert sched.is_idle(1) is True


# 4. Barrier blocks until two-phase resolution completes
class TestBarrierActCondition:
    def test_barrier_two_phase(self):
        """a1(A) -> barrier(act) -> a2(B)
        Phase 1: condition is met (actionable), wait for exit
        Phase 2: condition not met, then met again -> resolved
        """
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        frame_b = InputFrame(buttons=frozenset(["B"]))
        a1 = Action(frames=[frame_a])
        barrier = Barrier(condition="act")
        a2 = Action(frames=[frame_b])
        sched.load(1, [a1, barrier, a2])

        # Step 1: get A from a1
        gs = make_gamestate(1, "STANDING")
        result = sched.step(gs)
        assert result[1] == frame_a

        # Step 2: barrier is front, player is STANDING (actionable) -> phase 1, condition met, stay
        gs = make_gamestate(1, "STANDING")
        result = sched.step(gs)
        assert result[1] == NEUTRAL

        # Step 3: player enters non-actionable state -> phase 1 exits, _seen_exit=True
        # But condition not met yet for phase 2, so still neutral
        gs = make_gamestate(1, "ATTACK_11")
        result = sched.step(gs)
        assert result[1] == NEUTRAL

        # Step 4: player returns to actionable -> phase 2 condition met, barrier resolved
        # Next item (a2) starts same frame
        gs = make_gamestate(1, "STANDING")
        result = sched.step(gs)
        assert result[1] == frame_b

        assert sched.is_idle(1) is True


# 5. Barrier for "ground" condition
class TestBarrierGroundCondition:
    def test_ground_barrier_two_phase(self):
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        barrier = Barrier(condition="ground")
        action = Action(frames=[frame_a])
        sched.load(1, [barrier, action])

        # Player on ground -> phase 1, condition met, wait for exit
        gs = make_gamestate(1, "STANDING", on_ground=True)
        result = sched.step(gs)
        assert result[1] == NEUTRAL

        # Player leaves ground -> phase 1 exit
        gs = make_gamestate(1, "JUMP", on_ground=False)
        result = sched.step(gs)
        assert result[1] == NEUTRAL

        # Player lands -> phase 2 condition met, resolved
        gs = make_gamestate(1, "LANDING", on_ground=True)
        result = sched.step(gs)
        assert result[1] == frame_a

        assert sched.is_idle(1) is True


# 6. Barrier already in exited state (condition already not met -> skip phase 1)
class TestBarrierAlreadyExited:
    def test_ground_barrier_already_airborne(self):
        """If player is already airborne when ground barrier starts,
        phase 1 immediately exits (condition not met), enter phase 2."""
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        barrier = Barrier(condition="ground")
        action = Action(frames=[frame_a])
        sched.load(1, [barrier, action])

        # Player already airborne -> condition not met -> _seen_exit=True (phase 1 done)
        gs = make_gamestate(1, "JUMP", on_ground=False)
        result = sched.step(gs)
        assert result[1] == NEUTRAL  # Phase 2 not met yet (not on ground)

        # Player lands -> phase 2 met
        gs = make_gamestate(1, "LANDING", on_ground=True)
        result = sched.step(gs)
        assert result[1] == frame_a

    def test_act_barrier_already_non_actionable(self):
        """If player is already in non-actionable state, skip phase 1."""
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        barrier = Barrier(condition="act")
        action = Action(frames=[frame_a])
        sched.load(1, [barrier, action])

        # Player in non-actionable state -> skip phase 1
        gs = make_gamestate(1, "ATTACK_11")
        result = sched.step(gs)
        assert result[1] == NEUTRAL  # Phase 2: waiting for actionable

        # Player becomes actionable -> resolved
        gs = make_gamestate(1, "STANDING")
        result = sched.step(gs)
        assert result[1] == frame_a


# 7. push() appends to queue
class TestPush:
    def test_push_to_new_port(self):
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        action = Action(frames=[frame_a])
        sched.push(1, action)

        assert not sched.is_idle(1)
        result = sched.step(None)
        assert result[1] == frame_a
        assert sched.is_idle(1)

    def test_push_appends_to_existing(self):
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        frame_b = InputFrame(buttons=frozenset(["B"]))
        sched.load(1, [Action(frames=[frame_a])])
        sched.push(1, Action(frames=[frame_b]))

        result = sched.step(None)
        assert result[1] == frame_a
        result = sched.step(None)
        assert result[1] == frame_b
        assert sched.is_idle(1)


# 8. is_idle() returns True when queue empty, False otherwise
class TestIsIdle:
    def test_idle_after_load_empty(self):
        sched = Scheduler()
        sched.load(1, [])
        assert sched.is_idle(1) is True

    def test_not_idle_with_items(self):
        sched = Scheduler()
        sched.load(1, [Action(frames=[InputFrame()])])
        assert sched.is_idle(1) is False

    def test_idle_after_consuming_all(self):
        sched = Scheduler()
        sched.load(1, [Action(frames=[InputFrame()])])
        sched.step(None)
        assert sched.is_idle(1) is True


# 9. Multi-player: two ports stepping independently
class TestMultiPlayer:
    def test_two_ports_independent(self):
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        frame_b = InputFrame(buttons=frozenset(["B"]))
        frame_x = InputFrame(buttons=frozenset(["X"]))

        sched.load(1, [Action(frames=[frame_a, frame_a])])
        sched.load(2, [Action(frames=[frame_b]), Action(frames=[frame_x])])

        gs = make_multi_gamestate({
            1: ("STANDING", True, 0.0),
            2: ("STANDING", True, 0.0),
        })

        # Frame 1
        result = sched.step(gs)
        assert result[1] == frame_a
        assert result[2] == frame_b

        # Frame 2
        result = sched.step(gs)
        assert result[1] == frame_a
        assert result[2] == frame_x

        # Frame 3: port 1 done, port 2 done
        result = sched.step(gs)
        assert result[1] == NEUTRAL
        assert result[2] == NEUTRAL

    def test_one_port_barrier_other_continues(self):
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        frame_b = InputFrame(buttons=frozenset(["B"]))

        sched.load(1, [Barrier(condition="act"), Action(frames=[frame_a])])
        sched.load(2, [Action(frames=[frame_b])])

        gs = make_multi_gamestate({
            1: ("ATTACK_11", True, 0.0),
            2: ("STANDING", True, 0.0),
        })

        # Port 1 blocked on barrier, port 2 proceeds
        result = sched.step(gs)
        assert result[1] == NEUTRAL
        assert result[2] == frame_b

        # Port 2 now idle
        assert sched.is_idle(2) is True
        assert sched.is_idle(1) is False


# 10. Barrier with no gamestate returns neutral (can't evaluate)
class TestBarrierNoGamestate:
    def test_barrier_with_none_gamestate(self):
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        sched.load(1, [Barrier(condition="act"), Action(frames=[frame_a])])

        result = sched.step(None)
        assert result[1] == NEUTRAL
        # Barrier not resolved, still not idle
        assert sched.is_idle(1) is False


# Additional edge case tests
class TestApexBarrier:
    def test_apex_condition(self):
        """Apex = speed_y <= 0 and not on_ground."""
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        barrier = Barrier(condition="apex")
        action = Action(frames=[frame_a])
        sched.load(1, [barrier, action])

        # On ground, going up -> apex not met, skip phase 1
        gs = make_gamestate(1, "STANDING", on_ground=True, speed_y=5.0)
        result = sched.step(gs)
        assert result[1] == NEUTRAL  # Phase 1 exits (condition not met), phase 2 waiting

        # Airborne going up -> speed_y > 0, not apex
        gs = make_gamestate(1, "JUMP", on_ground=False, speed_y=5.0)
        result = sched.step(gs)
        assert result[1] == NEUTRAL

        # Airborne at apex -> speed_y <= 0 and not on_ground -> resolved
        gs = make_gamestate(1, "JUMP", on_ground=False, speed_y=0.0)
        result = sched.step(gs)
        assert result[1] == frame_a


class TestEmptyAction:
    def test_action_with_no_frames(self):
        """An action with no frames should be skipped."""
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        empty = Action(frames=[])
        real = Action(frames=[frame_a])
        sched.load(1, [empty, real])

        # Empty action consumed, real action starts
        result = sched.step(None)
        assert result[1] == NEUTRAL  # empty action returns neutral

        result = sched.step(None)
        assert result[1] == frame_a


class TestConsecutiveBarriers:
    def test_two_barriers_in_sequence(self):
        sched = Scheduler()
        frame_a = InputFrame(buttons=frozenset(["A"]))
        b1 = Barrier(condition="act")
        b2 = Barrier(condition="ground")
        action = Action(frames=[frame_a])
        sched.load(1, [b1, b2, action])

        # b1: player not actionable -> skip phase 1, enter phase 2
        gs = make_gamestate(1, "ATTACK_11", on_ground=True)
        result = sched.step(gs)
        assert result[1] == NEUTRAL

        # b1: player actionable -> phase 2 met, resolved. b2 starts same frame.
        # b2: player on ground -> phase 1, condition met, stay
        gs = make_gamestate(1, "STANDING", on_ground=True)
        result = sched.step(gs)
        assert result[1] == NEUTRAL  # b2 blocking

        # b2: player airborne -> phase 1 exits
        gs = make_gamestate(1, "JUMP", on_ground=False)
        result = sched.step(gs)
        assert result[1] == NEUTRAL

        # b2: player lands -> phase 2 met, resolved, action starts
        gs = make_gamestate(1, "LANDING", on_ground=True)
        result = sched.step(gs)
        assert result[1] == frame_a
