"""MASL Runner - Thin libmelee I/O layer."""
from __future__ import annotations
from src.compiler import InputFrame
from src.scheduler import Scheduler

CHARACTER_MAP = {
    "Fox": "FOX", "Falco": "FALCO", "Marth": "MARTH",
    "Sheik": "SHEIK", "Peach": "PEACH", "Puff": "JIGGLYPUFF",
    "Falcon": "CFALCON", "IceClimbers": "NANA",
    "Pikachu": "PIKACHU", "Samus": "SAMUS",
    "DrMario": "DOC", "Yoshi": "YOSHI", "Luigi": "LUIGI",
    "Ganondorf": "GANONDORF", "Mario": "MARIO",
    "YoungLink": "YLINK", "DonkeyKong": "DK",
    "Link": "LINK", "MrGameAndWatch": "GAMEANDWATCH",
    "Roy": "ROY", "Mewtwo": "MEWTWO", "Zelda": "ZELDA",
    "Ness": "NESS", "Pichu": "PICHU", "Bowser": "BOWSER",
    "Kirby": "KIRBY",
}

STAGE_MAP = {
    "FinalDestination": "FINAL_DESTINATION",
    "Battlefield": "BATTLEFIELD",
    "DreamLand": "DREAM_LAND_N64",
    "YoshisStory": "YOSHIS_STORY",
    "FountainOfDreams": "FOUNTAIN_OF_DREAMS",
    "PokemonStadium": "POKEMON_STADIUM",
}

BUTTON_MAP = {
    "A": "BUTTON_A", "B": "BUTTON_B",
    "X": "BUTTON_X", "Y": "BUTTON_Y",
    "Z": "BUTTON_Z", "L": "BUTTON_L", "R": "BUTTON_R",
    "START": "BUTTON_START",
    "DPAD_UP": "BUTTON_D_UP", "DPAD_DOWN": "BUTTON_D_DOWN",
    "DPAD_LEFT": "BUTTON_D_LEFT", "DPAD_RIGHT": "BUTTON_D_RIGHT",
}

# Default string-based controls for testing 
DEFAULT_CONTROLS: dict[str, object] = {
    **BUTTON_MAP,
    "MAIN": "BUTTON_MAIN",
    "C": "BUTTON_C",
    "L_SHOULDER": "BUTTON_L",
    "R_SHOULDER": "BUTTON_R",
}


def _build_melee_controls() -> dict[str, object]:
    """Build controls dict with resolved melee.Button enums."""
    import melee
    controls: dict[str, object] = {}
    for name, enum_str in BUTTON_MAP.items():
        controls[name] = getattr(melee.Button, enum_str)
    controls["MAIN"] = melee.Button.BUTTON_MAIN
    controls["C"] = melee.Button.BUTTON_C
    controls["L_SHOULDER"] = melee.Button.BUTTON_L
    controls["R_SHOULDER"] = melee.Button.BUTTON_R
    return controls


class Runner:
    def __init__(self, scheduler: Scheduler, dolphin_path: str | None = None,
                 iso_path: str | None = None, game_config=None):
        self.scheduler = scheduler
        self.dolphin_path = dolphin_path
        self.iso_path = iso_path
        self.game_config = game_config
        self._console = None

    def run(self) -> None:
        """Main frame loop. Requires libmelee + Dolphin."""
        import melee

        if not self.dolphin_path or not self.iso_path or not self.game_config:
            raise RuntimeError("dolphin_path, iso_path, and game_config required for run()")

        console = melee.Console(path=self.dolphin_path)
        self._console = console
        controls = _build_melee_controls()
 
        static_ports: dict[int, str] = {}  # port -> char name
        human_ports: set[int] = set()
        stage_name = self.game_config.stage

        for player in self.game_config.players:
            port = int(player.port[1:])  # "P1" -> 1
            if player.player_type == "Static":
                static_ports[port] = player.character
            else:
                human_ports.add(port)
 
        characters = {}
        for port, char_name in static_ports.items():
            characters[port] = getattr(melee.Character, CHARACTER_MAP[char_name])
        stage = getattr(melee.Stage, STAGE_MAP[stage_name])

        # Create controllers
        controllers: dict[int, melee.Controller] = {}
        for port in list(static_ports) + list(human_ports):
            controllers[port] = melee.Controller(
                console=console, port=port,
                type=melee.ControllerType.STANDARD,
            )

        console.run(iso_path=self.iso_path)
        console.connect()
        for ctrl in controllers.values():
            ctrl.connect()

        autostart_port = min(static_ports) if static_ports else None
        menu_helpers: dict[int, melee.MenuHelper] = {
            port: melee.MenuHelper() for port in static_ports
        }

        try:
            while True:
                gamestate = console.step()
                if gamestate is None:
                    break

                if gamestate.menu_state not in (melee.Menu.IN_GAME, melee.Menu.SUDDEN_DEATH):
                    for port in static_ports:
                        menu_helpers[port].menu_helper_simple(
                            gamestate,
                            controllers[port],
                            characters[port],
                            stage,
                            autostart=(port == autostart_port),
                        )
                    continue

                if gamestate.frame < 0:
                    continue

                # In-game
                frames = self.scheduler.step(gamestate)
                for port in static_ports:
                    if port in frames:
                        self._apply_frame_to_controller(
                            frames[port], controllers[port], controls,
                        )

                if self.all_idle():
                    break
        finally:
            console.stop()
            self._console = None

    def stop(self) -> None:
        """Stop the console if running."""
        if self._console is not None:
            self._console.stop()
            self._console = None

    def all_idle(self) -> bool:
        """Check if all static ports have finished their queues."""
        if not self.game_config:
            return all(
                self.scheduler.is_idle(port) for port in self.scheduler.queues
            )
        for player in self.game_config.players:
            if player.player_type == "Static":
                port = int(player.port[1:])
                if not self.scheduler.is_idle(port):
                    return False
        return True

    def dry_run(self, num_frames: int) -> list[dict[int, InputFrame]]:
        """Run without Dolphin for testing. Returns frame-by-frame output."""
        results = []
        for _ in range(num_frames):
            frames = self.scheduler.step(None)
            results.append(frames)
        return results

    @staticmethod
    def _apply_frame_to_controller(
        frame: InputFrame, controller, controls: dict[str, object] = DEFAULT_CONTROLS,
    ) -> None:
        """Translate InputFrame to controller calls.

        Controls dict maps button names to controller values — strings for
        testing, melee.Button enums for live execution.
        """
        if frame == InputFrame():
            controller.release_all()
            return

        controller.release_all()

        for btn_name in frame.buttons:
            if btn_name in controls:
                controller.press_button(controls[btn_name])

        if frame.main_stick != (0.0, 0.0):
            x, y = frame.main_stick
            controller.tilt_analog(controls["MAIN"], x, y)

        if frame.c_stick != (0.0, 0.0):
            x, y = frame.c_stick
            controller.tilt_analog(controls["C"], x, y)

        if frame.l_trigger > 0:
            controller.press_shoulder(controls["L_SHOULDER"], frame.l_trigger)

        if frame.r_trigger > 0:
            controller.press_shoulder(controls["R_SHOULDER"], frame.r_trigger)
