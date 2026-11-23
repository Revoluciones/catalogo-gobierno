#!/usr/bin/env python3
"""Procedures core 0.1: one small format for standard operating procedures, shared by Living (Barda), Cross
and Compartido. Spec: ../CORE.md.

A procedure is a YAML file of steps. This file checks it, turns it into a BPMN 2.0 flowchart (the same five
shapes and look as Barda's procedures) and writes a page that draws it with bpmn-js.

    python3 procedures_core.py check  <folder> [--catalog <catalogo-gobierno checkout>]
    python3 procedures_core.py render <folder> <output folder> [--catalog ...]
    python3 procedures_core.py layout <file.bpmn> ... [--style page|barda]   drawing check; exit 1 on any problem
    python3 procedures_core.py tidy   <file.bpmn> ... [--write]              redraw (stdout, or in place)

check also runs the drawing check on every .bpmn file in the folder and on every flowchart it generates.

Needs Python 3.10+ and PyYAML. check_diagram and build_diagram are Barda's (portfolio/procedures.py at 1f8388c),
with two additions for long public procedures: arrows go round steps that sit in their way, and long answers
wrap. A diagram drawn here opens in Barda and the other way round.
"""
import datetime
import html
import json
import re
import sys
from collections import deque
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr


class ValidationError(Exception):
    def __init__(self, problems):
        self.messages = [problems] if isinstance(problems, str) else list(problems)
        super().__init__('; '.join(self.messages))


# ---- From Barda ------------------------------------------------------------------------------------------
BPMN = 'http://www.omg.org/spec/BPMN/20100524/MODEL'
BPMNDI = 'http://www.omg.org/spec/BPMN/20100524/DI'
MAX_DIAGRAM = 200_000  # bytes; a procedure with a hundred steps is about 60 KB
STEPS = ('task', 'userTask', 'manualTask', 'sendTask')  # a plain step, desk work, in person, a message
KINDS = {'startEvent': 'Start', **dict.fromkeys(STEPS, 'Step'), 'exclusiveGateway': 'Decision',
         'intermediateCatchEvent': 'Wait', 'callActivity': 'Another procedure', 'endEvent': 'End'}
# Section and stage colours: Barda's soft tokens (fog, acid-soft, the cap-rate sand, success-soft) plus clay.
COLOURS = {'fog': '#f1f2eb', 'acid': '#f3f5c9', 'sand': '#fff5da', 'mint': '#f0fdf4', 'clay': '#f7e6df'}
STAGE_COLOURS = {'acquire': 'sand', 'fill': 'acid', 'live': 'mint', 'leave': 'clay', 'exit': 'fog'}
SIZES = {'startEvent': (36, 36), 'endEvent': (36, 36), 'intermediateCatchEvent': (36, 36),
         'exclusiveGateway': (220, 130), **dict.fromkeys(STEPS + ('callActivity',), (240, 100))}
PITCH, GAP = 310, 64  # column centres apart; space between rows (each row as tall as its tallest shape)
# The bpmn-js icon each kind of step is drawn with, and what it means, for the key under a flowchart.
ICONS = {'userTask': ('bpmn-icon-user-task', 'Desk work'), 'manualTask': ('bpmn-icon-manual-task', 'In person'),
         'sendTask': ('bpmn-icon-send-task', 'Message'), 'exclusiveGateway': ('bpmn-icon-gateway-xor', 'Decision'),
         'intermediateCatchEvent': ('bpmn-icon-intermediate-event-catch-timer', 'Wait'),
         'callActivity': ('bpmn-icon-call-activity', 'Another procedure')}
# Shape fills: decisions in acid, the goal in success green, other ends in clay with Barda's danger red.
TONES = {'decision': ('#d9df4a', '#000000'), 'done': ('#f0fdf4', '#166534'), 'stop': ('#f7e6df', '#9b211a')}




def q(tag, ns=BPMN):
    return f'{{{ns}}}{tag}'


def check_diagram(xml, procedure_names=(), own_name=''):
    """Return the procedure's steps in reading order, or raise ValidationError listing every problem.

    procedure_names: names of the procedures an "Another procedure" step may call.
    """
    if len(xml.encode()) > MAX_DIAGRAM:
        raise ValidationError('This diagram is too large to save (over 200 KB).')
    if '<!DOCTYPE' in xml or '<!ENTITY' in xml:
        raise ValidationError('This diagram contains a document type declaration, which Barda does not accept.')
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise ValidationError('This diagram could not be read as BPMN.')
    processes = root.findall(q('process'))
    if root.tag != q('definitions') or len(processes) != 1 or root.find(q('collaboration')) is not None:
        raise ValidationError('A procedure is one BPMN process without pools.')
    problems, nodes, flows = [], {}, []
    for child in processes[0]:
        tag = child.tag.rpartition('}')[2]
        name = ' '.join((child.get('name') or '').split())
        if tag in KINDS:
            notes = child.find(q('documentation'))
            nodes[child.get('id')] = {'id': child.get('id'), 'tag': tag, 'kind': KINDS[tag], 'name': name,
                                      'notes': (notes.text or '').strip() if notes is not None else '', 'out': [], 'in': 0}
        elif tag == 'sequenceFlow':
            flows.append((child.get('sourceRef'), child.get('targetRef'), name))
        elif tag not in ('documentation', 'extensionElements', 'group'):  # a group is a coloured section box
            problems.append(f'Remove the {tag} shape{f" “{name}”" if name else ""}: procedures use start, step, '
                            'decision, wait, another procedure, end and section.')
    for source, target, label in flows:
        if source not in nodes or target not in nodes:
            problems.append('An arrow is not connected at both ends.')
            continue
        nodes[source]['out'].append((label, target))
        nodes[target]['in'] += 1
    starts = [n for n in nodes.values() if n['tag'] == 'startEvent']
    if len(starts) != 1:
        problems.append('A procedure needs exactly one start.')
    if not any(n['tag'] == 'endEvent' for n in nodes.values()):
        problems.append('A procedure needs at least one end.')
    names = {name.lower() for name in procedure_names}
    for n in nodes.values():
        label = f'“{n["name"]}”' if n['name'] else f'An unnamed {n["kind"].lower()}'
        if n['tag'] in STEPS + ('callActivity', 'exclusiveGateway', 'intermediateCatchEvent') and not n['name']:
            problems.append(f'Name every {n["kind"].lower()}.')
        if n['tag'] != 'endEvent' and not n['out']:
            problems.append(f'{label} needs an arrow to what happens next.')
        if n['tag'] == 'endEvent' and n['out']:
            problems.append(f'{label} is an end, so nothing can follow it.')
        if n['tag'] == 'startEvent' and n['in']:
            problems.append('Nothing can lead back into the start.')
        if n['tag'] == 'exclusiveGateway' and (len(n['out']) < 2 or not all(label for label, _ in n['out'])):
            problems.append(f'Decision {label} needs two or more labelled answers, such as Yes and No.')
        if n['tag'] == 'callActivity' and n['name']:
            if n['name'].lower() == own_name.lower():
                problems.append(f'{label} calls this same procedure.')
            elif n['name'].lower() not in names:
                problems.append(f'{label} should be named after another procedure; none is called that.')
    order = reachable(starts[0]['id'], nodes) if len(starts) == 1 else []
    if starts and len(order) < len(nodes):
        problems.append('Every step needs a path to it from the start.')
    reverse = {i: [] for i in nodes}
    for n in nodes.values():
        for _, target in n['out']:
            reverse[target].append(n['id'])
    ends = [i for i, n in nodes.items() if n['tag'] == 'endEvent']
    if ends and len(reachable_many(ends, reverse)) < len(nodes):
        problems.append('Every step needs a path to an end.')
    drawn = {s.get('bpmnElement') for s in root.iter(q('BPMNShape', BPMNDI))}
    if set(nodes) - drawn:
        problems.append('Some steps have no position on the drawing; open it in the editor and save again.')
    if problems:
        raise ValidationError(list(dict.fromkeys(problems)))
    for n in nodes.values():
        n['next'] = [(label, nodes[target]['name'] or nodes[target]['kind']) for label, target in n['out']]
    return [nodes[i] for i in order]


def reachable(start, nodes):
    return reachable_many([start], {i: [t for _, t in n['out']] for i, n in nodes.items()})


