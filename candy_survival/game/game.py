import json

import pygame

from game.states.menu import MenuState
from game.states.pause import PauseState
from game.states.playing import PlayingState
from game.states.instructions import InstructionState


class Game:
    def __init__(self) -> None:
        with open("settings.json", "r", encoding="utf-8") as handle:
            self.settings = json.load(handle)

        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error:
            pass

        self.screen = pygame.display.set_mode(
            (self.settings["screen_width"], self.settings["screen_height"])
        )
        pygame.display.set_caption("Candy Survival")

        self.clock = pygame.time.Clock()
        self.running = True
        self.target_fps = self.settings.get("fps", 60)

        self.states = []
        self._state_factories = {
            "menu": lambda: MenuState(self),
            "pause": lambda: PauseState(self),
            "playing": lambda: PlayingState(self),
            "instructions": lambda: InstructionState(self),
        }
        self.previous_state = None
        self.current_state = None
        self.change_state("menu")

    def _make_state(self, name: str):
        if name not in self._state_factories:
            raise KeyError(f"Unknown state '{name}'")
        return self._state_factories[name]()

    def change_state(self, name: str) -> None:
        self.previous_state = self.current_state
        self.current_state = name
        self.states = [self._make_state(name)]

    def push_state(self, name: str) -> None:
        self.states.append(self._make_state(name))

    def pop_state(self) -> None:
        if len(self.states) > 1:
            self.states.pop()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.states:
            self.states[-1].handle_event(event)

    def update(self, dt: float) -> None:
        if self.states and hasattr(self.states[-1], "update"):
            self.states[-1].update(dt)

    def draw(self) -> None:
        if self.states and hasattr(self.states[-1], "draw"):
            self.states[-1].draw(self.screen)
        pygame.display.flip()


def main() -> None:
    game = Game()
    while game.running:
        dt = game.clock.tick(game.target_fps) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                game.running = False
            else:
                game.handle_event(event)
        game.update(dt)
        game.draw()
    pygame.quit()
