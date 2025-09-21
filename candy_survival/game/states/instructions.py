import json
import pygame
from game.events import parse_event_definitions
from game.states.playing import RECIPES


class InstructionState:
    def __init__(self, game):
        self.game=game
        self.title_font=pygame.font.SysFont(None, 56)
        self.section_font=pygame.font.SysFont(None, 32)
        self.body_font=pygame.font.SysFont(None, 24)
        self.controls=[
            "Move: WASD or Arrow keys",
            "Interact: E",
            "Open/Close minimap: M",
            "Pause: ESC",
            "Craft: Access crafting tablel and choose 1-4"
        ]
        with open("settings.json", "r", encoding="utf-8") as handle:
            settings = json.load(handle)
        default_cost = int(settings.get("event_self_deprecation_counter_cost", 2))
        raw_definitions = settings.get("event_definitions", [])
        if not isinstance(raw_definitions, list):
            raw_definitions = []
        definitions = parse_event_definitions(raw_definitions, default_cost)

        self.event_counters=[]
        for definition in definitions:
            if definition.requires_any_counter:
                requirement=f"Any counter x{definition.counter_amount}"
            else:
                item_label=definition.counter_item or "counter item"
                requirement=f"{item_label} x{definition.counter_amount}"
            self.event_counters.append(f"{definition.label} -> {requirement}")
        self.recipes=[]
        for result, need in RECIPES.items():
            parts=[]
            for k,v in need.items():
                pretty=k.replace("candy_","Candy ").replace("_"," ").title()
                parts.append(f"{pretty} x{v}")
            need_txt=", ".join(parts)
            self.recipes.append(f"{result}: {need_txt}")

    def handle_event(self, e):
        if e.type==pygame.KEYDOWN:
            if e.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE, pygame.K_RETURN, pygame.K_SPACE):
                self.game.pop_state()

    def update(self, dt):
        pass

    def draw(self, surf):
        surf.fill((12,16,22))
        title=self.title_font.render("Guide", True, (255,220,120))
        surf.blit(title, (surf.get_width()//2 - title.get_width()//2, 60))

        y=140
        controls_label=self.section_font.render("Control", True, (200,240,255))
        surf.blit(controls_label, (80, y)); y+=40
        for line in self.controls:
            txt=self.body_font.render(line, True, (230,230,230))
            surf.blit(txt, (100, y)); y+=28

        y+=20
        counter_label=self.section_font.render("Events & Counter items", True, (200,240,255))
        surf.blit(counter_label, (80, y)); y+=40
        for line in self.event_counters:
            txt=self.body_font.render(line, True, (230,230,230))
            surf.blit(txt, (100, y)); y+=26

        y+=20
        recipe_label=self.section_font.render("Blueprint", True, (200,240,255))
        surf.blit(recipe_label, (80, y)); y+=40
        for line in self.recipes:
            txt=self.body_font.render(line, True, (230,230,230))
            surf.blit(txt, (100, y)); y+=26

        footer=self.body_font.render("Esc / Enter back to menu", True, (180,180,180))
        surf.blit(footer, (surf.get_width()//2 - footer.get_width()//2, surf.get_height()-80))
