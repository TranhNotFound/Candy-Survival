import random
from typing import Callable, Optional, Tuple

import pygame

EVENTS = (
    ("storm", "Lightning Rod"),
    ("earthquake", "Shock Absorber"),
    ("drought", "Water Canister"),
    ("candy_swarm", "Bug Repellent"),
)

RadioCallback = Callable[[str, Tuple[int, int, int]], None]
HintCallback = Callable[[bool], None]


class EventManager:
    def __init__(
        self,
        interval_sec: int,
        radio_hint_long: int,
        radio_hint_short: int,
        audio,
        msglog,
        on_radio_message: Optional[RadioCallback] = None,
        on_radio_hint: Optional[HintCallback] = None,
    ):
        self.interval_ms = interval_sec * 1000
        self.hint_long = radio_hint_long * 1000
        self.hint_short = radio_hint_short * 1000
        self.audio = audio
        self.msglog = msglog
        self.on_radio_message = on_radio_message
        self.on_radio_hint = on_radio_hint

        self.next_event_time = pygame.time.get_ticks() + self.interval_ms
        self.next_event = random.choice(EVENTS)
        self.hint_time: Optional[int] = None
        self.long_hint_enabled = False
        self.schedule_hint()

    def schedule_hint(self) -> None:
        now = pygame.time.get_ticks()
        delta = self.hint_long if self.long_hint_enabled else self.hint_short
        self.hint_time = max(now, self.next_event_time - delta)

    def set_long_hint(self, enabled: bool) -> None:
        if self.long_hint_enabled == enabled:
            return
        self.long_hint_enabled = enabled
        self.schedule_hint()

    def seconds_until_event(self) -> Optional[int]:
        now = pygame.time.get_ticks()
        if self.next_event_time <= now:
            return 0
        return (self.next_event_time - now) // 1000

    def update(self, player_inventory):
        now = pygame.time.get_ticks()
        if self.hint_time and now >= self.hint_time:
            evt_name, _ = self.next_event
            text = f"Radio: Incoming event {evt_name}!"
            long_hint_active = self.long_hint_enabled
            self.msglog.add(text, (0, 255, 255))
            self.audio.sfx("radio")
            if self.on_radio_message:
                self.on_radio_message(text, (0, 255, 255))
            if self.on_radio_hint:
                self.on_radio_hint(long_hint_active)
            self.hint_time = None

        if now >= self.next_event_time:
            evt_name, requirement = self.next_event
            if player_inventory.has(requirement, 1):
                player_inventory.remove(requirement, 1)
                success = True
                text = f"Event '{evt_name}' resolved thanks to {requirement}!"
                color = (255, 255, 0)
            else:
                success = False
                text = f"Event '{evt_name}' struck! Missing {requirement}."
                color = (255, 80, 80)

            self.msglog.add(text, color)
            if self.on_radio_message:
                self.on_radio_message(text, color)

            self.next_event = random.choice(EVENTS)
            self.next_event_time = now + self.interval_ms
            self.schedule_hint()
            return "event", evt_name, success

        return None




