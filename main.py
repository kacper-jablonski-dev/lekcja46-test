import os
import sys
import math
import random
import json
import pygame

# Initialize Pygame
pygame.init()
pygame.font.init()

# --- Game Configuration ---
WINDOW_WIDTH = 1024
WINDOW_HEIGHT = 768
FPS = 60

# Physics parameters (simulating space movement with inertia & drift)
ROTATION_SPEED = 220.0       # Degrees per second
ACCELERATION = 350.0         # Pixels per second squared (forward thrust)
REVERSE_ACCELERATION = 180.0 # Pixels per second squared (reverse thruster)
MAX_SPEED = 500.0            # Max speed clamp (pixels per second)
SPACE_DRAG = 0.988           # Inertial damping per second (very low friction for authentic space drift)

# Laser projectile configuration
LASER_SPEED = 850.0          # Pixels per second
LASER_LENGTH = 18.0          # Streak length in pixels
SHOOT_COOLDOWN = 0.3         # Seconds between shots

# Asteroid configuration (3 sizes)
ASTEROID_CONFIG = {
    "large":  {"radius": 44.0, "speed_range": (50, 90),   "vertices": 10},
    "medium": {"radius": 24.0, "speed_range": (90, 150),  "vertices": 8},
    "small":  {"radius": 12.0, "speed_range": (150, 220), "vertices": 6},
}

# Ship sprite visual size
SHIP_TARGET_SIZE = (72, 72)

# --- Leaderboard System (JSON) ---
LEADERBOARD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leaderboard.json")

DEFAULT_LEADERBOARD = [
    {"name": "AAA", "score": 2500},
    {"name": "ACE", "score": 2000},
    {"name": "TOP", "score": 1600},
    {"name": "MAX", "score": 1300},
    {"name": "SKY", "score": 1000},
    {"name": "BOB", "score": 800},
    {"name": "NEO", "score": 600},
    {"name": "SAM", "score": 400},
    {"name": "FOX", "score": 200},
    {"name": "ZAP", "score": 100},
]


def load_leaderboard():
    """Load top 10 scores from leaderboard.json, creating with defaults if missing."""
    if os.path.exists(LEADERBOARD_FILE):
        try:
            with open(LEADERBOARD_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    data.sort(key=lambda x: x.get("score", 0), reverse=True)
                    return data[:10]
        except Exception as e:
            print(f"Warning: Could not read {LEADERBOARD_FILE}: {e}")

    # Fallback to defaults and create file
    save_leaderboard(DEFAULT_LEADERBOARD)
    return [dict(entry) for entry in DEFAULT_LEADERBOARD]


def save_leaderboard(leaderboard):
    """Save top 10 scores to leaderboard.json."""
    try:
        with open(LEADERBOARD_FILE, "w", encoding="utf-8") as f:
            json.dump(leaderboard[:10], f, indent=2)
    except Exception as e:
        print(f"Warning: Could not write {LEADERBOARD_FILE}: {e}")


def is_high_score(score, leaderboard):
    """Check if current score qualifies for top 10."""
    if score <= 0:
        return False
    if len(leaderboard) < 10:
        return True
    return score >= leaderboard[-1].get("score", 0)


def add_high_score(name, score, leaderboard):
    """Add a new high score entry, keep top 10, and save to json."""
    clean_name = (name.upper() + "AAA")[:3]
    entry = {"name": clean_name, "score": score}
    leaderboard.append(entry)
    leaderboard.sort(key=lambda x: x.get("score", 0), reverse=True)
    leaderboard[:] = leaderboard[:10]
    save_leaderboard(leaderboard)
    return entry


def get_spawn_rate(score):
    """
    Exponential function: spawn rate of asteroids increases exponentially as score increases.
    Returns asteroids to spawn per second.
    Formula: Rate(score) = base_rate * e^(k * score)
    """
    base_rate = 0.25          # ~1 asteroid every 4.0 seconds at score 0
    k = 0.00035               # Exponential growth factor
    max_rate = 2.5            # Upper safety cap (~2.5 asteroids/sec at very high scores)
    return min(max_rate, base_rate * math.exp(k * score))


def get_spawn_interval(score):
    """
    Time in seconds between asteroid spawns (inverse of exponential spawn rate).
    """
    return 1.0 / get_spawn_rate(score)


def point_to_segment_distance_sq(p, a, b):
    """Squared distance from point p to line segment ab."""
    ab = b - a
    ab_len_sq = ab.length_squared()
    if ab_len_sq == 0:
        return (p - a).length_squared()
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab_len_sq))
    projection = a + ab * t
    return (p - projection).length_squared()


