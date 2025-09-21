import random
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

import pygame

DEFAULT_COUNTER_ITEMS = ['Clothes Pin', 'Paper Ship', 'Dollhouse', 'Umbrella']

@dataclass(frozen=True)
class EventDefinition:
    name: str
    counter_item: Optional[str]
    counter_amount: int = 1
    display_name: Optional[str] = None

    @property
    def requires_any_counter(self) -> bool:
        return (self.counter_item or '').lower() == 'any'

    @property
    def label(self) -> str:
        return (self.display_name or self.name).replace('_', ' ').title()


def _default_event_definitions(any_counter_cost: int) -> List[EventDefinition]:
    return [
        EventDefinition(name='stink', counter_item='Clothes Pin'),
        EventDefinition(name='crying', counter_item='Paper Ship'),
        EventDefinition(name='landslide', counter_item='Dollhouse'),
        EventDefinition(name='embrassing', counter_item='Umbrella'),
        EventDefinition(name='self_deprecation', counter_item='any', counter_amount=any_counter_cost),
    ]


def parse_event_definitions(raw, default_any_cost: int) -> List[EventDefinition]:
    definitions: List[EventDefinition] = []
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            name = entry.get('name')
            if not name:
                continue
            counter_item = entry.get('counter_item')
            try:
                amount = int(entry.get('counter_amount', default_any_cost))
            except (TypeError, ValueError):
                amount = default_any_cost
            display_name = entry.get('display_name')
            definitions.append(
                EventDefinition(
                    name=name,
                    counter_item=counter_item,
                    counter_amount=amount,
                    display_name=display_name,
                )
            )
    if not definitions:
        definitions = _default_event_definitions(default_any_cost)
    return definitions


def derive_counter_items(explicit_items: Iterable[str], definitions: Sequence[EventDefinition]) -> List[str]:
    items: List[str] = []
    if explicit_items:
        items = [str(item) for item in explicit_items if item]
    if not items:
        items = list(DEFAULT_COUNTER_ITEMS)
    else:
        existing = []
        for item in items:
            if item not in existing:
                existing.append(item)
        for item in DEFAULT_COUNTER_ITEMS:
            if item not in existing:
                existing.append(item)
        items = existing
    for definition in definitions:
        if definition.requires_any_counter:
            continue
        if definition.counter_item and definition.counter_item not in items:
            items.append(definition.counter_item)
    return items


RadioCallback = Callable[[str, Tuple[int, int, int]], None]
HintCallback = Callable[[bool], None]


class EventManager:
    def __init__(
        self,
        audio,
        msglog,
        definitions: Sequence[EventDefinition],
        counter_items: Iterable[str],
        radio_hint_long: int,
        radio_hint_short: int,
        on_radio_message: Optional[RadioCallback] = None,
        on_radio_hint: Optional[HintCallback] = None,
    ) -> None:
        self.audio = audio
        self.msglog = msglog
        self.definitions: List[EventDefinition] = list(definitions)
        self.counter_items: List[str] = list(counter_items)
        self.hint_long = radio_hint_long * 1000
        self.hint_short = radio_hint_short * 1000
        self.on_radio_message = on_radio_message
        self.on_radio_hint = on_radio_hint

        self.night_active = False
        self.current_event: Optional[EventDefinition] = None
        self.next_event_time: Optional[int] = None
        self.hint_time: Optional[int] = None
        self.long_hint_enabled = False

    def begin_night(self, start_tick: int, delay_ms: int) -> None:
        if not self.definitions:
            self.night_active = False
            self.current_event = None
            self.next_event_time = None
            self.hint_time = None
            return

        self.night_active = True
        self.current_event = random.choice(self.definitions)
        self.next_event_time = start_tick + delay_ms
        self._schedule_hint()

    def end_night(self) -> None:
        self.night_active = False
        self.current_event = None
        self.next_event_time = None
        self.hint_time = None

    def _schedule_hint(self) -> None:
        if not (self.night_active and self.next_event_time):
            self.hint_time = None
            return
        delta = self.hint_long if self.long_hint_enabled else self.hint_short
        now = pygame.time.get_ticks()
        hint_at = max(now, self.next_event_time - delta)
        self.hint_time = hint_at if hint_at < self.next_event_time else None

    def set_long_hint(self, enabled: bool) -> None:
        if self.long_hint_enabled == enabled:
            return
        self.long_hint_enabled = enabled
        self._schedule_hint()

    def seconds_until_event(self) -> Optional[int]:
        if not self.next_event_time:
            return None
        now = pygame.time.get_ticks()
        if self.next_event_time <= now:
            return 0
        return (self.next_event_time - now) // 1000

    def update(self, player_inventory):
        if not (self.night_active and self.next_event_time and self.current_event):
            return None

        now = pygame.time.get_ticks()
        if self.hint_time and now >= self.hint_time:
            text = f"Radio: Incoming event {self.current_event.label}!"
            self._emit_radio_message(text, (0, 255, 255))
            if self.on_radio_hint:
                self.on_radio_hint(self.long_hint_enabled)
            self.hint_time = None

        if now < self.next_event_time:
            return None

        success, requirement_text, consumed_description = self._resolve_event(player_inventory)
        if success:
            message = f"Event '{self.current_event.label}' resolved thanks to {consumed_description}!"
            color = (255, 255, 0)
        else:
            message = f"Event '{self.current_event.label}' struck! Missing {requirement_text}."
            color = (255, 80, 80)
        self._emit_radio_message(message, color)

        result = ("event", self.current_event, success, consumed_description if success else requirement_text)
        self.current_event = None
        self.next_event_time = None
        self.hint_time = None
        return result

    def _emit_radio_message(self, text: str, color: Tuple[int, int, int]) -> None:
        self.msglog.add(text, color)
        if self.audio:
            self.audio.sfx("radio")
        if self.on_radio_message:
            self.on_radio_message(text, color)

    def _resolve_event(self, player_inventory):
        event = self.current_event
        assert event is not None

        if event.requires_any_counter:
            needed = max(1, event.counter_amount)
            remaining = needed
            consumed: List[Tuple[str, int]] = []
            total_available = sum(player_inventory.count(name) for name in self.counter_items)
            if total_available < needed:
                requirement = f"any counter items x{needed}"
                return False, requirement, requirement

            for item_name in self.counter_items:
                if remaining <= 0:
                    break
                available = player_inventory.count(item_name)
                if available <= 0:
                    continue
                take = min(available, remaining)
                if player_inventory.remove(item_name, take):
                    consumed.append((item_name, take))
                    remaining -= take
            description = ", ".join(f"{name} x{count}" for name, count in consumed) if consumed else f"counter items x{needed}"
            return True, description, description

        requirement_item = event.counter_item or "counter item"
        amount = max(1, event.counter_amount)
        if not player_inventory.has(requirement_item, amount):
            requirement = f"{requirement_item} x{amount}"
            return False, requirement, requirement
        player_inventory.remove(requirement_item, amount)
        description = f"{requirement_item} x{amount}"
        return True, description, description


