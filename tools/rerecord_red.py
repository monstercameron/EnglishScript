"""Re-record the Pokemon Red demo's controller logs against the current chapters.

Each log is first played on reference chapters on which it still reaches its
goal, such as docs/red from the last commit. The inputs it gave while walking,
naming or choosing a starter are kept, and loops that made no progress are cut.
Dialogue and battles are then driven afresh on docs/red: lines are paged with A,
and every battle turn takes the move, Potion or escape that a look ahead shows
winning best. When a trainer cannot be beaten yet, the starter first trains in
the grass nearest the last Pokemon Center it visited.

    git archive HEAD docs/red | tar -x -C REFERENCE
    python tools/rerecord_red.py --reference REFERENCE/docs/red [LOG ...]
"""
import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from englishscript import compile_file
from englishscript.libraries import page

RED = ROOT / "docs" / "red"
LOGS = ("replay.json", "replay-squirtle.json", "replay-charmander.json", "replay-gate.json")
DRIVEN = {"intro", "dialogue", "battle", "battle bag", "battle party"}
FLEETING = {"column", "row", "facing", "mode", "message", "selection", "animation", "wallet", "opponent"}
BROWSING = {"cursor", "notice", "shop item", "save request"}
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}
FACING = {"north": "up", "south": "down", "west": "left", "east": "right"}
GRID = {1: (0, 0), 2: (1, 0), 3: (0, 1), 4: (1, 1)}
FIGHT, BAG, RUN = 1, 3, 4
TURN_LIMIT = 40
TURN_COST = 2
WILD_TURN_LIMIT = 8
POTION_COST = 20


class Unwinnable(Exception):
    def __init__(self, challenger, level):
        super().__init__(f"{challenger} cannot be beaten at level {level}")
        self.level = level


class Game:
    def __init__(self, world):
        self.world = world
        self.things = {name.split("\x00")[0]: thing for name, thing in world.named.items()}
        self.things["controls"].fields["rendering"] = 0

    @classmethod
    async def open(cls, chapters):
        async def model(question, state, shape, complaint):
            return ""

        world = await compile_file(chapters / "main.english").run_async(
            out=lambda text="": None, model=model,
            on_world=lambda world: page.use_remote_canvas(world, lambda *drawing: None))
        return cls(world)

    def press(self, action):
        controls = self.things["controls"]
        if not self.world.event(lambda: controls.fields.__setitem__("action", action)):
            raise RuntimeError(f"The world ended before {action}.")

    def __getitem__(self, name):
        return self.things[name].fields

    @property
    def mode(self):
        return self["journey"]["mode"]

    @property
    def ally(self):
        return self["combat"]["ally"].fields

    def spot(self):
        journey = self["journey"]
        spot = (journey["mode"], journey["place"], journey["column"], journey["row"], journey["facing"])
        return spot if journey["mode"] == "walk" else spot + (journey["selection"],)

    def progress(self):
        journey = tuple(value for name, value in self["journey"].items() if name not in FLEETING)
        story = tuple(value for name, value in self["story"].items()
                      if name.endswith("beaten") or name == "recovery place")
        stock = tuple(value for name, value in self["stock"].items() if name not in BROWSING)
        return journey + story + stock

    def attempt(self, trial):
        restore = self.world.snapshot(self.world.globals)
        try:
            return trial()
        finally:
            restore()


@dataclass
class Step:
    action: str
    spot: tuple
    progress: tuple


def position(spot):
    return spot[1:4]


async def annotate(chapters, actions):
    game = await Game.open(chapters)
    steps = []
    for action in actions:
        if game.mode not in DRIVEN:
            steps.append(Step(action, game.spot(), game.progress()))
        game.press(action)
    return steps, game.mode


def simplify(steps):
    kept = []
    seen = {}
    for step in steps:
        key = (step.spot, step.progress)
        if step.spot[0] == "walk" and key in seen:
            del kept[seen[key]:]
            seen = {known: place for known, place in seen.items() if place < len(kept)}
        if step.spot[0] == "walk":
            seen[key] = len(kept)
        kept.append(step)
    return kept