class Particle:
    """Thruster exhaust, space dust, and asteroid break particles."""
    def __init__(self, pos, velocity, color, size, lifetime):
        self.pos = pygame.math.Vector2(pos)
        self.velocity = pygame.math.Vector2(velocity)
        self.color = color
        self.size = size
        self.initial_size = size
        self.lifetime = lifetime
        self.max_lifetime = lifetime

    def update(self, dt):
        self.pos += self.velocity * dt
        self.lifetime -= dt
        progress = max(0.0, self.lifetime / self.max_lifetime)
        self.size = max(1.0, self.initial_size * progress)
        return self.lifetime > 0

    def draw(self, surface):
        alpha = int(255 * max(0.0, min(1.0, self.lifetime / self.max_lifetime)))
        glow_surf = pygame.Surface((int(self.size * 2), int(self.size * 2)), pygame.SRCALPHA)
        color_with_alpha = (*self.color[:3], alpha)
        pygame.draw.circle(glow_surf, color_with_alpha, (int(self.size), int(self.size)), int(self.size))
        surface.blit(glow_surf, self.pos - pygame.math.Vector2(self.size, self.size), special_flags=pygame.BLEND_ADD)


def create_debris(pos, size, particles_list):
    """Sparks and rock debris particles when an asteroid breaks."""
    count = 14 if size == "large" else (9 if size == "medium" else 5)
    for _ in range(count):
        angle = random.uniform(0, 360)
        speed = random.uniform(50, 200)
        vel = pygame.math.Vector2(speed, 0).rotate(angle)
        color = random.choice([
            (180, 195, 215),  # light stone
            (120, 135, 155),  # medium stone
            (255, 215, 100),  # impact spark
            (240, 240, 250)   # white spark
        ])
        p_size = random.uniform(1.5, 3.5)
        lifetime = random.uniform(0.2, 0.45)
        particles_list.append(Particle(pos, vel, color, p_size, lifetime))


class Starfield:
    """Multi-layer starfield to provide visual reference for space drift."""
    def __init__(self, width, height, count=120):
        self.width = width
        self.height = height
        self.stars = []
        for _ in range(count):
            layer = random.choices([1, 2, 3], weights=[0.6, 0.3, 0.1])[0]
            x = random.uniform(0, width)
            y = random.uniform(0, height)
            speed_factor = layer * 0.15
            brightness = random.randint(100, 160) if layer == 1 else (random.randint(170, 220) if layer == 2 else 255)
            size = layer
            self.stars.append([x, y, speed_factor, brightness, size])

    def update(self, ship_vel, dt):
        for star in self.stars:
            star[0] -= ship_vel.x * star[2] * dt
            star[1] -= ship_vel.y * star[2] * dt

            if star[0] < 0:
                star[0] += self.width
            elif star[0] > self.width:
                star[0] -= self.width
            if star[1] < 0:
                star[1] += self.height
            elif star[1] > self.height:
                star[1] -= self.height

    def draw(self, surface):
        for star in self.stars:
            color = (star[3], star[3], min(255, int(star[3] * 1.1)))
            if star[4] == 1:
                surface.set_at((int(star[0]), int(star[1])), color)
            else:
                pygame.draw.circle(surface, color, (int(star[0]), int(star[1])), star[4])


class Laser:
    """Laser projectile: a single white streak that travels until reaching the edge of the map."""
    def __init__(self, pos, heading):
        self.pos = pygame.math.Vector2(pos)
        self.heading = pygame.math.Vector2(heading).normalize()
        self.speed = LASER_SPEED
        self.length = LASER_LENGTH

    def update(self, dt):
        self.pos += self.heading * self.speed * dt

    def is_off_screen(self, width, height):
        # Despawns when reaching the edge of the map
        return (self.pos.x < 0 or self.pos.x > width or
                self.pos.y < 0 or self.pos.y > height)

    def draw(self, surface):
        tail_pos = self.pos - self.heading * self.length
        pygame.draw.line(
            surface,
            (255, 255, 255),
            (int(self.pos.x), int(self.pos.y)),
            (int(tail_pos.x), int(tail_pos.y)),
            2
        )