def reachable_many(starts, edges):
    seen, queue = list(dict.fromkeys(starts)), deque(starts)
    while queue:
        for nxt in edges[queue.popleft()]:
            if nxt not in seen:
                seen.append(nxt)
                queue.append(nxt)
    return seen


def build_diagram(name, nodes, flows, sections=()):
    """BPMN with a top-down layout. nodes, in reading order: (id, tag, name, notes[, options]); flows: (source,
    target, label), an arrow to an earlier node being a loop;
    sections: (name, colour, node ids) drawn as a coloured box behind those rows.

    tag may carry an event type: 'startEvent:message', 'intermediateCatchEvent:timer'. options: {'col': n} to
    place a node in a column, {'tone': 'stop'} for an end that is not the goal.
    The main path (each node's first arrow) runs down; a decision's other answers branch right on its row and
    run down their own column. Arrows that loop back go up the right-hand side.
    ponytail: rows are the longest path from the start, columns are first-come with optional hints, and arrows
    are routed without checking for crossings; the starters are placed by hand around that.
    """
    ids = [n[0] for n in nodes]
    tags = {n[0]: n[1].partition(':')[0] for n in nodes}
    options = {n[0]: (n[4] if len(n) > 4 else {}) for n in nodes}
    outgoing = {}
    for source, target, _ in flows:
        outgoing.setdefault(source, []).append(target)
    order = {node: i for i, node in enumerate(ids)}
    back = {(s, t) for s, t, _ in flows if order[t] <= order[s]}  # nodes are listed in reading order
    side = {(s, t) for s, t, _ in flows if tags[s] == 'exclusiveGateway' and outgoing[s][0] != t}
    row = {ids[0]: 0}
    for _ in ids:  # longest path; a decision's other answers stay on its row
        for source, target, _ in flows:
            if source in row and (source, target) not in back:
                row[target] = max(row.get(target, 0), row[source] + ((source, target) not in side))
    column, taken = {}, set()
    for node in ids:
        row.setdefault(node, max(row.values()) + 1)  # unreachable: below the rest, for the check to report
        sources = [s for s, t, _ in flows if t == node and s in column and (s, t) not in back]
        lane = options[node].get('col', min((column[s] + ((s, node) in side) for s in sources), default=0))
        while (row[node], lane) in taken:
            lane += 1
        column[node] = lane
        taken.add((row[node], lane))
    heights = {}
    for node in ids:
        heights[row[node]] = max(heights.get(row[node], 0), SIZES[tags[node]][1])
    middle, y = {}, 42
    for r in range(max(heights) + 1):
        middle[r] = y + heights.get(r, 36) // 2
        y += heights.get(r, 36) + GAP
    box = {}
    for node in ids:
        w, h = SIZES[tags[node]]
        cx, cy = 300 + column[node] * PITCH, middle[row[node]]
        box[node] = (cx - w // 2, cy - h // 2, w, h)
    body = ''
    for node, tag, label, notes, *_ in nodes:
        tag, _, event = tag.partition(':')
        body += (f'<bpmn:{tag} id="{node}" name={quoteattr(label)}>'
                 + (f'<bpmn:documentation>{escape(notes)}</bpmn:documentation>' if notes else '')
                 + (f'<bpmn:{event}EventDefinition id="{node}_{event}" />' if event else '') + f'</bpmn:{tag}>')
    body += ''.join(f'<bpmn:sequenceFlow id="Flow_{i}" sourceRef="{s}" targetRef="{t}"'
                    + (f' name={quoteattr(label)}' if label else '') + ' />' for i, (s, t, label) in enumerate(flows))
    bounds = '<dc:Bounds x="{}" y="{}" width="{}" height="{}" />'.format
    shapes, tops = '', {}
    for node, _, text, *_ in nodes:
        x, y, w, h = box[node]
        tag, label, tops[node] = tags[node], '', y
        width = min(150, 7 * len(text) + 12)  # about 7px a character at 14px; longer labels wrap
        if tag == 'endEvent':  # to the right, nothing leaves an end
            label = bounds(x + w + 10, y + h // 2 - 20, width, 40)
        elif tag.endswith('Event'):  # to the left, ending 12px before it; a decision's question is drawn inside
            label = bounds(x - 12 - width, y + h // 2 - 20, width, 40)
        tone = 'decision' if tag == 'exclusiveGateway' else options[node].get('tone', 'done' if tag == 'endEvent' else '')
        colour = f' color:background-color="{TONES[tone][0]}" color:border-color="{TONES[tone][1]}"' if tone else ''
        shapes += (f'<bpmndi:BPMNShape id="{node}_di" bpmnElement="{node}"{colour}>{bounds(x, y, w, h)}'
                   + (f'<bpmndi:BPMNLabel>{label}</bpmndi:BPMNLabel>' if label else '') + '</bpmndi:BPMNShape>')
    right = max(x + w for x, _, w, _ in box.values())
    spots = {}
    for i, (s, t, text) in enumerate(flows):
        sx, sy, sw, sh = box[s]
        tx, ty, tw, th = box[t]
        (scx, scy), (tcx, tcy) = (sx + sw // 2, sy + sh // 2), (tx + tw // 2, ty + th // 2)
        if (s, t) in back:  # out of the right side, up past everything, into the step's right side
            lane = right + 24 if column[s] < max(column.values()) else sx + sw + 24
            points = [(sx + sw, scy), (lane, scy), (lane, tcy), (tx + tw, tcy)]
        elif scx == tcx and any(column[n] == column[s] and sy < box[n][1] < ty for n in ids if n not in (s, t)):
            lane = sx - 34  # steps sit in between: go down the left of the column and in from the side
            points = [(sx, scy), (lane, scy), (lane, tcy), (tx, tcy)]
        elif scx == tcx:
            points = [(scx, sy + sh), (tcx, ty)]
        elif scy == tcy:
            points = [(sx + sw, scy), (tx, tcy)] if tcx > scx else [(sx, scy), (tx + tw, tcy)]
        elif tcx > scx:  # right, then down
            points = [(sx + sw, scy), (tcx, scy), (tcx, ty)]
        elif any(column[n] == column[s] and sy < box[n][1] < tcy for n in ids if n != s):
            lane = sx + sw + 26  # its own column is busy below: go down beside it, then left into the step
            points = [(sx + sw, scy), (lane, scy), (lane, tcy), (tx + tw, tcy)]
        else:  # down its own column, then left into the step it rejoins
            points = [(scx, sy + sh), (scx, tcy), (tx + tw, tcy)]
        # bpmn-js centres a label in its box, so the box is the text's own width, tucked against the arrow's start.
        down = points[0][0] == points[1][0]
        wide = min(7 * len(text) + 8, 130 if down else 76)  # a long answer wraps instead of covering the next step
        tall = 20 * -(-(7 * len(text) + 8) // wide) if text else 20
        if down:  # leaves downwards: just right of the arrow, under the corner
            spot = (points[0][0] + 6, points[0][1] + 4)
        elif points[1][0] < points[0][0]:  # leaves to the left: above the arrow, ending at the corner
            spot = (points[0][0] - 8 - wide, points[0][1] - 2 - tall)
        else:  # leaves to the right: just above the arrow, after the corner
            spot = (points[0][0] + 8, points[0][1] - 2 - tall)
        while text and spot in spots:  # two answers leaving the same way: the second goes under the first
            spot = (spot[0], spot[1] + spots[spot])
        if text:
            spots[spot] = tall + 4
        label = f'<bpmndi:BPMNLabel>{bounds(*spot, wide, tall)}</bpmndi:BPMNLabel>' if text else ''
        shapes += (f'<bpmndi:BPMNEdge id="Flow_{i}_di" bpmnElement="Flow_{i}">'
                   + ''.join(f'<di:waypoint x="{x}" y="{y}" />' for x, y in points) + f'{label}</bpmndi:BPMNEdge>')
    categories = ''
    for i, (title, colour, members) in enumerate(sections):
        first, last = min(column[m] for m in members), max(column[m] for m in members)
        x0 = 300 + first * PITCH - 120 - (160 if first == 0 else 30)  # room for labels left of the main path
        x1 = 300 + last * PITCH + 120 + 40
        y0 = min(min(box[m][1] for m in members) - 36, min(tops[m] for m in members) - 8)
        y1 = max(box[m][1] + box[m][3] for m in members) + 16
        body += f'<bpmn:group id="Section_{i}" categoryValueRef="Section_{i}_name" />'
        categories += (f'<bpmn:category id="Category_{i}"><bpmn:categoryValue id="Section_{i}_name" '
                       f'value={quoteattr(title)} /></bpmn:category>')
        shapes = (f'<bpmndi:BPMNShape id="Section_{i}_di" bpmnElement="Section_{i}" color:background-color="{COLOURS[colour]}" '
                  f'color:border-color="#64655f">{bounds(x0, y0, x1 - x0, y1 - y0)}'
                  f'<bpmndi:BPMNLabel>{bounds(x0 + 14, y0 + 8, 8 * len(title) + 12, 20)}</bpmndi:BPMNLabel></bpmndi:BPMNShape>') + shapes
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
            'xmlns:color="http://www.omg.org/spec/BPMN/non-normative/color/1.0" '
            'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
            'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_1" targetNamespace="https://barda.app/procedures">'
            f'{categories}<bpmn:process id="Procedure" name={quoteattr(name)} isExecutable="false">{body}</bpmn:process>'
            '<bpmndi:BPMNDiagram id="Diagram_1"><bpmndi:BPMNPlane id="Plane_1" bpmnElement="Procedure">'
            f'{shapes}</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></bpmn:definitions>\n')



# ---- Drawing check and tidy (stdlib only) -----------------------------------------------------------------
# Geometry of the BPMN drawing (DI) as bpmn-js 18 draws it, so a check here matches what people see.
# Names of circles and diamonds, and arrow answers, are "external labels": 11px text wrapped to the label box's
# width (90px when the file gives no box), top-aligned at the box's top, centred across it. A file without a box
# gets bpmn-js's default: centred under the shape (top at its bottom edge), or near the middle of the arrow.
# Step names sit inside the step box at 12px. Widths are estimated per character, on the generous side.
# Two looks: 'page' is plain bpmn-js (the command center Procedures page: names 11px, steps 12px); 'barda' is
# Barda's and the core viewer's (names 14px, steps 18px, and a decision 120px or wider has its question inside).
STYLES = {'page': {'label_char': 6.0, 'label_line': 13, 'task_char': 7.0, 'task_line': 15, 'inside': False,
                   'gateway': (56, 56), 'task_h': 80},
          'barda': {'label_char': 8.0, 'label_line': 18, 'task_char': 10.0, 'task_line': 23, 'inside': True,
                    'gateway': (220, 130), 'task_h': 100}}
ST = dict(STYLES['page'])  # the look being checked; layout_problems and tidy set it for the length of a call
LABEL_WRAP, LABEL_MAX, TASK_PAD = 90, 150, 6
FLOW_INDENT = 15  # bpmn-js puts an arrow's default label 15px off the middle of its middle segment
EVENTS = ('startEvent', 'endEvent', 'intermediateCatchEvent')
BOXES = STEPS + ('callActivity',)


def _wrap(text, width, char):
    """Greedy word wrap as bpmn-js does it; a word wider than the box stays on its own line."""
    lines, line = [], ''
    for word in text.split():
        if line and (len(line) + 1 + len(word)) * char > width:
            lines.append(line)
            line = word
        else:
            line = f'{line} {word}'.strip()
    return lines + ([line] if line else [])


def _text_box(text, x, y, width, centre=True):
    """(x, y, w, h) of label text wrapped to width, top at y; x is the box's left (text centred in it)."""
    lines = _wrap(text, width, ST['label_char'])
    w = max((len(line) for line in lines), default=0) * ST['label_char']
    return (x + (width - w) / 2 if centre else x, y, w, len(lines) * ST['label_line'])


def _overlaps(a, b, pad=0.0):
    return a[0] < b[0] + b[2] + pad and b[0] < a[0] + a[2] + pad and a[1] < b[1] + b[3] + pad and b[1] < a[1] + a[3] + pad


def _cuts(p, r, box, pad=0.0):
    """Does the segment p-r pass through box (grown by pad, or shrunk if pad < 0)? Liang-Barsky clipping."""
    x0, y0, w, h = box[0] - pad, box[1] - pad, box[2] + 2 * pad, box[3] + 2 * pad
    if w <= 0 or h <= 0:
        return False
    dx, dy = r[0] - p[0], r[1] - p[1]
    lo, hi = 0.0, 1.0
    for d, dist in ((-dx, p[0] - x0), (dx, x0 + w - p[0]), (-dy, p[1] - y0), (dy, y0 + h - p[1])):
        if d == 0:
            if dist <= 0:
                return False
        else:
            t = dist / d
            if d < 0:
                lo = max(lo, t)
            else:
                hi = min(hi, t)
            if lo >= hi:
                return False
    return True


def read_drawing(xml):
    """Nodes, arrows and their drawing: ({id: node}, [arrow]) with node {tag, name, box, label} and arrow
    {id, source, target, name, points, label}. label is the estimated text box of the name (None if no name)."""
    root = ET.fromstring(xml)
    process = root.find(q('process'))
    if process is None:
        raise ValidationError('A procedure is one BPMN process without pools.')
    nodes, arrows = {}, []
    for child in process:
        tag = child.tag.rpartition('}')[2]
        name = ' '.join((child.get('name') or '').split())
        if tag in KINDS:
            nodes[child.get('id')] = {'id': child.get('id'), 'tag': tag, 'name': name, 'box': None, 'label': None,
                                      'label_bounds': None}
        elif tag == 'sequenceFlow':
            arrows.append({'id': child.get('id'), 'source': child.get('sourceRef'), 'target': child.get('targetRef'),
                           'name': name, 'points': [], 'label': None, 'label_bounds': None})
    by_id = {a['id']: a for a in arrows}

    def bounds(el):
        b = el.find(q('Bounds', 'http://www.omg.org/spec/DD/20100524/DC')) if el is not None else None
        return tuple(float(b.get(k, 0)) for k in ('x', 'y', 'width', 'height')) if b is not None else None
    for shape in root.iter(q('BPMNShape', BPMNDI)):
        n = nodes.get(shape.get('bpmnElement'))
        if n:
            n['box'], n['label_bounds'] = bounds(shape), bounds(shape.find(q('BPMNLabel', BPMNDI)))
    for edge in root.iter(q('BPMNEdge', BPMNDI)):
        a = by_id.get(edge.get('bpmnElement'))
        if a:
            a['points'] = [(float(p.get('x')), float(p.get('y')))
                           for p in edge.findall(q('waypoint', 'http://www.omg.org/spec/DD/20100524/DI'))]
            a['label_bounds'] = bounds(edge.find(q('BPMNLabel', BPMNDI)))
    for n in nodes.values():
        inside = ST['inside'] and n['tag'] == 'exclusiveGateway' and n['box'] and n['box'][2] >= 120
        if n['name'] and n['tag'] not in BOXES and n['box'] and not inside:
            b, x, y, w, h = n['label_bounds'], *n['box']
            n['label'] = (_text_box(n['name'], b[0], b[1], b[2]) if b else
                          _text_box(n['name'], x + w / 2 - LABEL_WRAP / 2, y + h, LABEL_WRAP))
    for a in arrows:
        if a['name'] and len(a['points']) > 1:
            b = a['label_bounds']
            if b:
                a['label'] = _text_box(a['name'], b[0], b[1], b[2])
            else:  # bpmn-js getFlowLabelPosition
                pts, mid = a['points'], len(a['points']) / 2 - 1
                p, r = pts[int(mid)], pts[min(len(pts) - 1, int(mid + 1.01))]
                cx, cy = (p[0] + r[0]) / 2, (p[1] + r[1]) / 2
                if r[0] != p[0]:
                    cy -= FLOW_INDENT
                else:
                    cx += FLOW_INDENT
                x, y, w, h = _text_box(a['name'], 0, 0, LABEL_WRAP)
                a['label'] = (cx - w / 2, cy - h / 2, w, h)
    return nodes, arrows


def _styled(fn):
    def call(xml, style='page'):
        before = dict(ST)
        ST.update(STYLES[style])
        try:
            return fn(xml)
        finally:
            ST.clear()
            ST.update(before)
    call.__name__, call.__doc__, call.__wrapped__ = fn.__name__, fn.__doc__, fn
    return call


@_styled
def layout_problems(xml):
    """Every place the drawing is hard to read, as plain sentences; empty when it is clean. Pure geometry:
    names on arrows, shapes or other names, arrows through shapes, overlapping shapes, step names too long.
    style='barda' checks it as Barda draws it (bigger text, questions inside large diamonds)."""
    nodes, arrows = read_drawing(xml)
    problems = []
    title = lambda n: f'“{n["name"][:50]}”' if n['name'] else f'the {KINDS[n["tag"]].lower()}'  # noqa: E731
    say_arrow = lambda a: (f'the arrow “{a["name"]}”' if a['name'] else  # noqa: E731
                           f'the arrow from {title(nodes[a["source"]])}' if a['source'] in nodes else 'an arrow')
    for n in nodes.values():
        if not n['box']:
            problems.append(f'{title(n)} has no place on the drawing.')
    shapes = [n for n in nodes.values() if n['box']]
    near = lambda pt, b: b[0] - 3 <= pt[0] <= b[0] + b[2] + 3 and b[1] - 3 <= pt[1] <= b[1] + b[3] + 3  # noqa: E731
    for a in arrows:
        s, t = nodes.get(a['source']), nodes.get(a['target'])
        if not (s and t and s['box'] and t['box']):
            continue
        if len(a['points']) < 2 or not near(a['points'][0], s['box']) or not near(a['points'][-1], t['box']):
            problems.append(f'{say_arrow(a)[0].upper()}{say_arrow(a)[1:]} to {title(t)} is not drawn between its '
                            'two shapes.')
    labels = [(f'The name of {title(n)}', n['label'], n['id'], n) for n in shapes if n['label']]
    labels += [(f'The answer “{a["name"]}”', a['label'], a['id'], a) for a in arrows if a['label']]
    for what, box, own, item in labels:
        given = item['label_bounds']
        if given and max(len(w) for w in item['name'].split()) * 6.0 + 4 > given[2]:  # 6px: the page's widest
            problems.append(f'{what} has a box narrower than its longest word, so it breaks mid-word (a much '
                            'narrower box can freeze the page).')
        for a in arrows:
            if any(_cuts(p, r, box, 2) for p, r in zip(a['points'], a['points'][1:])):
                problems.append(f'{what} lies on {"its own arrow" if a["id"] == own else say_arrow(a)}.')
        for n in shapes:
            if _overlaps(box, n['box'], -0.5):
                problems.append(f'{what} lies on {"its own shape" if n["id"] == own else title(n)}.')
    for i, (what, box, _, _) in enumerate(labels):
        for other, box2, _, _ in labels[i + 1:]:
            if _overlaps(box, box2, 2):
                problems.append(f'{what} and {other[0].lower()}{other[1:]} overlap.')
    for a in arrows:
        for n in shapes:
            if n['id'] in (a['source'], a['target']):
                continue
            if any(_cuts(p, r, n['box'], -2) for p, r in zip(a['points'], a['points'][1:])):
                problems.append(f'{say_arrow(a)[0].upper()}{say_arrow(a)[1:]} passes through {title(n)}.')
    for i, n in enumerate(shapes):
        for m in shapes[i + 1:]:
            if _overlaps(n['box'], m['box'], -1):
                problems.append(f'{title(n)} and {title(m)} overlap.')
    for n in shapes:
        if n['tag'] in BOXES and n['name']:
            x, y, w, h = n['box']
            lines = _wrap(n['name'], w - 2 * TASK_PAD, ST['task_char'])
            if len(lines) * ST['task_line'] > h - 2 * TASK_PAD or max(len(s) for s in lines) * ST['task_char'] > w - 2 * TASK_PAD:
                problems.append(f'The step name {title(n)} is too long for its box; shorten it (detail goes in the '
                                'notes) or widen the box.')
    return list(dict.fromkeys(problems))


# Tidy: the same process, drawn again. Main path (each node's first arrow) straight down one column; other
# answers branch into columns to the right; arrows that skip ahead or loop back run in lanes between columns,
# outside the shapes they pass; names of circles and diamonds beside the shape where no arrow is (left first);
# answers beside their arrow near its start.
TIDY = {'task_w': 240, 'wide_w': 300, 'event': 36, 'row_gap': 56, 'col_gap': 150,
        'left': 200, 'top': 40, 'lane': 16, 'lane_step': 14}


def _order(nodes, arrows):
    """Reading order (depth first, first arrow first), the depth-first tree and the arrows that close a loop."""
    out = {i: [a for a in arrows if a['source'] == i and a['target'] in nodes] for i in nodes}
    starts = [i for i, n in nodes.items() if n['tag'] == 'startEvent'] or list(nodes)[:1]
    order, parent, back, state = [], {}, set(), {}

    def visit(i):
        state[i] = 'open'
        order.append(i)
        for a in out[i]:
            t = a['target']
            if state.get(t) == 'open':
                back.add(a['id'])
            elif t not in state:
                parent[t] = a['id']
                visit(t)
        state[i] = 'done'
    import sys as _sys
    _sys.setrecursionlimit(max(1000, 4 * len(nodes) + 100))
    for s in starts + list(nodes):
        if s not in state:
            visit(s)
    return order, parent, back, out


def _sizes(n, cfg):
    if n['tag'] == 'exclusiveGateway':
        return ST['gateway']
    if n['tag'] in EVENTS:
        return cfg['event'], cfg['event']
    for w in (cfg['task_w'], cfg['wide_w']):
        lines = _wrap(n['name'], w - 2 * TASK_PAD, ST['task_char'])
        if len(lines) <= 3 and max((len(s) for s in lines), default=0) * ST['task_char'] <= w - 2 * TASK_PAD:
            return w, ST['task_h']
    lines = _wrap(n['name'], cfg['wide_w'] - 2 * TASK_PAD, ST['task_char'])
    longest = max(len(s) for s in lines) * ST['task_char'] + 2 * TASK_PAD
    return max(cfg['wide_w'], int(longest) + 2), max(ST['task_h'], len(lines) * ST['task_line'] + 2 * TASK_PAD + 8)


def _layout(nodes, arrows, cfg, sections=()):
    order, parent, back, out = _order(nodes, arrows)
    fwd = [a for a in arrows if a['id'] not in back and a['source'] in nodes and a['target'] in nodes]
    row = {i: 0 for i in nodes}
    band = {m: k for k, (_, members, _) in enumerate(sections) for m in members if m in nodes}
    for _ in range(len(nodes) * (len(sections) + 1)):  # longest path over forward arrows; a section starts below
        changed = False  # every row of the sections before it, so section boxes never share a row
        for a in fwd:
            if row[a['target']] < row[a['source']] + 1:
                row[a['target']], changed = row[a['source']] + 1, True
        last = {}
        for i, k in band.items():
            last[k] = max(last.get(k, -1), row[i])
        for i, k in band.items():
            floor = max((last[j] + 1 for j in last if j < k), default=0)
            if row[i] < floor:
                row[i], changed = floor, True
        if not changed:
            break
    col, cells = {}, set()
    first = {i: next((a['id'] for a in out[i] if a['id'] not in back), None) for i in nodes}
    for i in order:
        if i not in parent:  # a start (or unreachable): first free column on its row
            c = 0
            while (row[i], c) in cells:
                c += 1
            col[i] = c
            cells.add((row[i], c))
            continue
        a = next(x for x in arrows if x['id'] == parent[i])
        s = a['source']
        down = [(r, col[s]) for r in range(row[s] + 1, row[i] + 1)]
        if first[s] == a['id'] and not any(c in cells for c in down):
            col[i] = col[s]
            cells.update(down)
            continue
        c = col[s] + 1
        while (row[s], c) in cells or any((r, c) in cells for r in range(row[s] + 1, row[i] + 1)):
            c += 1  # a cell in between taken on the source's row is fine: the arrow then runs in the gap below
        col[i] = c
        cells.update((row[s], k) for k in range(col[s] + 1, c + 1))
        cells.update((r, c) for r in range(row[s] + 1, row[i] + 1))
    size = {i: _sizes(n, cfg) for i, n in nodes.items()}
    ncol, nrow = max(col.values()) + 1, max(row.values()) + 1
    col_w = [max([size[i][0] for i in nodes if col[i] == c] + [cfg['task_w']]) for c in range(ncol)]
    row_h = [max([size[i][1] for i in nodes if row[i] == r] + [cfg['event']]) for r in range(nrow)]
    cx, x = [], cfg['left']
    for w in col_w:
        cx.append(x + w / 2)
        x += w + cfg['col_gap']
    cy, y = [], cfg['top']
    for h in row_h:
        cy.append(y + h / 2)
        y += h + cfg['row_gap']
    box = {}
    for i in nodes:
        w, h = size[i]
        box[i] = (round(cx[col[i]] - w / 2), round(cy[row[i]] - h / 2), w, h)
    return order, back, out, row, col, box, col_w, cx, cy, row_h


def _route(nodes, arrows, back, out, row, col, box, col_w, cx, cy, row_h, cfg):
    """Orthogonal arrows. Tree arrows go straight down or right-then-down; the others try a few routes and keep
    the one that crosses no shape and runs along no other arrow."""
    routes, lanes = {}, []
    mid = lambda b: (b[0] + b[2] / 2, b[1] + b[3] / 2)  # noqa: E731
    others = lambda a: [b for i, b in box.items() if i not in (a['source'], a['target'])]  # noqa: E731

    def score(a, pts):
        bad = sum(100 for p, r in zip(pts, pts[1:]) for b in others(a) if _cuts(p, r, b, -2))
        bad += sum(100 for p, r in zip(pts[1:-1], pts[2:-1]) for i in (a['source'], a['target'])
                   if _cuts(p, r, box[i], -2))
        for other, opts in routes.items():
            o = next(x for x in arrows if x['id'] == other)
            if o['source'] == a['source'] or o['target'] == a['target']:
                continue
            for p, r in zip(pts, pts[1:]):  # running along (or end to end with) another arrow reads as one line
                for p2, r2 in zip(opts, opts[1:]):
                    if _same_line(p, r, (p2, r2), 8):
                        bad += 10
        (tx, ty, tw, th), (sx, sy, sw, sh) = box[a['target']], box[a['source']]
        side_answers = lambda i: nodes[i]['tag'] == 'exclusiveGateway' and len(out[i]) > 1  # noqa: E731
        if side_answers(a['target']) and pts[-1][0] == tx + tw:
            bad += 50  # keep a decision's right corner for its answers
        if side_answers(a['source']) and first[a['source']] != a['id'] and pts[0][1] == sy + sh:
            bad += 30  # the bottom corner is the first answer's
        return bad

    def lane_x(c, k):
        return cx[c] + col_w[c] / 2 + cfg['lane'] + k * cfg['lane_step']
    first = {i: next((a['id'] for a in out[i] if a['id'] not in back), None) for i in nodes}
    tree_like = []
    for a in arrows:
        s, t = a['source'], a['target']
        if s not in box or t not in box:
            continue
        (sx, sy, sw, sh), (tx, ty, tw, th) = box[s], box[t]
        (scx, scy), (tcx, tcy) = mid(box[s]), mid(box[t])
        options = []
        if a['id'] not in back and col[s] == col[t] and row[t] > row[s]:
            options.append([(scx, sy + sh), (tcx, ty)])
        if a['id'] not in back and col[t] > col[s] and row[t] > row[s]:
            options.append([(sx + sw, scy), (tcx, scy), (tcx, ty)])
            gy, lx = ty - cfg['row_gap'] / 2, lane_x(col[s], 0)
            options.append([(sx + sw, scy), (lx, scy), (lx, gy), (tcx, gy), (tcx, ty)])
        if a['id'] not in back and col[t] < col[s] and row[t] > row[s]:
            options.append([(scx, sy + sh), (scx, tcy), (tx + tw, tcy)])
            gy = ty - cfg['row_gap'] / 2
            options.append([(scx, sy + sh), (scx, gy), (tcx, gy), (tcx, ty)])
        span = range(min(row[s], row[t]), max(row[s], row[t]) + 1)
        outer = max([col[i] for i in nodes if row[i] in span] + [col[s], col[t]])
        for c in sorted({max(col[s], col[t]), outer}):
            for k in range(6):
                lx = lane_x(c, k)
                options.append([(sx + sw, scy), (lx, scy), (lx, tcy), (tx + tw, tcy)])
                if a['id'] not in back and row[t] > row[s]:
                    gy = ty - cfg['row_gap'] / 2
                    options.append([(sx + sw, scy), (lx, scy), (lx, gy), (tcx, gy), (tcx, ty)])
        if a['id'] not in back and row[t] > row[s]:
            gy = ty - cfg['row_gap'] / 2
            options.append([(scx, sy + sh), (scx, gy), (tcx, gy), (tcx, ty)])
        tree_like.append((a, options))
    # tree arrows first so the others route around them
    tree_like.sort(key=lambda ao: (ao[0]['id'] in back, first.get(ao[0]['source']) != ao[0]['id']))
    for a, options in tree_like:
        best = min(options, key=lambda pts: (score(a, pts), options.index(pts)))
        routes[a['id']] = [(round(x), round(y)) for x, y in _simplify(best)]
    return routes


def _simplify(pts):
    out = [pts[0]]
    for p in pts[1:]:
        if p == out[-1]:
            continue
        if len(out) >= 2 and (out[-2][0] == out[-1][0] == p[0] or out[-2][1] == out[-1][1] == p[1]):
            out[-1] = p
        else:
            out.append(p)
    return out


def _place_labels(nodes, arrows, box, routes):
    """Label boxes: names beside circles and diamonds (left, right, under, over), answers beside their arrow
    near its start. Each spot is tried in turn; the first that touches no arrow, shape or other name wins."""
    segs = [(a['id'], p, r) for a in arrows for p, r in zip(routes.get(a['id'], []), routes.get(a['id'], [])[1:])]
    taken, placed = [], {}

    def free(b, own=None):  # an answer keeps clear of other arrows so it is not read as theirs
        return (not any(_cuts(p, r, b, 3 if own in (None, i) else 9) for i, p, r in segs) and not any(_overlaps(b, s, 2) for s in box.values())
                and not any(_overlaps(b, t, 3) for t in taken))

    def fit(text, width):
        x, y, w, h = _text_box(text, 0, 0, width)
        return int(w + 0.999) + 10, h  # bpmn-js wraps at the box width: leave room so short words never break
    for i, n in nodes.items():
        if not n['name'] or n['tag'] in BOXES or i not in box or (
                ST['inside'] and n['tag'] == 'exclusiveGateway' and box[i][2] >= 120):  # Barda: question inside
            continue
        x, y, w, h = box[i]
        lw, lh = fit(n['name'], LABEL_MAX)
        spots = [(x - 10 - lw, y + h / 2 - lh / 2), (x + w + 10, y + h / 2 - lh / 2),
                 (x + w / 2 - lw / 2, y + h + 6), (x + w / 2 - lw / 2, y - 6 - lh),
                 (x - 10 - lw, y + h + 4), (x + w + 10, y + h + 4), (x - 10 - lw, y - 4 - lh), (x + w + 10, y - 4 - lh)]
        for lw2, lh2 in ((lw, lh), fit(n['name'], LABEL_WRAP)):
            spots2 = [(sx + (lw - lw2) if sx < x else sx, sy) for sx, sy in spots]
            got = next(((sx, sy, lw2, lh2) for sx, sy in spots2 if free((sx, sy, lw2, lh2))), None)
            if got:
                break
        got = got or (spots[0][0], spots[0][1], lw, lh)
        placed[i] = tuple(round(v) for v in got)
        taken.append(placed[i])
    for a in arrows:
        pts = routes.get(a['id'])
        if not a['name'] or not pts:
            continue
        lw, lh = fit(a['name'], LABEL_MAX)
        shared = {(p, r) for o in arrows if o['id'] != a['id'] and o['source'] == a['source']
                  for p, r in zip(routes.get(o['id'], []), routes.get(o['id'], [])[1:])}
        spots = []
        for k, (p, r) in enumerate(zip(pts, pts[1:])):
            on_shared = any(_same_line(p, r, s) for s in shared)
            cand = []
            for step in (0, 16):  # just after the corner, else a little further along
                if r[0] == p[0]:
                    y0 = p[1] + 6 + step if r[1] > p[1] else p[1] - 6 - step - lh
                    cand += [(p[0] + 8, y0), (p[0] - 8 - lw, y0)]
                else:
                    x0 = p[0] + 10 + step if r[0] > p[0] else p[0] - 10 - step - lw
                    cand += [(x0, p[1] - 5 - lh), (x0, p[1] + 5)]
            spots += [(on_shared, k, c) for c in cand]
        spots.sort(key=lambda s: (s[0], s[1]))
        got = next(((sx, sy, lw, lh) for _, _, (sx, sy) in spots if free((sx, sy, lw, lh), a['id'])), None)
        got = got or next(((sx, sy, lw, lh) for _, _, (sx, sy) in spots if free((sx, sy, lw, lh))), None)
        got = got or (spots[0][2][0], spots[0][2][1], lw, lh)
        placed[a['id']] = tuple(round(v) for v in got)
        taken.append(placed[a['id']])
    return placed


def _same_line(p, r, seg, slack=0):
    """Do two straight segments run along each other (or meet end to end within slack)?"""
    (p2, r2) = seg
    if p[0] == r[0] == p2[0] == r2[0]:
        return min(max(p[1], r[1]), max(p2[1], r2[1])) + slack > max(min(p[1], r[1]), min(p2[1], r2[1]))
    if p[1] == r[1] == p2[1] == r2[1]:
        return min(max(p[0], r[0]), max(p2[0], r2[0])) + slack > max(min(p[0], r[0]), min(p2[0], r2[0]))
    return False


def _draw(xml, nodes, arrows, box, routes, labels, sections=()):
    """xml with only the inside of its BPMNPlane rewritten; the process, ids, names and arrows stay as they are."""
    decls = {}  # namespace -> prefix, from the root and the plane (a tidied plane declares its own)
    for tag in re.findall(r'<(?:\w+:)?(?:definitions|BPMNDiagram|BPMNPlane)\b[^>]*>', xml):
        decls.update((uri, p) for p, uri in re.findall(r'xmlns:(\w+)="([^"]+)"', tag))
    dc, di = decls.get('http://www.omg.org/spec/DD/20100524/DC'), decls.get('http://www.omg.org/spec/DD/20100524/DI')
    color = decls.get('http://www.omg.org/spec/BPMN/non-normative/color/1.0')
    plane = re.search(r'<((?:\w+:)?)BPMNPlane\b([^>]*?)(/?)>', xml)
    old = {}
    if plane:
        pre = plane.group(1)
        end = xml.find(f'</{pre}BPMNPlane>', plane.end()) if not plane.group(3) else plane.end()
        inner = xml[plane.end():end] if not plane.group(3) else ''
        for m in re.finditer(r'<(?:\w+:)?BPMN(?:Shape|Edge)\b([^>]*?)/?>', inner):
            attrs = dict(re.findall(r'([\w:.-]+)="([^"]*)"', m.group(1)))
            if attrs.get('bpmnElement'):
                old[attrs['bpmnElement']] = attrs
    else:
        pre = 'bpmndi:'
    extra = ''
    if not dc:
        dc, extra = 'dc', extra + ' xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"'
    if not di:
        di, extra = 'di', extra + ' xmlns:di="http://www.omg.org/spec/DD/20100524/DI"'
    if not color:
        color, extra = 'color', extra + ' xmlns:color="http://www.omg.org/spec/BPMN/non-normative/color/1.0"'
    bounds = lambda b: f'<{dc}:Bounds x="{b[0]}" y="{b[1]}" width="{b[2]}" height="{b[3]}" />'  # noqa: E731
    keep = lambda el: ''.join(f' {k}={quoteattr(v)}' for k, v in old.get(el, {}).items()  # noqa: E731
                              if k not in ('id', 'bpmnElement', 'isMarkerVisible', 'isHorizontal'))
    body = ''
    for gid, members, title in sections:  # coloured section boxes, redrawn round the same steps, behind them
        if not members:
            continue
        parts = [box[m] for m in members] + [labels[m] for m in members if m in labels]
        x0, y0 = min(b[0] for b in parts) - 24, min(b[1] for b in parts) - 40
        x1, y1 = max(b[0] + b[2] for b in parts) + 24, max(b[1] + b[3] for b in parts) + 16
        sid = old.get(gid, {}).get('id') or f'{gid}_di'
        body += (f'<{pre}BPMNShape id={quoteattr(sid)} bpmnElement={quoteattr(gid)}{keep(gid)}>'
                 f'{bounds((round(x0), round(y0), round(x1 - x0), round(y1 - y0)))}<{pre}BPMNLabel>'
                 f'{bounds((round(x0) + 14, round(y0) + 8, int(len(title) * ST["label_char"]) + 14, 20))}'
                 f'</{pre}BPMNLabel></{pre}BPMNShape>')
    for i, n in nodes.items():
        attrs = keep(i)
        if 'color' not in attrs and 'fill' not in attrs:
            tone = 'decision' if n['tag'] == 'exclusiveGateway' else 'done' if n['tag'] == 'endEvent' else ''
            attrs += f' {color}:background-color="{TONES[tone][0]}" {color}:border-color="{TONES[tone][1]}"' if tone else ''
        sid = old.get(i, {}).get('id') or f'{i}_di'
        body += (f'<{pre}BPMNShape id={quoteattr(sid)} bpmnElement={quoteattr(i)}{attrs}'
                 + (' isMarkerVisible="true"' if n['tag'] == 'exclusiveGateway' else '') + f'>{bounds(box[i])}'
                 + (f'<{pre}BPMNLabel>{bounds(labels[i])}</{pre}BPMNLabel>' if i in labels else '')
                 + f'</{pre}BPMNShape>')
    for a in arrows:
        if a['id'] not in routes:
            continue
        eid = old.get(a['id'], {}).get('id') or f'{a["id"]}_di'
        body += (f'<{pre}BPMNEdge id={quoteattr(eid)} bpmnElement={quoteattr(a["id"])}{keep(a["id"])}>'
                 + ''.join(f'<{di}:waypoint x="{x}" y="{y}" />' for x, y in routes[a['id']])
                 + (f'<{pre}BPMNLabel>{bounds(labels[a["id"]])}</{pre}BPMNLabel>' if a['id'] in labels else '')
                 + f'</{pre}BPMNEdge>')
    if plane:
        start = plane.group(0)[:-2] + '>' if plane.group(3) else plane.group(0)
        start = start[:-1] + extra + '>' if extra else start
        return xml[:plane.start()] + start + body + f'</{pre}BPMNPlane>' + xml[end + (0 if plane.group(3) else len(f'</{pre}BPMNPlane>')):]
    pid = ET.fromstring(xml).find(q('process')).get('id')
    diagram = (f'<bpmndi:BPMNDiagram xmlns:bpmndi="{BPMNDI}" id="Diagram_tidy"><bpmndi:BPMNPlane id="Plane_tidy" '
               f'bpmnElement={quoteattr(pid)}{extra}>{body}</bpmndi:BPMNPlane></bpmndi:BPMNDiagram>')
    close = re.search(r'</(?:\w+:)?definitions>\s*$', xml)
    return xml[:close.start()] + diagram + xml[close.start():]


def _sections(xml, nodes):
    """Section boxes (bpmn:group): (id, the steps drawn inside it now, its title)."""
    root = ET.fromstring(xml)
    titles = {v.get('id'): v.get('value') or '' for v in root.iter(q('categoryValue'))}
    groups = {g.get('id'): titles.get(g.get('categoryValueRef'), '') for g in root.iter(q('group'))}
    out = []
    for shape in root.iter(q('BPMNShape', BPMNDI)):
        gid = shape.get('bpmnElement')
        b = shape.find(q('Bounds', 'http://www.omg.org/spec/DD/20100524/DC'))
        if gid in groups and b is not None:
            x, y, w, h = (float(b.get(k, 0)) for k in ('x', 'y', 'width', 'height'))
            inside = [i for i, n in nodes.items() if n['box'] and x <= n['box'][0] + n['box'][2] / 2 <= x + w
                      and y <= n['box'][1] + n['box'][3] / 2 <= y + h]
            out.append((gid, inside, groups[gid], (x + w / 2, y + h / 2)))
    owner = {}  # a step inside two overlapping boxes belongs to the one whose middle is nearest, so a redraw
    for k, (_, inside, _, (mx, my)) in enumerate(out):  # cannot make one section swallow the next
        for i in inside:
            bx, by, bw, bh = nodes[i]['box']
            d = (bx + bw / 2 - mx) ** 2 + (by + bh / 2 - my) ** 2
            if i not in owner or d < owner[i][0]:
                owner[i] = (d, k)
    out = [(gid, [i for i in inside if owner[i][1] == k], title, mid) for k, (gid, inside, title, mid) in enumerate(out)]
    return [g[:3] for g in sorted(out, key=lambda g: g[3][1])]  # top to bottom, the order the bands are laid out in


@_styled
def tidy(xml):
    """The same process with only its drawing redone, so layout_problems(result) is empty when it can be.
    Element ids, names, arrows and notes are untouched (run history is keyed on the ids)."""
    nodes, arrows = read_drawing(xml)
    arrows = [a for a in arrows if a['source'] in nodes and a['target'] in nodes]
    sections = _sections(xml, nodes)
    best = None
    for grow in (0, 1, 2):
        cfg = {**TIDY, 'row_gap': TIDY['row_gap'] + 24 * grow, 'col_gap': TIDY['col_gap'] + 60 * grow}
        order, back, out, row, col, box, col_w, cx, cy, row_h = _layout(nodes, arrows, cfg, sections)
        routes = _route(nodes, arrows, back, out, row, col, box, col_w, cx, cy, row_h, cfg)
        labels = _place_labels(nodes, arrows, box, routes)
        drawn = _draw(xml, {i: nodes[i] for i in order}, arrows, box, routes, labels, sections)
        problems = layout_problems.__wrapped__(drawn)
        if best is None or len(problems) < len(best[1]):
            best = (drawn, problems)
        if not problems:
            break
    return best[0]


# ---- The core: YAML procedures ---------------------------------------------------------------------------
REQUIRED = ('id', 'title', 'summary', 'owner', 'audience', 'status', 'last_checked', 'steps')
AUDIENCES = ('internal', 'shared', 'public')
STATUSES = {'draft': 'draft', 'reviewed': 'reviewed', 'outdated': 'outdated',  # and the catalog's Spanish words
            'borrador': 'draft', 'revisado': 'reviewed', 'desactualizado': 'outdated', 'importado': 'reviewed'}
VIA = {'desk': 'userTask', 'in-person': 'manualTask', 'message': 'sendTask'}
ENDS = ('end', 'fin')
STALE_DAYS = 180  # the same age at which a phone-menu map is treated as old
CATALOG_URL = 'https://github.com/Revoluciones/catalogo-gobierno/blob/main/'


def load(folder, catalog=None):
    """Every procedure in folder, by id, and the government procedures they point to: {id: {title, ...}}."""
    import yaml
    own = {}
    for path in sorted(Path(folder).rglob('*.yaml')):
        if path.name.startswith('_') or 'core' in path.parts:
            continue
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError as error:
            data = {'_error': ' '.join(str(error).split())}
        data = data if isinstance(data, dict) else {'_error': 'this is not a procedure file.'}
        data['_path'] = path
        own[str(data.get('id') or path.stem)] = data
    wanted = {r['id'] for p in own.values() for r in references(p)} - set(own)
    outside = {}
    if catalog:
        for path in Path(catalog).rglob('*.yaml'):
            if path.stem in wanted:
                data = yaml.safe_load(path.read_text())
                outside[path.stem] = {'title': ' '.join(data['title'].split()), 'status': data.get('status'),
                                      'last_checked': str(data.get('last_checked', '')),
                                      'url': CATALOG_URL + path.relative_to(catalog).as_posix()}
    return own, outside


def references(procedure):
    """Every other procedure this one names: hand-offs (calls, next.to) and things a step relies on (refs)."""
    steps = [s for s in procedure.get('steps') or [] if isinstance(s, dict)]
    numbers = {str(s.get('n')) for s in steps}
    for step in steps:
        if step.get('calls'):
            yield {'id': step['calls'], 'n': step.get('n')}
        for ref in step.get('refs') or []:
            yield {**(ref if isinstance(ref, dict) else {'id': ref}), 'n': step.get('n')}
        for nxt in step.get('next') or []:
            if str(nxt.get('to')) not in numbers and nxt.get('to') not in ENDS:
                yield {'id': nxt['to'], 'n': step.get('n')}


def short(text, limit=64):
    """A label for a step that has only a long description: its first clause, cut at a word."""
    first = re.split(r'(?<=[.;:])\s', text, maxsplit=1)[0].rstrip('.;:')
    return first if len(first) <= limit else first[:limit].rsplit(' ', 1)[0].rstrip(',') + '…'


def to_bpmn(procedure, titles):
    """The procedure as BPMN. titles: {id: title} of every procedure it may hand off to."""
    steps = procedure['steps']
    node = {str(s['n']): 'S_' + re.sub(r'\W', '_', str(s['n'])) for s in steps}
    nodes, flows, calls = [('Start', 'startEvent', procedure.get('starts_when', 'Start'), '')], [], 0
    default_end = False
    flows.append(('Start', node[str(steps[0]['n'])], ''))
    for i, step in enumerate(steps):
        n, kind = str(step['n']), step.get('kind', 'step')
        text = ' '.join(str(step.get('action', '')).split())
        name = step.get('name') or (titles.get(step['calls'], step['calls']) if step.get('calls') else short(text))
        notes = [f'Who: {step["actor"]}'] if step.get('actor') else []
        notes += [text] if text and text != name else []
        notes += [f'Target: {step["deadline"]}'] if step.get('deadline') else []
        notes += [f'See: {titles.get(r["id"], r["id"])}' + (f' ({r["why"]})' if r.get('why') else '')
                  for r in (x if isinstance(x, dict) else {'id': x} for x in step.get('refs') or [])]
        tag = ('callActivity' if step.get('calls') else
               {'decision': 'exclusiveGateway', 'wait': 'intermediateCatchEvent:timer', 'end': 'endEvent'}.get(
                   kind, VIA.get(step.get('via'), 'task')))
        nodes.append((node[n], tag, name, '\n'.join(notes), {'tone': 'stop'} if step.get('stop') else {}))
        if kind == 'end':
            continue
        following = [{'to': steps[i + 1]['n']}] if i + 1 < len(steps) and steps[i + 1].get('kind') != 'end' else [{'to': 'end'}]
        branches, source = step.get('next') or following, node[n]
        if len(branches) > 1 and kind != 'decision':  # an action with several outcomes: draw the question after it
            nodes.append((f'Q_{node[n]}', 'exclusiveGateway', step.get('ask', 'What happened?'), ''))
            flows.append((source, f'Q_{node[n]}', ''))
            source = f'Q_{node[n]}'
        for nxt in branches:
            to, label = str(nxt['to']), nxt.get('when', '')
            if to in node:
                flows.append((source, node[to], label))
            elif to in ENDS:
                default_end = True
                flows.append((source, 'End', label))
            else:  # hands off to another procedure, then this one is done
                calls, default_end = calls + 1, True
                nodes.append((f'Call_{calls}', 'callActivity', titles.get(to, to), ''))
                flows += [(source, f'Call_{calls}', label), (f'Call_{calls}', 'End', '')]
    if default_end:
        nodes.append(('End', 'endEvent', procedure.get('result', 'Done'), ''))
    known = {n[0] for n in nodes}
    lost = [t for _, t, _ in flows if t not in known]
    if lost:
        raise ValidationError([f'A step points to “{t}”, which does not exist.' for t in lost])
    sections = [(s['name'], s.get('colour', 'fog'), [node[str(n)] for n in s['steps']])
                for s in procedure.get('sections') or []]
    return tidy(build_diagram(procedure['title'], nodes, flows, sections), 'barda')  # tidy: nothing on a line


def check(folder, catalog=None, today=None):
    """(procedures, outside, diagrams, problems, warnings). Problems must be fixed; warnings are for review."""
    own, outside = load(folder, catalog)
    today = today or datetime.date.today()
    titles = {i: p.get('title', i) for i, p in own.items()} | {i: o['title'] for i, o in outside.items()}
    diagrams, problems, warnings = {}, [], []
    for key, p in own.items():
        said = lambda text, where=problems: where.append(f'{p["_path"].name}: {text}')  # noqa: E731
        if p.get('_error'):
            said(f'could not be read: {p["_error"]}')
            continue
        missing = [f for f in REQUIRED if not p.get(f)]
        if missing:
            said(f'add {", ".join(missing)}.')
            continue
        if p['_path'].stem != p['id'] or not re.fullmatch(r'[a-z0-9-]+', p['id']):
            said('the id is lowercase letters, digits and hyphens, and the file is named after it.')
        if p['audience'] not in AUDIENCES:
            said(f'audience is one of {", ".join(AUDIENCES)}.')
        if p['status'] not in STATUSES:
            said('status is one of draft, reviewed, outdated.')
        numbers = [str(s.get('n')) for s in p['steps']]
        if len(set(numbers)) < len(numbers) or 'None' in numbers:
            said('every step needs its own n.')
            continue
        refs = list(references(p))
        for ref in refs:
            there = outside.get(ref['id'])
            if ref['id'] in own:
                if AUDIENCES.index(own[ref['id']]['audience']) < AUDIENCES.index(p['audience']):
                    said(f'step {ref["n"]} sends a {p["audience"]} reader to “{ref["id"]}”, which is '
                         f'{own[ref["id"]]["audience"]}.', warnings)
            elif not there:
                said(f'step {ref["n"]} names “{ref["id"]}”, ' + ('which is not in the government catalog.' if catalog
                     else 'a procedure kept elsewhere; not verified (run with --catalog).'), problems if catalog else warnings)
            elif there['status'] == 'desactualizado' or str(ref.get('checked', '')) < there['last_checked']:
                said(f'step {ref["n"]}: the government procedure “{there["title"][:60]}” was updated on '
                     f'{there["last_checked"]}; read it again and set checked.', warnings)
        try:
            diagrams[key] = to_bpmn(p, titles)
            check_diagram(diagrams[key], [titles.get(r['id'], r['id']) for r in refs], p['title'])
            for message in layout_problems(diagrams[key], 'barda'):
                said(f'drawing: {message}')
        except ValidationError as error:
            for message in error.messages:
                said(message)
        age = (today - datetime.date.fromisoformat(str(p['last_checked']))).days
        if age > STALE_DAYS and STATUSES.get(p['status']) != 'outdated':
            said(f'last checked {age} days ago; walk through it again.', warnings)
    for path in sorted(Path(folder).rglob('*.bpmn')):
        if 'core' in path.parts or 'fixtures-drawing' in path.parts:
            continue
        try:
            problems += [f'{path.name}: drawing: {m}' for m in layout_problems(path.read_text())]
        except (ET.ParseError, ValidationError):
            problems.append(f'{path.name}: could not be read as BPMN.')
    return own, outside, diagrams, problems, warnings


PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{core}/viewer/bpmn-js-18.31.1/assets/diagram-js.css">
<link rel="stylesheet" href="{core}/viewer/bpmn-js-18.31.1/assets/bpmn-js.css">
<link rel="stylesheet" href="{core}/viewer/bpmn-js-18.31.1/assets/bpmn-font/css/bpmn.css">
<link rel="stylesheet" href="{core}/viewer/viewer.css">
<main><p><a href="index.html">← All procedures</a></p><h1>{title}</h1>
<p class="lead">{summary}</p><p class="muted">{meta}</p>
<div class="procedure-diagram" data-procedure-view><div class="procedure-canvas"></div></div>
<h2>Steps</h2><p class="muted">Starts when: {starts}</p><ol>{steps}</ol>
</main>
<script type="application/json" id="procedure-diagram">{diagram}</script>
<script type="application/json" id="procedure-links">{links}</script>
<script src="{core}/viewer/bpmn-js-18.31.1/bpmn-navigated-viewer.production.min.js"></script>
<script src="{core}/viewer/viewer.js"></script></html>
'''
INDEX = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Procedures</title><link rel="stylesheet" href="{core}/viewer/viewer.css">
<main><h1>Procedures</h1>{warnings}<ul class="list">{rows}</ul></main></html>
'''


def render(folder, out, catalog=None, core=None):
    own, outside, diagrams, problems, warnings = check(folder, catalog)
    if problems:
        raise ValidationError(problems)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    import os
    core = core or os.path.relpath(Path(__file__).resolve().parent, out.resolve())
    e = html.escape
    script = lambda value: json.dumps(value).replace('<', '\\u003c')  # noqa: E731
    urls = {i: f'{i}.html' for i in own} | {i: o['url'] for i, o in outside.items()}
    for key, p in own.items():
        (out / f'{key}.bpmn').write_text(diagrams[key])
        links = {(own[r['id']]['title'] if r['id'] in own else outside[r['id']]['title']).lower(): urls[r['id']]
                 for r in references(p) if r['id'] in urls}
        steps = ''
        for step in check_diagram(diagrams[key], list(links) + [r['id'] for r in references(p)], p['title']):
            if step['tag'] in ('startEvent', 'endEvent'):
                continue
            url = links.get(step['name'].lower()) if step['tag'] == 'callActivity' else None
            name = f'<a href="{e(url)}">{e(step["name"])}</a>' if url else e(step['name'])
            steps += (f'<li><strong>{name}</strong>' + (' <span class="muted">· another procedure</span>' if step['tag'] == 'callActivity' else '')
                      + (f'<p>{e(step["notes"]).replace(chr(10), "<br>")}</p>' if step['notes'] else '')
                      + ('<ul>' + ''.join(f'<li>{e(a)} → {e(t)}</li>' for a, t in step['next']) + '</ul>' if step['tag'] == 'exclusiveGateway' else '')
                      + '</li>')
        meta = f'{p["owner"]} · {p["audience"]} · {STATUSES[p["status"]]} · last checked {p["last_checked"]}'
        (out / f'{key}.html').write_text(PAGE.format(
            title=e(p['title']), summary=e(' '.join(p['summary'].split())), meta=e(meta), core=core, steps=steps,
            starts=e(p.get('starts_when', 'Start')), diagram=script(diagrams[key]), links=script(links)))
    rows = ''.join(f'<li><a href="{i}.html">{e(p["title"])}</a><p class="muted">{e(" ".join(p["summary"].split()))}</p></li>'
                   for i, p in own.items())
    notes = ('<h2>To review</h2><ul>' + ''.join(f'<li>{e(w)}</li>' for w in warnings) + '</ul><h2>All</h2>') if warnings else ''
    (out / 'index.html').write_text(INDEX.format(core=core, rows=rows, warnings=notes))
    return own, warnings


def drawings(argv):
    """layout / tidy on .bpmn files."""
    style = argv[argv.index('--style') + 1] if '--style' in argv else 'page'
    files = [a for a in argv[1:] if a.endswith('.bpmn')]
    bad = 0
    for path in files:
        xml = Path(path).read_text()
        if argv[0] == 'tidy':
            new = tidy(xml, style)
            if '--write' in argv:
                if new != xml:
                    Path(path).write_text(new)
                left = layout_problems(new, style)
                print(f'{path}: {"tidied" if new != xml else "unchanged"}' + (f', {len(left)} left' if left else ''))
                bad += len(left)
            else:
                sys.stdout.write(new)
            continue
        for message in layout_problems(xml, style):
            print('FIX   ', f'{path}: {message}')
            bad += 1
    if argv[0] == 'layout':
        print(f'{len(files)} drawings, {bad} to fix')
    return 1 if bad else 0


def main(argv):
    if argv and argv[0] in ('layout', 'tidy') and len(argv) > 1:
        return drawings(argv)
    catalog = argv[argv.index('--catalog') + 1] if '--catalog' in argv else None
    args = [a for a in argv if a != '--catalog' and a != catalog]
    if len(args) < 2 or args[0] not in ('check', 'render') or (args[0] == 'render' and len(args) < 3):
        print(__doc__)
        return 2
    try:
        if args[0] == 'render':
            own, warnings = render(args[1], args[2], catalog)
            problems = []
        else:
            own, _, _, problems, warnings = check(args[1], catalog)
    except ValidationError as error:
        own, problems, warnings = {}, error.messages, []
    for line in problems:
        print('FIX   ', line)
    for line in warnings:
        print('REVIEW', line)
    print(f'{len(own)} procedures, {len(problems)} to fix, {len(warnings)} to review')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
