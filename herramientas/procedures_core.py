#!/usr/bin/env python3
"""Procedures core 0.1: one small format for standard operating procedures, shared by Living (Barda), Cross
and Compartido. Spec: ../CORE.md.

A procedure is a YAML file of steps. This file checks it, turns it into a BPMN 2.0 flowchart (the same five
shapes and look as Barda's procedures) and writes a page that draws it with bpmn-js.

    python3 procedures_core.py check  <folder> [--catalog <catalogo-gobierno checkout>]
    python3 procedures_core.py render <folder> <output folder> [--catalog ...]

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
    return build_diagram(procedure['title'], nodes, flows, sections)


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
        except ValidationError as error:
            for message in error.messages:
                said(message)
        age = (today - datetime.date.fromisoformat(str(p['last_checked']))).days
        if age > STALE_DAYS and STATUSES.get(p['status']) != 'outdated':
            said(f'last checked {age} days ago; walk through it again.', warnings)
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


def main(argv):
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