class Asteroid:
    """
    Asteroid with 3 sizes:
    - Large: breaks into 3 mediums
    - Medium: breaks into 3 smalls
    - Small: does not break
    """
    def __init__(self, x, y, size="large", velocity=None):
        self.pos = pygame.math.Vector2(x, y)
        self.size = size
        cfg = ASTEROID_CONFIG[size]
        self.radius = cfg["radius"]

        if velocity is None:
            speed = random.uniform(*cfg["speed_range"])
            angle = random.uniform(0, 360)
            self.velocity = pygame.math.Vector2(speed, 0).rotate(angle)
        else:
            self.velocity = pygame.math.Vector2(velocity)

        self.angle = random.uniform(0, 360)
        self.rot_speed = random.uniform(-40, 40)

        # Generate jagged polygon offsets for authentic asteroid shape
        self.shape_offsets = []
        n = cfg["vertices"]
        for i in range(n):
            rad = (2 * math.pi * i) / n
            r = self.radius * random.uniform(0.75, 1.25)
            self.shape_offsets.append((r * math.cos(rad), r * math.sin(rad)))

    def update(self, dt, screen_width, screen_height):
        self.pos += self.velocity * dt
        self.angle += self.rot_speed * dt

        # Screen wrap-around with margin
        margin = self.radius + 10
        if self.pos.x < -margin:
            self.pos.x = screen_width + margin
        elif self.pos.x > screen_width + margin:
            self.pos.x = -margin

        if self.pos.y < -margin:
            self.pos.y = screen_height + margin
        elif self.pos.y > screen_height + margin:
            self.pos.y = -margin

    def break_up(self):
        """Break this asteroid: Large -> 3 mediums, Medium -> 3 smalls, Small -> does not break."""
        if self.size == "large":
            next_size = "medium"
        elif self.size == "medium":
            next_size = "small"
        else:
            return []  # Small does not break

        cfg = ASTEROID_CONFIG[next_size]
        children = []
        base_angle = random.uniform(0, 360)
        # Break into THREE smaller asteroids spread outwards
        for i in range(3):
            angle_deg = base_angle + (i * 120.0) + random.uniform(-20, 20)
            speed = random.uniform(*cfg["speed_range"])
            vel = pygame.math.Vector2(speed, 0).rotate(angle_deg)
            offset = vel.normalize() * (self.radius * 0.35)
            children.append(Asteroid(self.pos.x + offset.x, self.pos.y + offset.y, size=next_size, velocity=vel))
        return children

    def draw(self, surface):
        cos_a = math.cos(math.radians(self.angle))
        sin_a = math.sin(math.radians(self.angle))
        points = []
        for ox, oy in self.shape_offsets:
            rx = ox * cos_a - oy * sin_a
            ry = ox * sin_a + oy * cos_a
            points.append((int(self.pos.x + rx), int(self.pos.y + ry)))

        pygame.draw.polygon(surface, (36, 42, 54), points)
        pygame.draw.polygon(surface, (170, 185, 205), points, width=2)


def spawn_asteroid(screen_width, screen_height):
    """Spawn a large asteroid at the edge of the map moving inward."""
    edge = random.choice(["top", "bottom", "left", "right"])
    margin = 40
    if edge == "top":
        x = random.uniform(0, screen_width)
        y = -margin
    elif edge == "bottom":
        x = random.uniform(0, screen_width)
        y = screen_height + margin
    elif edge == "left":
        x = -margin
        y = random.uniform(0, screen_height)
    else:
        x = screen_width + margin
        y = random.uniform(0, screen_height)

    target = pygame.math.Vector2(
        random.uniform(screen_width * 0.2, screen_width * 0.8),
        random.uniform(screen_height * 0.2, screen_height * 0.8)
    )
    spawn_pos = pygame.math.Vector2(x, y)
    direction = (target - spawn_pos).normalize()
    speed = random.uniform(*ASTEROID_CONFIG["large"]["speed_range"])
    return Asteroid(x, y, size="large", velocity=direction * speed)


