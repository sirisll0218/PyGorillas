import math
import random
import sys
import pygame
from pathlib import Path

def resource_path(relative: str) -> str:
    """
    Get absolute path to resource, works for dev and for PyInstaller one-folder builds.
    In one-folder builds, PyInstaller may place data files under _internal/.
    """
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent  # dist\PyGorillas
        # If assets are bundled under _internal, use that as the base
        if (base / "_internal").exists():
            base = base / "_internal"
    else:
        base = Path(__file__).resolve().parent
    return str(base / relative)


def make_background(w, h, seed=1):
    rng = random.Random(seed)
    bg = pygame.Surface((w, h)).convert()

    # Vertical gradient: top -> bottom
    top = (10, 10, 25)
    bot = (40, 20, 50)
    for y in range(h):
        t = y / (h - 1)
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        pygame.draw.line(bg, (r, g, b), (0, y), (w, y))

    # Stars (simple)
    star_count = int(w * h * 0.00015)  # tweak density
    for _ in range(star_count):
        x = rng.randrange(w)
        y = rng.randrange(int(h * 0.75))
        c = rng.randint(180, 255)
        bg.set_at((x, y), (c, c, c))
        # occasional twinkle (2nd pixel)
        if rng.random() < 0.08 and x + 1 < w:
            bg.set_at((x + 1, y), (c, c, c))

    # Moon with glow (cheap radial “rings”)
    mx, my = int(w * 0.15), int(h * 0.18)
    moon_r = 18
    for rr in range(60, moon_r, -1):
        a = int(40 * (1 - (rr - moon_r) / (60 - moon_r)))  # fade
        glow = pygame.Surface((rr * 2, rr * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (220, 220, 255, a), (rr, rr), rr)
        bg.blit(glow, (mx - rr, my - rr))
    pygame.draw.circle(bg, (235, 235, 255), (mx, my), moon_r)

    # Subtle haze near horizon
    haze = pygame.Surface((w, int(h * 0.25)), pygame.SRCALPHA)
    for y in range(haze.get_height()):
        a = int(80 * (y / (haze.get_height() - 1)))
        pygame.draw.line(haze, (80, 60, 110, a), (0, y), (w, y))
    bg.blit(haze, (0, int(h * 0.65)))

    return bg

pygame.init()

# ---------- Config ----------
screen_w, screen_h = 900, 600
fps = 60

gravity = 260.0   # pixels/sec^2  (tweak to taste)
wind_ax = 0.0     # pixels/sec^2  (set to random each round if you want)

bg_color = (15, 15, 25)
building_color = (60, 60, 75)
text_color = (230, 230, 235)

p1_color = (200, 120, 90)
p2_color = (90, 160, 210)
banana_color = (240, 220, 90)

screen = pygame.display.set_mode((screen_w, screen_h))
pygame.display.set_caption("PyGorillas")
pygame.display.set_icon(pygame.image.load(resource_path("assets/gorilla1.png")).convert_alpha())

gorilla_img = pygame.image.load(resource_path("assets/gorilla1.png")).convert_alpha()
gorilla_scale = 0.2
gorilla_img = pygame.transform.scale(
    gorilla_img, (gorilla_img.get_width() * gorilla_scale, gorilla_img.get_height() * gorilla_scale)  
)
gorilla_img_1 = gorilla_img
gorilla_img_2 = pygame.transform.flip(gorilla_img, True, False)

banana_img  = pygame.image.load(resource_path("assets/banana1.png")).convert_alpha()
banana_scale = 1.0  # try 0.5 if it's big
banana_img = pygame.transform.scale(
    banana_img,
    (int(banana_img.get_width() * banana_scale), int(banana_img.get_height() * banana_scale))
)
banana_radius = max(2, min(banana_img.get_width(), banana_img.get_height()) // 3)
explode_radius = 12
explosion_time = 0.2

clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 28)
big_font = pygame.font.SysFont(None, 44)
background = make_background(screen_w, screen_h, seed=42)


# ---------- Helpers ----------
def draw_text(s, x, y, fnt=font, color=text_color):
    surf = fnt.render(s, True, color)
    screen.blit(surf, (x, y))

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def pick_rooftop(buildings, side):
    # side: "left" or "right"
    n = len(buildings)
    if n < 6:
        idxs = range(n)
    else:
        if side == "left":
            idxs = range(1, max(2, n // 3))
        else:
            idxs = range(min(n - 2, 2 * n // 3), n - 1)
    i = random.choice(list(idxs))
    return buildings[i]

def circle_rect_hit(cx, cy, r, rect: pygame.Rect):
    # classic circle-rect collision
    closest_x = clamp(cx, rect.left, rect.right)
    closest_y = clamp(cy, rect.top, rect.bottom)
    dx = cx - closest_x
    dy = cy - closest_y
    return (dx*dx + dy*dy) <= r*r

def build_city_surface(buildings, w, h):
    # Per-pixel alpha surface (transparent background)
    city = pygame.Surface((w, h), pygame.SRCALPHA)
    # Draw buildings onto it (opaque)
    for b in buildings:
        pygame.draw.rect(city, (*building_color, 255), b)
    return city

def city_solid_at(city_surface, x, y):
    # bounds check
    if x < 0 or x >= city_surface.get_width() or y < 0 or y >= city_surface.get_height():
        return False
    return city_surface.get_at((int(x), int(y))).a > 0

def explode_at(city_surface, x, y, radius=explode_radius):
    # A "mask" surface the size of the explosion area
    mask = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA).convert_alpha()

    # Start fully opaque (so outside the circle does nothing)
    mask.fill((255, 255, 255, 255))

    # Draw a transparent circle (this is the part that will erase)
    pygame.draw.circle(mask, (255, 255, 255, 0), (radius, radius), radius)

    # Multiply destination by mask: inside circle alpha->0, outside stays same
    city_surface.blit(mask, (x - radius, y - radius), special_flags=pygame.BLEND_RGBA_MULT)

def spawn_explosion(x, y):
    explosions.append({"x": int(x), "y": int(y), "t": 0.0})


# ---------- World generation ----------
def generate_skyline():
    buildings = []
    x = 0
    while x < screen_w:
        bw = random.randint(30, 70)
        bh = random.randint(120, 420)
        rect = pygame.Rect(x, screen_h - bh, bw, bh)
        buildings.append(rect)
        x += bw
    return buildings

def place_gorillas(buildings):
    left_b = pick_rooftop(buildings, "left")
    right_b = pick_rooftop(buildings, "right")

    gorilla_1_rect = gorilla_img_1.get_rect()
    gorilla_1_rect.midbottom = (left_b.centerx, left_b.top)  # feet on roof

    gorilla_2_rect = gorilla_img_2.get_rect()
    gorilla_2_rect.midbottom = (right_b.centerx, right_b.top)
    gorilla_1 = {
        "x": gorilla_1_rect.centerx,
        "y": gorilla_1_rect.centery,
        "img": gorilla_img_1,
        "rect": gorilla_1_rect,
        "name": "P1",
    }
    gorilla_2 = {
        "x": gorilla_2_rect.centerx,
        "y": gorilla_2_rect.centery,
        "img": gorilla_img_2,
        "rect": gorilla_2_rect,
        "name": "P2",
    }
    return gorilla_1, gorilla_2


# ---------- Game state ----------
buildings = generate_skyline()
city_surface = build_city_surface(buildings, screen_w, screen_h)
gorilla_1, gorilla_2 = place_gorillas(buildings)

turn = 0  # 0 -> P1, 1 -> P2
phase = "angle"  # angle -> speed -> flying
typed = ""       # current input buffer
angle_deg = None
speed = None

banana = None  # dict with x,y,vx,vy,r

message = ""   # winner / miss messages
message_timer = 0.0

explosions = []  # each: {"x": int, "y": int, "t": float}


def reset_round(new_winner_msg=""):
    global background, buildings, gorilla_1, gorilla_2, city_surface
    background = make_background(screen_w, screen_h, seed=random.randint(1, 999999))
    global buildings, gorilla_1, gorilla_2, turn, phase, typed, angle_deg, speed, banana, message, message_timer
    buildings = generate_skyline()
    city_surface = build_city_surface(buildings, screen_w, screen_h)
    gorilla_1, gorilla_2 = place_gorillas(buildings)
    turn = 0
    phase = "angle"
    typed = ""
    angle_deg = None
    speed = None
    banana = None
    message = new_winner_msg
    message_timer = 2.0 if new_winner_msg else 0.0

def end_turn(msg=""):
    global turn, phase, typed, angle_deg, speed, banana, message, message_timer
    turn = 1 - turn
    phase = "angle"
    typed = ""
    angle_deg = None
    speed = None
    banana = None
    if msg:
        message = msg
        message_timer = 1.2

def current_player():
    return gorilla_1 if turn == 0 else gorilla_2

def other_player():
    return gorilla_2 if turn == 0 else gorilla_1

def launch_banana(a_deg, v):
    global banana
    shooter = current_player()
    # DOS-style: angle measured from shooter, velocity in "pixels/sec"
    a = math.radians(a_deg)
    # If P2 throws from right side, mirror the x-direction
    dir_x = 1.0 if shooter["name"] == "P1" else -1.0

    vx = dir_x * v * math.cos(a)
    vy = -v * math.sin(a)  # negative because screen y increases downward

    spawn_x = shooter["rect"].centerx
    spawn_y = shooter["rect"].top + shooter["rect"].height * 0.35

    spin_deg_per_sec = 720.0  # 2 rotations per second

    banana = {
        "x": float(spawn_x),
        "y": float(spawn_y),
        "vx": vx,
        "vy": vy,
        "r": banana_radius,
        "angle": 0.0,
        "spin": spin_deg_per_sec,
    }

# ---------- Main loop ----------
running = True
while running:
    dt = clock.tick(fps) / 1000.0

    # timers
    if message_timer > 0:
        message_timer -= dt
        if message_timer <= 0:
            message = ""

    # update explosions
    for e in explosions[:]:
        e["t"] += dt
        if e["t"] > explosion_time:  # lifetime in seconds
            explosions.remove(e)

    # ----- Events -----
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.KEYDOWN:
            # quick reset
            if event.key == pygame.K_r:
                reset_round("")
                continue

            if phase in ("angle", "speed"):
                if event.key == pygame.K_BACKSPACE:
                    typed = typed[:-1]
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if typed.strip() == "":
                        continue
                    try:
                        val = float(typed)
                    except ValueError:
                        typed = ""
                        continue

                    if phase == "angle":
                        angle_deg = clamp(val, 0.0, 90.0)
                        phase = "speed"
                        typed = ""
                    else:
                        speed = clamp(val, 20.0, 800.0)
                        # launch
                        launch_banana(angle_deg, speed)
                        phase = "flying"
                        typed = ""
                else:
                    ch = event.unicode
                    # allow digits, dot, minus (though we clamp later)
                    if ch.isdigit() or ch in ".-":
                        typed += ch

    # ----- Update physics -----
    if phase == "flying" and banana is not None:
        # integrate
        banana["vx"] += wind_ax * dt
        banana["vy"] += gravity * dt
        banana["x"] += banana["vx"] * dt
        banana["y"] += banana["vy"] * dt
        banana["angle"] = (banana["angle"] + banana["spin"] * dt) % 360.0


        bx, by, br = banana["x"], banana["y"], banana["r"]

        # out of bounds -> miss
        if bx < -50 or bx > screen_w + 50 or by > screen_h + 50 or by < -200:
            end_turn("Miss!")
        else:
            # building collision
            if city_solid_at(city_surface, bx, by):
                spawn_explosion(bx, by)
                explode_at(city_surface, int(bx), int(by), radius=explode_radius)
                end_turn("Boom!")
            else:
                # gorilla hit (simple circle-circle)
                target = other_player()
                if circle_rect_hit(bx, by, br, target["rect"]):
                    winner = current_player()["name"]
                    reset_round(f"{winner} wins!  (Press R to reroll)")
                    message_timer = 2.5

    # ----- Draw -----
    screen.blit(background, (0, 0))

    # city
    screen.blit(city_surface, (0, 0))

    # gorillas
    screen.blit(gorilla_1["img"], gorilla_1["rect"].topleft)
    screen.blit(gorilla_2["img"], gorilla_2["rect"].topleft)

    # banana
    if banana is not None and phase == "flying":
        x = int(banana["x"])
        y = int(banana["y"])
        rotated = pygame.transform.rotate(banana_img, banana["angle"])
        rect = rotated.get_rect(center=(x, y))
        screen.blit(rotated, rect.topleft)

    # draw explosions (expanding ring + flash)
    for e in explosions:
        t = e["t"] / explosion_time # normalized time (0.0 to 1.0)
        r = int(6 + 40 * t)                # radius grows
        a = int(220 * (1 - t))             # alpha fades

        # ring
        ring = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(ring, (255, 220, 120, a), (r + 1, r + 1), r, 3)
        screen.blit(ring, (e["x"] - r - 1, e["y"] - r - 1))

        # quick inner flash
        if t < 0.2:
            fr = int(10 * (1 - t / 0.2))
            flash = pygame.Surface((fr * 2 + 2, fr * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(flash, (255, 255, 255, int(a * 0.8)), (fr + 1, fr + 1), fr)
            screen.blit(flash, (e["x"] - fr - 1, e["y"] - fr - 1))

    # HUD / prompt
    p = current_player()
    draw_text(f"Turn: {p['name']}   (R = reroll city)", 12, 10)

    if phase == "angle":
        draw_text("Enter ANGLE (0–90): " + typed, 12, 40)
    elif phase == "speed":
        draw_text("Enter VELOCITY (20–800): " + typed, 12, 40)

    if message:
        # centered big message
        surf = big_font.render(message, True, text_color)
        rect = surf.get_rect(center=(screen_w//2, 90))
        screen.blit(surf, rect)

    pygame.display.flip()

pygame.quit()
sys.exit()
