#!/usr/bin/env python3
"""Render a decorative Tetris-style reveal of GitHub's actual contribution calendar."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import urllib.request
from PIL import Image, ImageDraw, ImageFont

BG = '#0B1120'
PANEL = '#101B2D'
TEXT = '#E6EDF3'
MUTED = '#91A4B7'
CYAN = '#22D3EE'
EMPTY = '#18283B'
LEVELS = {'NONE': EMPTY, 'FIRST_QUARTILE': '#104C61',
          'SECOND_QUARTILE': '#087F93', 'THIRD_QUARTILE': '#06B6D4',
          'FOURTH_QUARTILE': '#67E8F9'}
PIECES = ['#22D3EE', '#A78BFA', '#60A5FA', '#FBBF24', '#34D399', '#FB7185']
STEP, SIZE, X, Y = 17, 13, 50, 110
H = 278


def font(size, bold=False):
    try:
        return ImageFont.truetype('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf', size)
    except OSError:
        return ImageFont.load_default(size=size)


def fetch(user):
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        raise RuntimeError('GITHUB_TOKEN is required (provided by GitHub Actions).')
    query = '''query($login: String!) { user(login: $login) {
      contributionsCollection { contributionCalendar { totalContributions weeks {
        contributionDays { date weekday contributionCount contributionLevel }
      } } } } }'''
    request = urllib.request.Request('https://api.github.com/graphql',
        data=json.dumps({'query': query, 'variables': {'login': user}}).encode(),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                 'User-Agent': 'profile-contribution-tetris'})
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.load(response)
    if result.get('errors') or not result.get('data', {}).get('user'):
        raise RuntimeError('GitHub GraphQL request failed: ' + str(result.get('errors', 'user not found')))
    return result['data']['user']['contributionsCollection']['contributionCalendar']


def groups(cols):
    """Tile the calendar using L/J, O and I tetrominoes, with edge fragments."""
    bands = []
    for row in (6, 4, 2, 0):
        g = []
        for col in range(0, cols, 4):
            if row == 6:
                shapes = [[(0, 0), (1, 0), (2, 0), (3, 0)]]
            elif (col // 4 + row // 2) % 2:
                shapes = [[(0, 0), (0, 1), (1, 1), (2, 1)],
                          [(1, 0), (2, 0), (3, 0), (3, 1)]]
            else:
                shapes = [[(0, 0), (1, 0), (0, 1), (1, 1)],
                          [(2, 0), (3, 0), (2, 1), (3, 1)]]
            for shape in shapes:
                cells = [(col + dx, row + dy) for dx, dy in shape if col + dx < cols]
                if cells:
                    g.append(cells)
        bands.extend([g[::2], g[1::2]])
    return [wave for wave in bands if wave]


def render(calendar, out):
    weeks = calendar['weeks']
    cols = len(weeks)
    if not 1 <= cols <= 54:
        raise ValueError(f'Unexpected number of weeks: {cols}')
    data = {(i, d['weekday']): d for i, week in enumerate(weeks)
            for d in week['contributionDays']}
    if not data:
        raise ValueError('Empty calendar response')
    W = X + cols * STEP + 28
    out.mkdir(parents=True, exist_ok=True)
    dates = sorted(d['date'] for d in data.values())
    all_cells = {(c, r) for c in range(cols) for r in range(7)}
    title_font, normal, tiny = font(21, True), font(12), font(11)

    def frame(revealed, falling=None, progress=0, final=False):
        im = Image.new('RGB', (W, H), BG)
        draw = ImageDraw.Draw(im)
        draw.rounded_rectangle((8, 8, W - 9, H - 9), 13, fill=PANEL, outline='#24364B')
        draw.text((X, 20), 'CONTRIBUTION TETRIS', font=title_font, fill=CYAN)
        draw.text((X, 48), 'GitHub activity  /  Last 12 months', font=normal, fill=MUTED)
        subtitle = ('Actual calendar  •  ' + f"{calendar['totalContributions']:,} contributions" if final
                    else 'Falling blocks  •  Building the contribution calendar')
        draw.text((W - 24, 22), subtitle, font=normal, fill=TEXT, anchor='ra')
        # Month labels use the calendar dates, not invented labels.
        month = None
        last_label = -100
        for c, week in enumerate(weeks):
            days = week['contributionDays']
            if not days:
                continue
            day = dt.date.fromisoformat(days[0]['date'])
            if day.month != month:
                px = X + c * STEP
                if px - last_label >= 36 and px < W - 35:
                    draw.text((px, Y - 18), day.strftime('%b'), font=tiny, fill=MUTED)
                    last_label = px
                month = day.month
        for r, label in ((1, 'Mon'), (3, 'Wed'), (5, 'Fri')):
            draw.text((19, Y + r * STEP), label, font=tiny, fill=MUTED)
        for c, r in all_cells:
            x, y = X + c * STEP, Y + r * STEP
            d = data.get((c, r))
            if not d:
                continue
            fill = LEVELS[d['contributionLevel']] if (c, r) in revealed else '#142135'
            draw.rounded_rectangle((x, y, x + SIZE, y + SIZE), 3, fill=fill,
                                   outline='#21364A' if (c, r) not in revealed else fill)
        if falling:
            for i, cells in enumerate(falling):
                color = PIECES[i % len(PIECES)]
                minrow = min(r for _, r in cells)
                for c, r in cells:
                    # Each shape begins just above the grid; staggered drop then snap.
                    start_y = 67 + (r - minrow) * STEP
                    target_y = Y + r * STEP
                    t = max(0, min(1, progress * 1.18 - (i % 4) * 0.06))
                    y = round(start_y + (target_y - start_y) * t * t)
                    x = X + c * STEP
                    draw.rounded_rectangle((x, y, x + SIZE, y + SIZE), 2, fill=color)
                    draw.line((x+2, y+2, x+SIZE-2, y+2), fill='#E6EDF3', width=1)
        draw.text((X, 240), dates[0] + ' — ' + dates[-1], fill=MUTED, font=tiny)
        lx = W - 165
        draw.text((lx-29, 240), 'Less', font=tiny, fill=MUTED)
        for i, color in enumerate(LEVELS.values()):
            xx = lx + i * STEP
            draw.rounded_rectangle((xx, 239, xx+SIZE, 239+SIZE), 3, fill=color)
        draw.text((lx+5*STEP+3, 240), 'More', font=tiny, fill=MUTED)
        return im

    revealed = set()
    frames, durations = [frame(revealed)], [350]
    for wave in groups(cols):
        for step in range(1, 7):
            frames.append(frame(revealed, wave, step/6))
            durations.append(65)
        revealed.update(cell for cells in wave for cell in cells)
        frames.append(frame(revealed))
        durations.append(90)
    assert revealed == all_cells
    final = frame(all_cells, final=True)
    frames.append(final)
    durations.append(3600)
    final.save(out / 'contribution-calendar.png', optimize=True)
    frames[0].save(out / 'contribution-tetris.gif', save_all=True,
                   append_images=frames[1:], duration=durations, loop=0, optimize=True, disposal=1)
    print(f'Rendered {len(frames)} frames from {len(data)} actual calendar days.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', default='YASHWANTH-KURAPATI')
    parser.add_argument('--output', type=Path, default=Path('assets'))
    parser.add_argument('--fixture', type=Path, help='Local calendar JSON for offline testing only')
    args = parser.parse_args()
    calendar = json.loads(args.fixture.read_text()) if args.fixture else fetch(args.user)
    render(calendar, args.output)


if __name__ == '__main__':
    main()