class SpaceShip:
    def __init__(self, x, y, image_path):
        raw_image = pygame.image.load(image_path).convert_alpha()
        self.original_image = pygame.transform.smoothscale(raw_image, SHIP_TARGET_SIZE)

        self.pos = pygame.math.Vector2(x, y)
        self.velocity = pygame.math.Vector2(0, 0)
        self.angle = 0.0  # 0 degrees points straight UP (0, -1)
        self.radius = SHIP_TARGET_SIZE[0] // 2

        self.is_thrusting_forward = False
        self.is_thrusting_backward = False
        self.shoot_cooldown = 0.0
        self.invulnerable_timer = 0.0

        self.particles = []

    @property
    def heading(self):
        """Unit vector in the direction the ship is currently pointing."""
        return pygame.math.Vector2(0, -1).rotate(-self.angle)

    def handle_input(self, keys, dt):
        # Turn Left / Right
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.angle += ROTATION_SPEED * dt
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.angle -= ROTATION_SPEED * dt

        self.angle %= 360.0

        # Thrust Forward / Backward
        self.is_thrusting_forward = keys[pygame.K_UP] or keys[pygame.K_w]
        self.is_thrusting_backward = keys[pygame.K_DOWN] or keys[pygame.K_s]

        heading_dir = self.heading

        if self.is_thrusting_forward:
            self.velocity += heading_dir * ACCELERATION * dt
            self._emit_engine_particles(heading_dir, is_forward=True)

        if self.is_thrusting_backward:
            self.velocity -= heading_dir * REVERSE_ACCELERATION * dt
            self._emit_engine_particles(heading_dir, is_forward=False)

    def shoot(self):
        """Spawn a laser streak from the nose of the ship."""
        nose_offset = self.heading * (self.radius * 0.95)
        spawn_pos = self.pos + nose_offset
        return Laser(spawn_pos, self.heading)

    def _emit_engine_particles(self, heading_dir, is_forward=True):
        """Emit thrust plasma particles from thrusters."""
        if is_forward:
            rear_offset = pygame.math.Vector2(0, self.radius * 0.85).rotate(-self.angle)
            spawn_pos = self.pos + rear_offset

            for _ in range(2):
                spread_angle = random.uniform(-18, 18)
                exhaust_dir = (-heading_dir).rotate(spread_angle)
                exhaust_speed = random.uniform(160, 260)
                vel = (exhaust_dir * exhaust_speed) + (self.velocity * 0.4)
                color = random.choice([
                    (255, 230, 80),   # Bright yellow
                    (255, 120, 30),   # Orange
                    (100, 200, 255),  # Cyan plasma core
                    (255, 60, 20)     # Red-orange
                ])
                size = random.uniform(2.5, 4.5)
                lifetime = random.uniform(0.18, 0.32)
                self.particles.append(Particle(spawn_pos, vel, color, size, lifetime))
        else:
            front_offset = pygame.math.Vector2(0, -self.radius * 0.75).rotate(-self.angle)
            spawn_pos = self.pos + front_offset
            for _ in range(1):
                spread_angle = random.uniform(-40, 40)
                exhaust_dir = heading_dir.rotate(spread_angle)
                exhaust_speed = random.uniform(80, 140)
                vel = (exhaust_dir * exhaust_speed) + (self.velocity * 0.3)
                color = (180, 220, 255)  # Cool RCS vapor
                size = random.uniform(2.0, 3.5)
                lifetime = random.uniform(0.12, 0.22)
                self.particles.append(Particle(spawn_pos, vel, color, size, lifetime))

    def update(self, dt, screen_width, screen_height):
        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= dt

        if self.invulnerable_timer > 0:
            self.invulnerable_timer -= dt

        # Update thruster particles
        self.particles = [p for p in self.particles if p.update(dt)]

        # Space drift & drag
        effective_drag = SPACE_DRAG ** dt
        self.velocity *= effective_drag

        # Clamp max speed
        current_speed = self.velocity.length()
        if current_speed > MAX_SPEED:
            self.velocity.scale_to_length(MAX_SPEED)

        self.pos += self.velocity * dt

        # Screen wrap-around
        margin = self.radius
        if self.pos.x < -margin:
            self.pos.x = screen_width + margin
        elif self.pos.x > screen_width + margin:
            self.pos.x = -margin

        if self.pos.y < -margin:
            self.pos.y = screen_height + margin
        elif self.pos.y > screen_height + margin:
            self.pos.y = -margin

    def draw(self, surface):
        for p in self.particles:
            p.draw(surface)

        # Flicker ship when invulnerable
        if self.invulnerable_timer > 0:
            if int(self.invulnerable_timer * 12) % 2 == 0:
                return

        rotated_image = pygame.transform.rotate(self.original_image, self.angle)
        new_rect = rotated_image.get_rect(center=(int(self.pos.x), int(self.pos.y)))
        surface.blit(rotated_image, new_rect.topleft)