def moves_toward(start, goal):
    (column, row), (goal_column, goal_row) = GRID[start], GRID[goal]
    keys = []
    if goal_column != column:
        keys.append("right" if goal_column > column else "left")
    if goal_row != row:
        keys.append("down" if goal_row > row else "up")
    return keys


def order_keys(game, order):
    kind, choice = order
    orders = game["orders"]
    keys = []
    if kind == "move":
        if orders["phase"] != "moves":
            keys += moves_toward(int(orders["cursor"]), FIGHT) + ["a"]
            current = 1
        else:
            current = int(game["combat"]["choice"])
        return keys + moves_toward(current, choice) + ["a"]
    if orders["phase"] == "moves":
        keys.append("b")
    target = BAG if kind == "potion" else RUN
    keys += moves_toward(int(orders["cursor"]), target) + ["a"]
    return keys + (["a"] if kind == "potion" else [])


def usable_moves(game):
    choices = [slot + 1 for slot, left in enumerate(game.ally["pp"]) if left > 0]
    return choices or [1]


def awaiting_order(game):
    combat = game["combat"]
    return game.mode == "battle" and combat["active"] == 1 and not combat["later lines"]


def give(game, order):
    for key in order_keys(game, order):
        game.press(key)


def play_out(game, opening, follow):
    potions = game["stock"]["potions"]
    give(game, opening)
    turns = 1
    while game["combat"]["active"] == 1 and turns < TURN_LIMIT:
        if not awaiting_order(game):
            game.press("a")
            continue
        choice = follow if game.ally["pp"][follow - 1] > 0 else usable_moves(game)[0]
        give(game, ("move", choice))
        turns += 1
    won = game["combat"]["outcome"] == "win"
    used = potions - game["stock"]["potions"]
    health = int(game.ally["health"])
    return won, health - TURN_COST * turns - POTION_COST * int(used), health, turns


def openings(game):
    options = [("move", choice) for choice in usable_moves(game)]
    if game["stock"]["potions"] > 0 and game.ally["health"] < game.ally["maximum health"]:
        options.append(("potion", 0))
    return options


def best_order(game):
    best = None
    for opening in openings(game):
        for follow in usable_moves(game):
            score = game.attempt(lambda: play_out(game, opening, follow))
            if best is None or score > best[0]:
                best = (score, opening)
    return best


def decide(game):
    (won, _, health, turns), order = best_order(game)
    if game["combat"]["challenger"] == "wild":
        worthwhile = won and health * 4 >= game.ally["maximum health"] and turns <= WILD_TURN_LIMIT
        return order if worthwhile else ("run", 0)
    if not won:
        raise Unwinnable(game["combat"]["challenger"], int(game.ally["level"]))
    return order


