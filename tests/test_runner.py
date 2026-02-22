from src.runner import Runner, CHARACTER_MAP, STAGE_MAP, BUTTON_MAP
from src.compiler import InputFrame, Action
from src.scheduler import Scheduler
from src.parser import PlayerConfig, Game
from unittest.mock import MagicMock, patch

def test_character_map_has_common_chars():
    assert "Fox" in CHARACTER_MAP
    assert "Falco" in CHARACTER_MAP
    assert "Marth" in CHARACTER_MAP

def test_stage_map_has_common_stages():
    assert "FinalDestination" in STAGE_MAP
    assert "Battlefield" in STAGE_MAP
    assert "DreamLand" in STAGE_MAP

def test_button_map_covers_gc_buttons():
    for btn in ["A", "B", "X", "Y", "Z", "L", "R", "START"]:
        assert btn in BUTTON_MAP

def test_apply_neutral_frame():
    controller = MagicMock()
    Runner._apply_frame_to_controller(InputFrame(), controller)
    controller.release_all.assert_called_once()
    controller.press_button.assert_not_called()

def test_apply_button_frame():
    controller = MagicMock()
    frame = InputFrame(buttons=frozenset({"A", "B"}))
    Runner._apply_frame_to_controller(frame, controller)
    assert controller.press_button.call_count == 2

def test_apply_stick_frame():
    controller = MagicMock()
    frame = InputFrame(main_stick=(0.5, -1.0))
    Runner._apply_frame_to_controller(frame, controller)
    controller.tilt_analog.assert_called_once()

def test_apply_cstick_frame():
    controller = MagicMock()
    frame = InputFrame(c_stick=(1.0, 0.0))
    Runner._apply_frame_to_controller(frame, controller)
    controller.tilt_analog.assert_called_once()

def test_apply_trigger_frame():
    controller = MagicMock()
    frame = InputFrame(l_trigger=0.4)
    Runner._apply_frame_to_controller(frame, controller)
    controller.press_shoulder.assert_called_once()

def test_apply_rtrigger_frame():
    controller = MagicMock()
    frame = InputFrame(r_trigger=0.7)
    Runner._apply_frame_to_controller(frame, controller)
    controller.press_shoulder.assert_called_once()

def test_dry_run():
    sched = Scheduler()
    sched.load(1, [Action(frames=[InputFrame(buttons=frozenset({"A"})), InputFrame(buttons=frozenset({"A"}))])])
    runner = Runner(sched)
    results = runner.dry_run(5)
    assert len(results) == 5
    assert "A" in results[0][1].buttons
    assert "A" in results[1][1].buttons
    assert results[2][1].buttons == frozenset()  # action done, neutral

def test_dry_run_empty():
    sched = Scheduler()
    runner = Runner(sched)
    results = runner.dry_run(3)
    assert len(results) == 3


def test_all_idle_no_game_config():
    sched = Scheduler()
    sched.load(1, [Action(frames=[InputFrame()])])
    runner = Runner(sched)
    assert not runner.all_idle()
    sched.step(None)  # consume the single frame
    assert runner.all_idle()


def test_all_idle_with_game_config():
    game = Game(
        stage="FinalDestination",
        players=[
            PlayerConfig(port="P1", character="Fox", player_type="Static"),
            PlayerConfig(port="P2", character=None, player_type="Human"),
        ],
    )
    sched = Scheduler()
    sched.load(1, [Action(frames=[InputFrame()])])
    runner = Runner(sched, game_config=game)
    assert not runner.all_idle()
    sched.step(None)
    assert runner.all_idle()  # only checks P1 (static), ignores P2 (human)


def test_stop_without_console():
    sched = Scheduler()
    runner = Runner(sched)
    runner.stop()  # should not raise


def test_stop_with_console():
    sched = Scheduler()
    runner = Runner(sched)
    mock_console = MagicMock()
    runner._console = mock_console
    runner.stop()
    mock_console.stop.assert_called_once()
    assert runner._console is None


def test_run_requires_config():
    sched = Scheduler()
    runner = Runner(sched)
    try:
        runner.run()
        assert False, "Should have raised"
    except (RuntimeError, ImportError):
        pass  # RuntimeError if melee installed, ImportError if not