def draw_hud(surface, font, score, lives):
    """Draw game HUD: score and lives."""
    score_surf = font.render(f"SCORE: {score:06d}", True, (255, 255, 255))
    lives_surf = font.render(f"LIVES: {lives}", True, (255, 255, 255))
    surface.blit(score_surf, (24, 20))
    surface.blit(lives_surf, (24, 50))


def draw_name_entry(surface, font, big_font, small_font, score, player_name, blink_on):
    """Draw arcade-style 3-letter name input screen."""
    card_w, card_h = 500, 360
    card_x = (WINDOW_WIDTH - card_w) // 2
    card_y = (WINDOW_HEIGHT - card_h) // 2

    # Translucent card backdrop
    card_surf = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
    card_surf.fill((12, 17, 28, 235))
    pygame.draw.rect(card_surf, (255, 215, 80), card_surf.get_rect(), width=2, border_radius=10)
    surface.blit(card_surf, (card_x, card_y))

    # Title & score
    title_surf = big_font.render("NEW HIGH SCORE!", True, (255, 215, 80))
    surface.blit(title_surf, title_surf.get_rect(center=(WINDOW_WIDTH // 2, card_y + 45)))

    score_surf = font.render(f"FINAL SCORE: {score:06d}", True, (240, 245, 255))
    surface.blit(score_surf, score_surf.get_rect(center=(WINDOW_WIDTH // 2, card_y + 90)))

    prompt_surf = small_font.render("ENTER YOUR 3-LETTER INITIALS", True, (140, 180, 230))
    surface.blit(prompt_surf, prompt_surf.get_rect(center=(WINDOW_WIDTH // 2, card_y + 130)))

    # 3 Letter Entry Boxes
    box_w, box_h = 60, 72
    start_box_x = WINDOW_WIDTH // 2 - (3 * box_w + 2 * 20) // 2
    box_y = card_y + 165

    for i in range(3):
        bx = start_box_x + i * (box_w + 20)
        is_current = (i == len(player_name))
        has_letter = (i < len(player_name))

        border_color = (255, 215, 80) if (is_current or has_letter) else (60, 90, 130)
        pygame.draw.rect(surface, (20, 30, 48), (bx, box_y, box_w, box_h), border_radius=6)
        pygame.draw.rect(surface, border_color, (bx, box_y, box_w, box_h), width=2, border_radius=6)

        if has_letter:
            char_surf = big_font.render(player_name[i], True, (255, 255, 255))
            surface.blit(char_surf, char_surf.get_rect(center=(bx + box_w // 2, box_y + box_h // 2)))
        elif is_current and blink_on:
            cursor_surf = big_font.render("_", True, (255, 215, 80))
            surface.blit(cursor_surf, cursor_surf.get_rect(center=(bx + box_w // 2, box_y + box_h // 2 + 5)))

    # Hint text
    if len(player_name) == 3:
        hint_surf = font.render("Press [ENTER] to Save", True, (100, 255, 140))
    else:
        hint_surf = small_font.render("Type Letters (A-Z)  |  [BACKSPACE] to Edit", True, (170, 190, 215))
    surface.blit(hint_surf, hint_surf.get_rect(center=(WINDOW_WIDTH // 2, card_y + 285)))


def draw_leaderboard_overlay(surface, font, title_font, small_font, leaderboard, highlight_entry=None):
    """Draw Top 10 leaderboard overlay."""
    card_w, card_h = 490, 530
    card_x = (WINDOW_WIDTH - card_w) // 2
    card_y = (WINDOW_HEIGHT - card_h) // 2

    # Semi-transparent backdrop card
    card_surf = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
    card_surf.fill((12, 17, 28, 230))
    pygame.draw.rect(card_surf, (55, 90, 140), card_surf.get_rect(), width=2, border_radius=10)
    surface.blit(card_surf, (card_x, card_y))

    # Header
    title_surf = title_font.render("TOP 10 LEADERBOARD", True, (255, 215, 80))
    surface.blit(title_surf, title_surf.get_rect(center=(WINDOW_WIDTH // 2, card_y + 35)))

    # Table columns header
    header_surf = font.render("RANK   NAME     SCORE", True, (130, 175, 225))
    surface.blit(header_surf, (card_x + 60, card_y + 75))
    pygame.draw.line(surface, (45, 75, 115), (card_x + 40, card_y + 105), (card_x + card_w - 40, card_y + 105), 1)

    # Top 10 rows
    row_y = card_y + 118
    for i, entry in enumerate(leaderboard[:10], start=1):
        is_highlight = (entry is highlight_entry)
        if is_highlight:
            row_color = (255, 235, 90)  # Highlighted new entry
        elif i == 1:
            row_color = (255, 215, 80)  # 1st place
        elif i <= 3:
            row_color = (220, 235, 255)  # 2nd & 3rd
        else:
            row_color = (165, 185, 210)  # Rest

        rank_str = f"{i:2d}."
        name_str = f"{entry.get('name', '???'):3s}"
        score_str = f"{entry.get('score', 0):06d}"

        row_text = f" {rank_str}    {name_str}    {score_str}"
        if is_highlight:
            row_text += "  ◄ YOU"

        text_surf = font.render(row_text, True, row_color)
        surface.blit(text_surf, (card_x + 60, row_y))
        row_y += 31

    # Restart instructions
    restart_surf = small_font.render("Press [R] to Play Again", True, (190, 215, 245))
    surface.blit(restart_surf, restart_surf.get_rect(center=(WINDOW_WIDTH // 2, card_y + card_h - 26)))


def main():
    # Setup window and display
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Space Drift - Topdown Game")
    clock = pygame.time.Clock()

    # Asset paths
    current_dir = os.path.dirname(os.path.abspath(__file__))
    ship_image_path = os.path.join(current_dir, "ship.png")

    if not os.path.exists(ship_image_path):
        print(f"Error: ship.png not found at {ship_image_path}")
        sys.exit(1)

    start_x = WINDOW_WIDTH / 2.0
    start_y = WINDOW_HEIGHT / 2.0
    ship = SpaceShip(start_x, start_y, ship_image_path)

    starfield = Starfield(WINDOW_WIDTH, WINDOW_HEIGHT, count=140)

    # Fonts
    font = pygame.font.SysFont("Consolas", 22, bold=True)
    big_font = pygame.font.SysFont("Consolas", 36, bold=True)
    title_font = pygame.font.SysFont("Consolas", 28, bold=True)
    small_font = pygame.font.SysFont("Consolas", 15)

    # Load leaderboard from JSON
    leaderboard = load_leaderboard()

    # Game state: "PLAYING", "NAME_ENTRY", "GAME_OVER"
    game_state = "PLAYING"
    player_name = ""
    highlight_entry = None

    score = 0
    lives = 3
    show_tab_leaderboard = False

    lasers = []
    asteroids = []
    particles = []
    spawn_timer = 0.0
    blink_timer = 0.0

    # Initial asteroids
    for _ in range(3):
        asteroids.append(spawn_asteroid(WINDOW_WIDTH, WINDOW_HEIGHT))

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        dt = min(dt, 0.1)
        blink_timer += dt
        blink_on = int(blink_timer * 2.5) % 2 == 0

        # Event handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                # State: PLAYING
                elif game_state == "PLAYING":
                    if event.key == pygame.K_SPACE:
                        lasers.append(ship.shoot())
                        ship.shoot_cooldown = SHOOT_COOLDOWN
                    elif event.key == pygame.K_TAB:
                        show_tab_leaderboard = not show_tab_leaderboard
                    elif event.key == pygame.K_r:
                        ship.pos = pygame.math.Vector2(start_x, start_y)
                        ship.velocity = pygame.math.Vector2(0, 0)
                        ship.angle = 0.0

                # State: NAME_ENTRY
                elif game_state == "NAME_ENTRY":
                    if event.key == pygame.K_BACKSPACE:
                        player_name = player_name[:-1]
                    elif event.key == pygame.K_RETURN:
                        final_name = player_name if len(player_name) > 0 else "YOU"
                        highlight_entry = add_high_score(final_name, score, leaderboard)
                        game_state = "GAME_OVER"
                    else:
                        # Append uppercase letter or digit up to 3 chars
                        char = event.unicode.upper()
                        if len(player_name) < 3 and char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
                            player_name += char

                # State: GAME_OVER
                elif game_state == "GAME_OVER":
                    if event.key == pygame.K_r:
                        # Restart game
                        score = 0
                        lives = 3
                        game_state = "PLAYING"
                        player_name = ""
                        highlight_entry = None
                        show_tab_leaderboard = False
                        lasers.clear()
                        asteroids.clear()
                        particles.clear()
                        spawn_timer = 0.0
                        ship.pos = pygame.math.Vector2(start_x, start_y)
                        ship.velocity = pygame.math.Vector2(0, 0)
                        ship.angle = 0.0
                        ship.invulnerable_timer = 1.0
                        for _ in range(3):
                            asteroids.append(spawn_asteroid(WINDOW_WIDTH, WINDOW_HEIGHT))

        # Gameplay input & physics update (only when in PLAYING state)
        if game_state == "PLAYING":
            keys = pygame.key.get_pressed()
            ship.handle_input(keys, dt)

            # Continuous shooting if SPACE is held
            if keys[pygame.K_SPACE] and ship.shoot_cooldown <= 0:
                lasers.append(ship.shoot())
                ship.shoot_cooldown = SHOOT_COOLDOWN

            # Update ship & starfield
            ship.update(dt, WINDOW_WIDTH, WINDOW_HEIGHT)
            starfield.update(ship.velocity, dt)

            # Exponential spawn rate
            spawn_interval = get_spawn_interval(score)
            spawn_timer += dt
            if spawn_timer >= spawn_interval:
                spawn_timer = 0.0
                asteroids.append(spawn_asteroid(WINDOW_WIDTH, WINDOW_HEIGHT))

            # Update asteroids
            for asteroid in asteroids:
                asteroid.update(dt, WINDOW_WIDTH, WINDOW_HEIGHT)

            # Update lasers
            for laser in lasers:
                laser.update(dt)
            lasers = [laser for laser in lasers if not laser.is_off_screen(WINDOW_WIDTH, WINDOW_HEIGHT)]

            # Laser - Asteroid collisions
            for laser in lasers[:]:
                laser_head = laser.pos
                laser_tail = laser.pos - laser.heading * laser.length
                hit_asteroid = None
                for asteroid in asteroids:
                    dist_sq = point_to_segment_distance_sq(asteroid.pos, laser_tail, laser_head)
                    if dist_sq <= (asteroid.radius + 3) ** 2:
                        hit_asteroid = asteroid
                        break

                if hit_asteroid:
                    if laser in lasers:
                        lasers.remove(laser)
                    score += 100  # Each break gives 100 points
                    create_debris(hit_asteroid.pos, hit_asteroid.size, particles)
                    pieces = hit_asteroid.break_up()
                    if hit_asteroid in asteroids:
                        asteroids.remove(hit_asteroid)
                    asteroids.extend(pieces)

            # Ship - Asteroid collisions
            if ship.invulnerable_timer <= 0:
                for asteroid in asteroids:
                    if (ship.pos - asteroid.pos).length_squared() <= (ship.radius * 0.75 + asteroid.radius) ** 2:
                        lives -= 1
                        ship.invulnerable_timer = 2.0
                        create_debris(ship.pos, "medium", particles)
                        if lives <= 0:
                            # Game Over: check if high score beaten
                            if is_high_score(score, leaderboard):
                                game_state = "NAME_ENTRY"
                                player_name = ""
                            else:
                                game_state = "GAME_OVER"
                                highlight_entry = None
                        break

        # Always update particles & starfield drift
        particles = [p for p in particles if p.update(dt)]
        if game_state != "PLAYING":
            starfield.update(pygame.math.Vector2(0, 0), dt)

        # --- Render ---
        screen.fill((7, 9, 16))

        # Background stars
        starfield.draw(screen)

        # Debris particles
        for p in particles:
            p.draw(screen)

        # Asteroids
        for asteroid in asteroids:
            asteroid.draw(screen)

        # Lasers
        for laser in lasers:
            laser.draw(screen)

        # Ship (only when playing or invulnerable flicker)
        if game_state == "PLAYING":
            ship.draw(screen)

        # HUD overlay (score and lives)
        draw_hud(screen, font, score, lives)

        # State-dependent overlays
        if game_state == "NAME_ENTRY":
            draw_name_entry(screen, font, big_font, small_font, score, player_name, blink_on)
        elif game_state == "GAME_OVER":
            draw_leaderboard_overlay(screen, font, title_font, small_font, leaderboard, highlight_entry)
        elif show_tab_leaderboard:
            draw_leaderboard_overlay(screen, font, title_font, small_font, leaderboard)

        pygame.display.flip()

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
