import math
import random
import sys
import pygame

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
    left_building = pick_rooftop(buildings, "left")
    right_building = pick_rooftop(buildings, "right")

    # gorillas as circles
    r = 16
    gorilla_1 = {
        "r": r,
        "x": left_building.centerx,
        "y": left_building.top - r,
        "color": p1_color,
        "name": "P1",
    }
    gorilla_2 = {
        "r": r,
        "x": right_building.centerx,
        "y": right_building.top - r,
        "color": p2_color,
        "name": "P2",
    }
    return gorilla_1, gorilla_2

# ---------- Game state ----------
buildings = generate_skyline()
gorilla_1, gorilla_2 = place_gorillas(buildings)

turn = 0  # 0 -> P1, 1 -> P2
phase = "angle"  # angle -> speed -> flying
typed = ""       # current input buffer
angle_deg = None
speed = None

banana = None  # dict with x,y,vx,vy,r

message = ""   # winner / miss messages
message_timer = 0.0

def reset_round(new_winner_msg=""):
    global background
    background = make_background(screen_w, screen_h, seed=random.randint(1, 999999))
    global buildings, gorilla_1, gorilla_2, turn, phase, typed, angle_deg, speed, banana, message, message_timer
    buildings = generate_skyline()
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

    banana = {
        "x": float(shooter["x"]),
        "y": float(shooter["y"] - shooter["r"] - 2),
        "vx": vx,
        "vy": vy,
        "r": 6,
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

        bx, by, br = banana["x"], banana["y"], banana["r"]

        # out of bounds -> miss
        if bx < -50 or bx > screen_w + 50 or by > screen_h + 50 or by < -200:
            end_turn("Miss!")
        else:
            # building collision
            hit_building = False
            for b in buildings:
                if circle_rect_hit(bx, by, br, b):
                    hit_building = True
                    break
            if hit_building:
                end_turn("Boom!")
            else:
                # gorilla hit (simple circle-circle)
                target = other_player()
                dx = bx - target["x"]
                dy = by - target["y"]
                if dx*dx + dy*dy <= (br + target["r"])**2:
                    # winner message, then reset
                    winner = current_player()["name"]
                    reset_round(f"{winner} wins!  (Press R to reroll)")
                    # keep message on screen for a moment
                    message_timer = 2.5

    # ----- Draw -----
    screen.blit(background, (0, 0))

    # buildings
    for b in buildings:
        pygame.draw.rect(screen, building_color, b)

    # gorillas
    pygame.draw.circle(screen, gorilla_1["color"], (int(gorilla_1["x"]), int(gorilla_1["y"])), gorilla_1["r"])
    pygame.draw.circle(screen, gorilla_2["color"], (int(gorilla_2["x"]), int(gorilla_2["y"])), gorilla_2["r"])

    # banana
    if banana is not None and phase == "flying":
        pygame.draw.circle(screen, banana_color, (int(banana["x"]), int(banana["y"])), banana["r"])

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
