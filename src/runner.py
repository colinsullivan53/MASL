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

class Runner:
    def __init__(self, scheduler: Scheduler, dolphin_path: str | None = None,
                 iso_path: str | None = None, game_config=None):
        self.scheduler = scheduler
        self.dolphin_path = dolphin_path
        self.iso_path = iso_path
        self.game_config = game_config

    def run(self) -> None:
        """Main frame loop. Requires libmelee + Dolphin."""
        raise NotImplementedError("Full runner requires libmelee + Dolphin")

    def dry_run(self, num_frames: int) -> list[dict[int, InputFrame]]:
        """Run without Dolphin for testing. Returns frame-by-frame output."""
        results = []
        for _ in range(num_frames):
            frames = self.scheduler.step(None)
            results.append(frames)
        return results

    @staticmethod
    def _apply_frame_to_controller(frame: InputFrame, controller) -> None:
        """Translate InputFrame to libmelee controller calls.""" 
        if frame == InputFrame():
            controller.release_all()
            return

        controller.release_all()
 
        for btn_name in frame.buttons:
            if btn_name in BUTTON_MAP:
                controller.press_button(BUTTON_MAP[btn_name])

        # Main stick
        if frame.main_stick != (0.0, 0.0):
            x, y = frame.main_stick
            controller.tilt_analog("BUTTON_MAIN", x, y)

        # C stick
        if frame.c_stick != (0.0, 0.0):
            x, y = frame.c_stick
            controller.tilt_analog("BUTTON_C", x, y)

        # Analog triggers
        if frame.l_trigger > 0:
            controller.press_shoulder("BUTTON_L", frame.l_trigger)

        if frame.r_trigger > 0:
            controller.press_shoulder("BUTTON_R", frame.r_trigger)