class Drive:
    def __init__(self, game, route, grinds):
        self.game = game
        self.route = route
        self.grinds = grinds
        self.actions = []
        self.heals = []
        self.grassy = set()
        self.escapes = 0
        self.index = 0

    def press(self, key):
        self.game.press(key)
        self.actions.append(key)

    def settle(self):
        while self.game.mode in DRIVEN:
            if awaiting_order(self.game):
                order = decide(self.game)
                self.escapes += order[0] == "run"
                for key in order_keys(self.game, order):
                    self.press(key)
            else:
                self.press("a")

    def where(self):
        return position(self.game.spot())

    def take(self, step):
        grass = self.game["story"]["grass steps"]
        self.press(step.action)
        if step.action in OPPOSITE and (self.game.mode == "battle" or self.game["story"]["grass steps"] != grass):
            self.grassy.add(self.index)
        if step.action == "a" and step.spot[0] == "walk" and self.game.mode == "dialogue":
            self.settle()
            ally = self.game.ally
            if ally["health"] == ally["maximum health"] and self.game["story"]["recovery place"] == self.where()[0]:
                self.heals.append(self.index)
                if self.index in self.grinds:
                    self.grind(self.index)

    def forward(self, start, stop):
        return [(position(self.route[index].spot), self.route[index].action)
                for index in range(start, stop) if self.route[index].action in OPPOSITE]

    def backward(self, start, stop):
        return [(position(self.route[index + 1].spot), OPPOSITE[self.route[index].action])
                for index in reversed(range(start, stop))
                if self.route[index].action in OPPOSITE and moved(self.route, index)]

    def follow(self, path):
        for where, key in path:
            self.settle()
            if self.where() != where:
                raise RuntimeError(f"Lost the way while training: at {self.where()}, expected {where}.")
            self.press(key)
        self.settle()

    def fresh(self):
        ally = self.game.ally
        return ally["health"] * 2 >= ally["maximum health"]

    def grind(self, heal):
        site, level = self.grinds[heal]
        if site > heal:
            out, back = self.forward(heal + 1, site + 1), self.backward(heal + 1, site + 1)
        else:
            out, back = self.backward(site + 1, heal), self.forward(site + 1, heal)
        pace = self.route[site].action
        here, there = position(self.route[site].spot), position(self.route[site + 1].spot)
        facing = self.route[heal].spot[4]
        while self.game.ally["level"] < level:
            experience = self.game.ally["experience"]
            self.follow(out)
            escapes = self.escapes
            while self.game.ally["level"] < level and self.fresh() and self.escapes == escapes:
                self.follow([(there, OPPOSITE[pace]), (here, pace)])
            self.follow(back)
            if self.game["journey"]["facing"] != facing:
                self.press(FACING[facing])
            self.press("a")
            self.settle()
            if self.game.ally["experience"] == experience:
                raise RuntimeError(f"Training near step {heal} earned no experience.")

    def run(self, final_mode):
        while self.index < len(self.route):
            self.settle()
            step = self.route[self.index]
            spot = self.game.spot()
            if spot != step.spot:
                ahead = next((later for later in range(self.index + 1, len(self.route))
                              if self.route[later].spot == spot), None)
                if ahead is None:
                    raise RuntimeError(f"Lost the route at step {self.index}: at {spot}, expected {step.spot}.")
                self.index = ahead
                continue
            self.take(step)
            self.index += 1
        if final_mode not in DRIVEN:
            self.settle()


def moved(route, index):
    return position(route[index].spot) != position(route[index + 1].spot)


def training_site(route, grassy, heal, failure):
    sites = [index for index in sorted(grassy) if index - 1 in grassy and index + 1 < len(route)
             and route[index].spot[1] == route[index + 1].spot[1] and moved(route, index)]
    later = [index for index in sites if heal < index < failure]
    if later:
        return later[0]
    earlier = [index for index in sites if index < heal]
    if earlier:
        return earlier[-1]
    raise RuntimeError(f"No grass to train in near step {heal}.")


async def rerecord(reference, name):
    actions = json.loads((reference / name).read_text())
    steps, final_mode = await annotate(reference, actions)
    route = simplify(steps)
    grinds = {}
    while True:
        drive = Drive(await Game.open(RED), route, grinds)
        try:
            drive.run(final_mode)
            break
        except Unwinnable as failure:
            heal = max((index for index in drive.heals if index < drive.index), default=None)
            if heal is None:
                raise
            site = grinds[heal][0] if heal in grinds else training_site(route, drive.grassy, heal, drive.index)
            grinds[heal] = (site, failure.level + 1)
            print(f"{name}: {failure}; training to level {failure.level + 1} after step {heal}")
    journey = drive.game["journey"]
    print(f"{name}: {len(actions)} -> {len(drive.actions)} actions, ending in {journey['place']} "
          f"at {journey['stage']} with level {drive.game.ally['level']}")
    return drive.actions


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("logs", nargs="*", default=LOGS)
    options = parser.parse_args()
    for name in options.logs:
        fresh = await rerecord(options.reference, name)
        (RED / name).write_text(json.dumps(fresh))


if __name__ == "__main__":
    asyncio.run(main())
