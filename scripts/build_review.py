#!/usr/bin/env python3
"""Validate an IELTS review JSON and build the approved five-section Word layout."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re
import sys

SKILL_ROOT = Path(__file__).resolve().parents[1]
CAUSES = {
    '01': '词句没读懂', '02': '换个说法没认出', '03': '证据没找到',
    '04': '题目要求没查全', '05': '相似内容选混了', '06': '答案填写出错',
}
METHODS = {'reading': '读题', 'locating': '定位', 'deciding': '确定答案',
           'checking': '验证进步', 'keeping': '保留做法'}
SECTIONS = ['01 本篇概况', '02 逐题复盘', '03 错因汇总', '04 下一篇怎样做', '05 高亮修改']
TIMING_SCOPES = {'full_test': '整套阅读', 'passage': '单篇阅读', 'question_group': '题组'}


class DataError(ValueError):
    """Actionable validation error with a field path."""


def require(condition, message):
    if not condition:
        raise DataError(message)


def required_text(obj, field, path):
    value = obj.get(field)
    require(isinstance(value, str) and bool(value.strip()), f'{path}.{field} 必须是非空文本')
    return value


def required_list(obj, field, path):
    value = obj.get(field)
    require(isinstance(value, list), f'{path}.{field} 必须是数组')
    return value


def object_at(obj, path):
    require(isinstance(obj, dict), f'{path} 必须是对象')
    return obj


def normalized(text):
    return ' '.join(text.split())


def answer_text(value):
    return ' / '.join(value) if isinstance(value, list) else ('待核对' if value is None else (value or '未作答'))


def cause_memberships(cause):
    """A confirmed cause is one finding; pending entries are alternative hypotheses."""
    if cause['certainty'] == 'confirmed':
        return [('confirmed', cause['code'])]
    codes = ([cause['code']] if cause['certainty'] == 'possible' else []) + cause.get('candidates', [])
    return [('pending', code) for code in codes] or [('pending', None)]


def timing_summary(timing):
    """Describe a recorded interval, without inventing a time target or band score."""
    elapsed = timing['elapsed_minutes']
    text = f"{TIMING_SCOPES[timing['scope']]}：实际 {elapsed:g} 分钟"
    if 'budget_minutes' in timing:
        budget = timing['budget_minutes']; difference = round(elapsed - budget, 10)
        text += f'；预算 {budget:g} 分钟；'
        text += f'超时 {difference:g} 分钟' if difference > 0 else (f'余量 {-difference:g} 分钟' if difference < 0 else '与预算一致')
    return text


def validate(data):
    """Return calculated counts; reject contradictions without diagnosing a learner."""
    object_at(data, '根对象')
    required_text(data, 'title', '根对象')
    require(isinstance(data.get('subtitle', ''), str), 'subtitle 必须是文本')
    sources = {}
    for i, source in enumerate(required_list(data, 'sources', '根对象')):
        path = f'sources[{i}]'; object_at(source, path)
        sid = required_text(source, 'id', path)
        require(sid not in sources, f'{path}.id 重复：{sid}')
        required_text(source, 'label', path)
        require('text' not in source or isinstance(source['text'], str), f'{path}.text 必须是文本')
        sources[sid] = source
    require(sources, '至少填写一个 sources 来源')
    answers = {}
    counts = Counter()
    by_type = defaultdict(Counter)
    for i, answer in enumerate(required_list(data, 'answers', '根对象')):
        path = f'answers[{i}]'; object_at(answer, path)
        qid = answer.get('id')
        require(isinstance(qid, (str, int)) and not isinstance(qid, bool) and str(qid).strip(), f'{path}.id 必须是题号')
        qid = str(qid)
        require(qid not in answers, f'{path}.id 重复：{qid}')
        typ = required_text(answer, 'type', path)
        status = answer.get('status')
        require(status in {'correct', 'wrong', 'unverified'}, f'{path}.status 必须为 correct / wrong / unverified')
        if status != 'unverified' or 'answer_source' in answer:
            answer_source = required_text(answer, 'answer_source', path)
            require(answer_source in sources, f'{path}.answer_source 未在 sources 中声明：{answer_source}')
        require(isinstance(answer.get('user_answer'), str), f'{path}.user_answer 必须是文本；未作答用空字符串')
        key = answer.get('key')
        if key is not None:
            require(isinstance(key, str) or (isinstance(key, list) and key and all(isinstance(k, str) and k.strip() for k in key)), f'{path}.key 为答案文本或可接受答案数组')
        if status != 'unverified':
            require(bool(key), f'{path} 已批改状态需要可靠 key；未知答案标 unverified')
            acceptable = key if isinstance(key, list) else [key]
            matches = normalized(answer['user_answer']).casefold() in {normalized(k).casefold() for k in acceptable}
            if matches != (status == 'correct'):
                require(isinstance(answer.get('marking_note'), str) and bool(answer['marking_note'].strip()), f'{path} 状态与答案字面核对矛盾；核对后修正或填写 marking_note')
        counts[status] += 1; by_type[typ][status] += 1; answers[qid] = answer
    require(answers, 'answers 不能为空')
    routes = {}
    for i, route in enumerate(required_list(data, 'answer_routes', '根对象')):
        path = f'answer_routes[{i}]'; object_at(route, path)
        route_id = route.get('id')
        require(isinstance(route_id, (str, int)) and not isinstance(route_id, bool), f'{path}.id 必须是题号')
        route_id = str(route_id)
        require(route_id in answers, f'{path}.id 未在 answers 中声明：{route_id}')
        require(route_id not in routes, f'{path}.id 重复：{route_id}')
        route_status = route.get('status')
        require(route_status in {'verified', 'pending'}, f'{path}.status 必须为 verified / pending')
        if route_status == 'verified':
            require(answers[route_id]['status'] != 'unverified', f'{path} 的答案尚未核对，定位路线不能标为 verified')
        else:
            required_text(route, 'reason', path)
        for field in ('source', 'entry', 'path', 'location', 'check', 'time_saver'):
            if route_status == 'verified' or field in route:
                required_text(route, field, path)
        if 'source' in route:
            require(route['source'] in sources, f'{path}.source 未在 sources 中声明：{route["source"]}')
        if 'if_stuck' in route:
            required_text(route, 'if_stuck', path)
        if 'test_point' in route:
            required_text(route, 'test_point', path)
        routes[route_id] = route
    require(routes.keys() == answers.keys(), 'answer_routes 必须覆盖所有题目（含正确题与待核对题）；缺少：' + '、'.join(qid for qid in answers if qid not in routes))
    overview = object_at(data.get('overview'), 'overview')
    required_text(overview, 'focus', 'overview')
    for field in ('time', 'order', 'date'):
        require(field not in overview or isinstance(overview[field], str), f'overview.{field} 必须是文本')
    if 'passage_map' in overview:
        passage_map = required_list(overview, 'passage_map', 'overview')
        require(passage_map, 'overview.passage_map 不能为空')
        paragraphs = set()
        for i, item in enumerate(passage_map):
            path = f'overview.passage_map[{i}]'; object_at(item, path)
            for field in ('paragraph', 'role', 'use'):
                required_text(item, field, path)
            paragraph_id = normalized(item['paragraph'])
            require(paragraph_id not in paragraphs, f'{path}.paragraph 重复：{paragraph_id}')
            paragraphs.add(paragraph_id)
    if 'timing' in overview:
        timing = object_at(overview['timing'], 'overview.timing')
        require(timing.get('scope') in TIMING_SCOPES, 'overview.timing.scope 必须为 full_test / passage / question_group')
        for field in ('elapsed_minutes', 'budget_minutes'):
            if field == 'elapsed_minutes' or field in timing:
                value = timing.get(field)
                require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0, f'overview.timing.{field} 必须是正有限数')
        required_text(timing, 'basis', 'overview.timing')
        require('completion_note' not in timing or isinstance(timing['completion_note'], str), 'overview.timing.completion_note 必须是文本')
    comments = object_at(overview.get('type_comments', {}), 'overview.type_comments')
    for typ, comment in comments.items():
        require(typ in by_type and isinstance(comment, str), f'overview.type_comments 存在未知题型或非文本评价：{typ}')

    def verify_quote(item, field, path):
        sid = required_text(item, 'source', path)
        require(sid in sources, f'{path}.source 未在 sources 中声明：{sid}')
        quote = required_text(item, field, path)
        original = sources[sid].get('text')
        if original:
            require(normalized(quote) in normalized(original), f'{path}.{field} 不是来源 {sid} 中的连续摘录；保留完整关键分句，分开记录不连续引文')
        return quote

    questions = {}
    for i, question in enumerate(required_list(data, 'questions', '根对象')):
        path = f'questions[{i}]'; object_at(question, path)
        qid = str(question.get('id'))
        require(qid in answers, f'{path}.id 未在 answers 中声明')
        require(qid not in questions, f'{path}.id 重复：{qid}')
        for field in ('title', 'comparison', 'action'):
            required_text(question, field, path)
        requirement = object_at(question.get('requirement'), f'{path}.requirement')
        for field in ('text', 'meaning'):
            required_text(requirement, field, f'{path}.requirement')
        evidence = required_list(question, 'evidence', path)
        evidence_type = question.get('evidence_type', 'direct')
        require(evidence_type in {'direct', 'contradiction', 'not_given', 'main_idea'}, f'{path}.evidence_type 必须为 direct / contradiction / not_given / main_idea')
        keys = answers[qid].get('key')
        keys = keys if isinstance(keys, list) else [keys]
        normalized_keys = {normalized(key).upper() for key in keys if isinstance(key, str)}
        if normalized_keys & {'NOT GIVEN', 'NG'}:
            require(evidence_type == 'not_given', f'{path} 的参考答案是 NOT GIVEN / NG，必须使用 not_given 证据模式')
        if evidence_type == 'not_given':
            require(not normalized_keys & {'TRUE', 'FALSE', 'YES', 'NO'}, f'{path} 的参考答案明确为 TRUE / FALSE / YES / NO，不能使用 not_given 证据模式')
            review = object_at(question.get('evidence_review'), f'{path}.evidence_review')
            sid = required_text(review, 'source', f'{path}.evidence_review')
            require(sid in sources, f'{path}.evidence_review.source 未在 sources 中声明：{sid}')
            for field in ('scope', 'missing_information'):
                required_text(review, field, f'{path}.evidence_review')
        elif evidence_type in {'contradiction', 'main_idea'} or answers[qid]['status'] != 'unverified':
            require(evidence, f'{path}.evidence 不能为空；已判定答案必须有证据')
        for j, ev in enumerate(evidence):
            ep = f'{path}.evidence[{j}]'; object_at(ev, ep)
            quote = verify_quote(ev, 'quote', ep)
            for field in ('location', 'explanation'):
                required_text(ev, field, ep)
            terms = ev.get('emphasis', [])
            require(isinstance(terms, list) and all(isinstance(t, str) and t.strip() for t in terms), f'{ep}.emphasis 必须为短语数组')
            for term in terms:
                require(term in quote, f'{ep}.emphasis 中的短语未在 quote 中：{term}')
                require(len(term) <= 80 and len(term.split()) <= 12, f'{ep}.emphasis 请保留短关键词，不要整句加粗')
            if len(quote) > 90 and terms:
                marked = set()
                for term in terms:
                    for match in re.finditer(re.escape(term), quote):
                        marked.update(range(match.start(), match.end()))
                require(len(marked) / len(quote) <= 0.65, f'{ep}.emphasis 覆盖大半长引文；请减少至决定答案的短语')
        cause = question.get('cause')
        status = answers[qid]['status']
        if status == 'wrong':
            require(isinstance(cause, dict), f'{path}.cause 是错题必填字段')
        if cause is not None:
            require(status == 'wrong', f'{path}.cause：正确题或待核对题使用 null，不预先归因')
            object_at(cause, f'{path}.cause')
            certainty = cause.get('certainty')
            require(certainty in {'confirmed', 'possible', 'unconfirmed'}, f'{path}.cause.certainty 必须为 confirmed / possible / unconfirmed')
            if certainty == 'unconfirmed':
                require('code' in cause and cause['code'] is None, f'{path}.cause.code：unconfirmed 必须显式为 null')
            else:
                require(isinstance(cause.get('code'), str) and cause['code'] in CAUSES, f'{path}.cause.code 必须为 01—06')
            candidates = cause.get('candidates', [])
            require(isinstance(candidates, list) and all(isinstance(code, str) and code in CAUSES for code in candidates), f'{path}.cause.candidates 必须为 01—06 代码数组')
            require(len(set(candidates)) == len(candidates) and cause.get('code') not in candidates, f'{path}.cause.candidates 不得重复，也不得重复主因 code')
            required_text(cause, 'observation', f'{path}.cause')
            if 'stage' in cause:
                required_text(cause, 'stage', f'{path}.cause')
            if certainty == 'confirmed':
                require(not candidates, f'{path}.cause：已确认原因不能保留待排查候选')
                required_text(cause, 'basis', f'{path}.cause')
            else:
                required_text(cause, 'self_check', f'{path}.cause')
        require(isinstance(question.get('break_before', False), bool), f'{path}.break_before 必须为布尔值')
        questions[qid] = question
    wrong_ids = {qid for qid, answer in answers.items() if answer['status'] == 'wrong'}
    require(wrong_ids <= questions.keys(), '以下错题缺少六字段复盘：' + '、'.join(sorted(wrong_ids - questions.keys())))
    expected_causes = defaultdict(set)
    for qid in wrong_ids:
        for membership in cause_memberships(questions[qid]['cause']):
            expected_causes[membership].add(qid)
    actual_causes = {}
    cause_statuses = []
    for i, cause in enumerate(required_list(data, 'causes', '根对象')):
        path = f'causes[{i}]'; object_at(cause, path)
        code = cause.get('code')
        require('code' in cause and (code is None or isinstance(code, str) and code in CAUSES), f'{path}.code 必须为 01—06 或 null')
        ids = required_list(cause, 'question_ids', path)
        require(ids and all(str(qid) in wrong_ids for qid in ids), f'{path}.question_ids 只汇总已经确认答错的题号')
        require(len({str(qid) for qid in ids}) == len(ids), f'{path}.question_ids 存在重复')
        required_text(cause, 'training', path)
        ids = {str(qid) for qid in ids}
        summary_status = cause.get('status')
        if 'status' not in cause:
            inferred = [state for (state, candidate), members in expected_causes.items() if candidate == code and ids <= members]
            require(len(inferred) == 1, f'{path}.status 无法推定；同类别中已确认与待排查题必须拆行，或核对题号及候选')
            summary_status = inferred[0]
        require(summary_status in {'confirmed', 'pending'}, f'{path}.status 必须为 confirmed / pending')
        require(code is not None or summary_status == 'pending', f'{path}.code 为 null 时只能使用 pending')
        membership = (summary_status, code)
        require(membership not in actual_causes, f'{path} 重复了相同的 (status, code) 汇总行')
        actual_causes[membership] = ids
        cause_statuses.append(summary_status)
    require(dict(expected_causes) == actual_causes, 'causes 汇总必须与逐题的确认原因、待排查候选或未归类状态一致；清除已排除候选，不漏记或重复计错')
    method = object_at(data.get('method'), 'method')
    for field in METHODS:
        required_text(method, field, 'method')
    if 'speed_plan' in method:
        speed_plan = object_at(method['speed_plan'], 'method.speed_plan')
        for field in ('context', 'stop_rule', 'practice'):
            required_text(speed_plan, field, 'method.speed_plan')
        steps = required_list(speed_plan, 'steps', 'method.speed_plan')
        require(steps, 'method.speed_plan.steps 不能为空')
        for i, step in enumerate(steps):
            path = f'method.speed_plan.steps[{i}]'; object_at(step, path)
            for field in ('stage', 'action', 'saves'):
                required_text(step, field, path)
    if 'habits' in method:
        habits = required_list(method, 'habits', 'method')
        require(1 <= len(habits) <= 2, 'method.habits 每轮只选 1—2 个训练动作')
        for i, habit in enumerate(habits):
            path = f'method.habits[{i}]'; object_at(habit, path)
            for field in ('name', 'trigger', 'action', 'pass_check', 'record'):
                required_text(habit, field, path)
    highlights = object_at(data.get('highlights'), 'highlights')
    require(highlights.get('status') in {'observed', 'not_provided'}, 'highlights.status 必须为 observed / not_provided')
    for group in ('add', 'reduce', 'keep'):
        rows = required_list(highlights, group, 'highlights')
        require(highlights['status'] == 'observed' or not rows, '未提供实际高亮材料时，add / reduce / keep 必须为空，不能虚构用户标记')
        for i, row in enumerate(rows):
            path = f'highlights.{group}[{i}]'; object_at(row, path)
            require(row.get('priority', 'core') in {'core', 'optional'}, f'{path}.priority 必须为 core / optional')
            for field in ('location', 'observed', 'reason'):
                required_text(row, field, path)
            if group == 'add':
                verify_quote(row, 'quote', path)
            else:
                verify_quote(row, 'observed', path)
            if group == 'reduce':
                required_text(row, 'action', path)
    required_text(highlights, 'boundary', 'highlights')
    require(isinstance(highlights.get('question_adjustments', ''), str), 'highlights.question_adjustments 必须是文本')
    layout = object_at(data.get('layout', {}), 'layout')
    breaks = layout.get('break_before_sections', [])
    require(isinstance(breaks, list) and all(b in {'02', '03', '04', '05'} for b in breaks), 'layout.break_before_sections 只能包含 02 / 03 / 04 / 05')
    return {'counts': dict(counts), 'by_type': {k: dict(v) for k, v in by_type.items()}, 'total': len(answers), 'wrong_ids': sorted(wrong_ids, key=lambda value: (0, int(value)) if value.isdigit() else (1, value)), 'cause_statuses': cause_statuses, 'warnings': [f'来源 {sid} 未附文本；引文须人工对照原图或文件核验' for sid, source in sources.items() if not source.get('text')]}


def build_document(data, output, template=None, style_path=None, cjk_font=None, english_font=None):
    audit = validate(data)
    try:
        from docx import Document
        from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Cm, Pt, RGBColor
    except ImportError as error:
        raise DataError('缺少 python-docx；请使用已有文档运行环境，或自行安装 requirements.txt 中的依赖') from error
    style = json.loads(Path(style_path or SKILL_ROOT / 'assets/word-style.json').read_text(encoding='utf-8'))
    fonts = {'cjk': cjk_font or style['fonts']['cjk'], 'english': english_font or style['fonts']['english']}
    colors = style['colors']
    template_path = Path(template or SKILL_ROOT / 'assets/review-template.docx')
    require(template_path.is_file(), f'找不到版式模板：{template_path}')
    doc = Document(template_path)
    for child in list(doc._element.body):
        if child.tag != qn('w:sectPr'):
            doc._element.body.remove(child)

    def set_font(rpr):
        rf = rpr.find(qn('w:rFonts'))
        if rf is None:
            rf = OxmlElement('w:rFonts'); rpr.insert(0, rf)
        for attr in list(rf.attrib):
            if 'theme' in attr.lower():
                del rf.attrib[attr]
        for key, val in {'ascii': fonts['english'], 'hAnsi': fonts['english'], 'eastAsia': fonts['cjk'], 'cs': fonts['english']}.items():
            rf.set(qn('w:' + key), val)

    # Overrides apply to inherited defaults, existing footer, and newly authored runs.
    roots = [doc.styles.element, doc.element]
    for section in doc.sections:
        roots.extend([section.header._element, section.footer._element])
    for root in roots:
        for rpr in root.iter(qn('w:rPr')):
            set_font(rpr)
    for name, values in style['styles'].items():
        st = doc.styles[name]; st.font.name = fonts['english']; set_font(st.element.get_or_add_rPr())
        st.font.size = Pt(values['size']); st.font.bold = values['bold']; st.font.color.rgb = RGBColor.from_string(colors[values['color']])
        pf = st.paragraph_format
        pf.space_before = Pt(values['before']); pf.space_after = Pt(values['after']); pf.line_spacing = Pt(values['line'])
        pf.keep_with_next = name in {'Title', 'Subtitle', 'Heading 1', 'Heading 2'}
        pf.widow_control = True
    for section in doc.sections:
        vals = style['page_cm']; section.page_width = Cm(vals['width']); section.page_height = Cm(vals['height'])
        for side in ('top', 'bottom', 'left', 'right'):
            setattr(section, side + '_margin', Cm(vals[side]))
        section.footer_distance = Cm(vals['footer'])
    doc.core_properties.title = data['title']; doc.core_properties.subject = '雅思阅读复盘'
    doc.core_properties.author = ''; doc.core_properties.last_modified_by = ''
    doc.core_properties.comments = ''

    def run(p, text, bold=False, color='body', size=None):
        r = p.add_run(str(text)); set_font(r._r.get_or_add_rPr())
        r.bold = bold; r.font.color.rgb = RGBColor.from_string(colors.get(color, color))
        if size is not None:
            r.font.size = Pt(size)
        return r

    def paragraph(text='', label=None, role='blue', style_name='Normal'):
        p = doc.add_paragraph(style=style_name)
        if label:
            run(p, label, True, role); run(p, '　')
        if text:
            run(p, text)
        return p

    def heading(text, level=1, page_break=False):
        p = doc.add_paragraph(style=f'Heading {level}')
        run(p, text, True, 'blue'); p.paragraph_format.page_break_before = page_break
        return p

    def section(index):
        return heading(SECTIONS[index], page_break=SECTIONS[index][:2] in data.get('layout', {}).get('break_before_sections', ['05']))

    def emphasized(p, text, terms):
        ranges = []
        for term in terms:
            ranges.extend((m.start(), m.end()) for m in re.finditer(re.escape(term), text))
        points = sorted({0, len(text)} | {point for interval in ranges for point in interval})
        for left, right in zip(points, points[1:]):
            run(p, text[left:right], any(left >= start and right <= end for start, end in ranges))

    def table(headers, rows, kind, first_color=None, widths=None):
        if not rows:
            return
        widths = widths or style['table_widths_cm'][kind]; ts = style['table']
        t = doc.add_table(rows=1, cols=len(headers)); t.alignment = WD_TABLE_ALIGNMENT.CENTER; t.autofit = False
        for column, width in zip(t.columns, widths):
            column.width = Cm(width)
        borders = OxmlElement('w:tblBorders')
        for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
            e = OxmlElement('w:' + edge)
            for key, val in {'val': 'single', 'sz': str(ts['border_eighth_points']), 'color': colors['border']}.items():
                e.set(qn('w:' + key), val)
            borders.append(e)
        t._tbl.tblPr.append(borders)
        for ri, values in enumerate([headers] + rows):
            row = t.rows[0] if ri == 0 else t.add_row()
            trpr = row._tr.get_or_add_trPr(); trpr.append(OxmlElement('w:cantSplit'))
            if ri == 0:
                trpr.append(OxmlElement('w:tblHeader'))
            for ci, (cell, value, width) in enumerate(zip(row.cells, values, widths)):
                cell.width = Cm(width); cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                tcpr = cell._tc.get_or_add_tcPr()
                shd = OxmlElement('w:shd'); shd.set(qn('w:fill'), colors['header'] if ri == 0 else 'FFFFFF'); tcpr.append(shd)
                margins = OxmlElement('w:tcMar')
                for edge in ('top', 'bottom', 'left', 'right'):
                    e = OxmlElement('w:' + edge); e.set(qn('w:type'), 'dxa')
                    e.set(qn('w:w'), str(ts['padding_vertical_twips' if edge in {'top', 'bottom'} else 'padding_horizontal_twips']))
                    margins.append(e)
                tcpr.append(margins)
                p = cell.paragraphs[0]; pf = p.paragraph_format
                pf.space_before = Pt(0); pf.space_after = Pt(0); pf.line_spacing = Pt(ts['line']); pf.keep_with_next = ri == 0
                if width <= 2.7:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                role = 'blue' if ri == 0 else (first_color if ci == 0 and first_color else 'body')
                if isinstance(value, list):
                    for text, bold, segment_role in value:
                        run(p, text, bold, segment_role, ts['size'])
                else:
                    run(p, value, ri == 0 or bool(ci == 0 and first_color), role, ts['size'])
        # Small measured spacer, not a blank full-height paragraph.
        gap = doc.add_paragraph(); gap.paragraph_format.line_spacing = Pt(3); gap.paragraph_format.space_after = Pt(0)
        return t

    p = doc.add_paragraph(style='Title'); run(p, data['title'], True, 'title')
    if data.get('subtitle'):
        p = doc.add_paragraph(style='Subtitle'); run(p, data['subtitle'], False, 'muted')
    section(0)
    counts = audit['counts']; checked = counts.get('correct', 0) + counts.get('wrong', 0)
    score = f"{counts.get('correct', 0)}/{audit['total']}" if not counts.get('unverified') else f"已核对 {checked}/{audit['total']}；其中正确 {counts.get('correct', 0)}，错误 {counts.get('wrong', 0)}，待核对 {counts['unverified']}"
    meta = data['overview']
    result = f"{score}　错题 {'、'.join(audit['wrong_ids']) or '无'}"
    paragraph(result if 'timing' in meta else result + f"　用时 {meta.get('time') or '未记录'}", '练习结果')
    if 'timing' in meta:
        paragraph(timing_summary(meta['timing']), '用时')
        paragraph(meta['timing']['basis'], '计时依据')
        if meta['timing'].get('completion_note'):
            paragraph(meta['timing']['completion_note'], '完成情况')
    if meta.get('date'):
        paragraph(meta['date'], '练习日期')
    paragraph(meta.get('order') or '未记录', '作答顺序')
    overview_rows = []
    for typ, ct in audit['by_type'].items():
        total = sum(ct.values()); ids = '、'.join(str(a['id']) for a in data['answers'] if a['type'] == typ)
        result = f"{ct.get('correct', 0)}/{total}" if not ct.get('unverified') else f"正确{ct.get('correct', 0)}；待核对{ct['unverified']}"
        overview_rows.append([f'{typ} {ids}', result, meta.get('type_comments', {}).get(typ, '暂无足够信息判断')])
    table(['题型与题号', '正确数', '本篇判断'], overview_rows, 'overview')
    paragraph(meta['focus'], '本篇重点')
    if 'passage_map' in meta:
        heading('全文检索地图', 2)
        paragraph('用于复盘后回忆各段功能与检索线索；不要求考场上先读完全篇或制作此表。')
        table(['段落', '内容与作用', '怎样用于解题'],
              [[item['paragraph'], item['role'], item['use']] for item in meta['passage_map']],
              'overview', widths=[1.5, 7.3, 8.6])

    section(1)
    lookup = {str(a['id']): a for a in data['answers']}
    route_lookup = {str(route['id']): route for route in data['answer_routes']}
    show_route_sources = len({route['source'] for route in data['answer_routes'] if route.get('source')}) > 1
    heading('每题定位与提速', 2)
    route_rows = []
    for answer in data['answers']:
        qid = str(answer['id']); route = route_lookup[qid]
        search = []
        if route['status'] == 'pending':
            search.append('待核对：' + route['reason'])
        if route.get('entry'):
            search.append('入口：' + route['entry'])
        if route.get('path'):
            search.append('→ ' + route['path'])
        if route.get('location'):
            source = f"[{route['source']}] " if show_route_sources and route.get('source') else ''
            search.append('→ ' + source + route['location'])
        check = []
        if route.get('test_point'):
            check.extend([('考点：', True, 'brown'), (route['test_point'] + '\n', False, 'body'), ('判定：', True, 'blue')])
        check.append((route.get('check', '核对条件待补充'), False, 'body'))
        if route.get('time_saver'):
            check.extend([('\n', False, 'body'), ('省时：', True, 'green'), (route['time_saver'], False, 'body')])
        if route.get('if_stuck'):
            check.append(('\n暂放：' + route['if_stuck'], False, 'body'))
        route_rows.append([qid, '\n'.join(search), check])
    table(['题号', '从哪里找', '确认与省时动作'], route_rows, 'overview', widths=[1.5, 8.1, 7.8])
    if not audit['wrong_ids']:
        paragraph('已核对题目无错题；待核对题不计入错题。' if counts.get('unverified') else '本篇无错题。')
    for q in data['questions']:
        qid = str(q['id']); a = lookup[qid]; status = a['status']
        if q.get('break_before', False):
            heading('02 逐题复盘  续', page_break=True)
        heading(f"第 {qid} 题　{q['title']}" + ('（待核对）' if status == 'unverified' else ''), 2)
        p = paragraph(label='作答结果'); run(p, '你的答案 ')
        run(p, a['user_answer'] or '未作答', True, 'wrong' if status == 'wrong' else ('green' if status == 'correct' else 'body'))
        run(p, '　' + ('参考答案（待核对） ' if status == 'unverified' else '正确答案 '))
        run(p, answer_text(a.get('key')), True, 'body' if status == 'unverified' else 'green'); run(p, '　题型 ' + a['type'])
        paragraph(q['requirement']['text'], '题目要求'); paragraph(q['requirement']['meaning'])
        is_not_given = q.get('evidence_type', 'direct') == 'not_given'
        if is_not_given:
            review = q['evidence_review']
            paragraph(f"核查范围：[{review['source']}] {review['scope']}", '正确证据')
            paragraph('缺失信息：' + review['missing_information'])
        elif not q['evidence']:
            paragraph('暂缺可核对的原文证据，不据此判断对错。', '正确证据')
        for ei, ev in enumerate(q['evidence']):
            p = paragraph(label='正确证据' if ei == 0 and not is_not_given else None)
            run(p, ev['location'] + '：'); emphasized(p, '“' + ev['quote'] + '”', ev.get('emphasis', []))
            paragraph(ev['explanation'])
        paragraph(q['comparison'], '答案对比')
        cause = q.get('cause')
        if cause:
            p = paragraph(label='错因判断', role='brown')
            run(p, cause['observation'] + '　个人原因：')
            certainty = cause['certainty']
            if certainty == 'unconfirmed':
                run(p, '待确认，尚未归类', True)
            else:
                run(p, '已确认 ' if certainty == 'confirmed' else '优先排查 ')
                run(p, cause['code'] + ' ' + CAUSES[cause['code']], True)
            if cause.get('candidates'):
                run(p, '；候选：' + '、'.join(code + ' ' + CAUSES[code] for code in cause['candidates']))
            run(p, '。')
            if cause.get('stage'):
                run(p, (' 出错环节：' if certainty == 'confirmed' else ' 优先检查环节：'), True, 'brown')
                run(p, cause['stage'])
            if certainty == 'confirmed':
                paragraph('确认依据：' + cause['basis'])
            if certainty != 'confirmed' and cause.get('self_check'):
                paragraph('自测：' + cause['self_check'])
        else:
            paragraph('本题未判定为错题，不强行归入错因。', '错因判断', 'brown')
        paragraph(q['action'], '下次动作', 'green')

    section(2)
    if data['causes']:
        rows = []
        pending_counts = Counter()
        for cause, summary_status in zip(data['causes'], audit['cause_statuses']):
            if cause['code'] is None:
                title = '待确认未归类'
            else:
                title = ('已确认 ' if summary_status == 'confirmed' else '待排查 ') + cause['code'] + ' ' + CAUSES[cause['code']]
            rows.append([title, '、'.join(str(i) for i in cause['question_ids']), cause['training']])
            if summary_status == 'pending':
                pending_counts.update(str(i) for i in cause['question_ids'])
        table(['本次涉及的类别', '题号', '针对性训练'], rows, 'causes', 'body')
        if any(count > 1 for count in pending_counts.values()):
            paragraph('同题的多个候选是待排查方向，不能相加作为错题数；错题数以本篇概况为准。')
    else:
        paragraph('本篇没有已确认的错题，暂不汇总错因。')
    section(3)
    if 'speed_plan' in data['method']:
        speed_plan = data['method']['speed_plan']
        heading('本篇提速路线', 2)
        paragraph(speed_plan['context'])
        table(['先后安排', '具体操作', '省在哪里'],
              [[step['stage'], step['action'], step['saves']] for step in speed_plan['steps']],
              'overview', widths=[3, 9.4, 5])
        paragraph(speed_plan['stop_rule'], '何时暂放', 'green')
        paragraph(speed_plan['practice'], '怎样练快', 'green')
    if 'habits' in data['method']:
        heading('本轮训练动作', 2)
        paragraph('以下是下一轮训练安排；完成情况以练习记录为准。').paragraph_format.keep_with_next = True
        for habit in data['method']['habits']:
            p = paragraph(label=habit['name'], role='green')
            p.paragraph_format.keep_with_next = True
            run(p, '触发：', True, 'green'); run(p, habit['trigger'])
            paragraph(habit['action'], '动作', 'green').paragraph_format.keep_with_next = True
            p = paragraph(habit['pass_check'], '验收', 'green')
            run(p, '　记录：', True, 'green'); run(p, habit['record'])
    for key, label in METHODS.items():
        paragraph(data['method'][key], label, 'green')
    section(4)
    hl = data['highlights']
    def ordered_highlights(group):
        return sorted(hl[group], key=lambda row: row.get('priority', 'core') == 'optional')

    def highlight_location(row):
        return row['location'] + ('（可选）' if row.get('priority') == 'optional' else '')

    if hl['status'] == 'not_provided':
        paragraph('未提供实际高亮材料，本次不判断哪些标多了或漏标了。')
    else:
        heading('优先补标', 2)
        table(['位置与题号', '实际标记情况', '建议补上的具体原文'],
              [[highlight_location(r), r['observed'], r['quote'] + '\n' + r['reason']] for r in ordered_highlights('add')], 'add')
        if not hl['add']:
            paragraph('暂无需要优先补标的内容。')
        heading('取消或缩短', 2)
        table(['位置', '实际已标原文', '具体处理与理由'],
                  [[highlight_location(r), r['observed'], r['action'].rstrip('。；; ') + '；' + r['reason']] for r in ordered_highlights('reduce')], 'reduce')
        if not hl['reduce']:
            paragraph('暂无需要删减的标记。')
        if hl['keep']:
            for index, row in enumerate(ordered_highlights('keep')):
                paragraph(highlight_location(row) + '：“' + row['observed'] + '”。' + row['reason'],
                          '继续保留' if index == 0 else None, 'green')
    if hl.get('question_adjustments'):
        paragraph(hl['question_adjustments'], '题干同步调整')
    paragraph(hl['boundary'], '使用边界')
    p = paragraph(label='原始材料', role='muted')
    run(p, '；'.join(f"[{s['id']}] {s['label']}" for s in data['sources']), color='muted', size=9)
    answer_sources = defaultdict(list)
    missing_source_ids = []
    for answer in data['answers']:
        qid = str(answer['id']) + ('（待核对）' if answer['status'] == 'unverified' else '')
        if answer.get('answer_source'):
            answer_sources[answer['answer_source']].append(qid)
        else:
            missing_source_ids.append(str(answer['id']))
    source_notes = [f"[{sid}] 第 {'、'.join(ids)} 题" for sid, ids in answer_sources.items()]
    if missing_source_ids:
        source_notes.append('第 ' + '、'.join(missing_source_ids) + ' 题未提供来源（待核对）')
    p = paragraph(label='答案来源', role='muted')
    run(p, '；'.join(source_notes), color='muted', size=9)
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True); doc.save(output)
    return audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='复盘 JSON 文件')
    parser.add_argument('--output', type=Path, help='输出 .docx 路径')
    parser.add_argument('--check-only', action='store_true', help='只校验数据，不创建 Word')
    parser.add_argument('--cjk-font', help='覆盖中文字体，例如 Microsoft YaHei 或 Noto Sans CJK SC')
    parser.add_argument('--english-font', help='覆盖英文字体；默认 Arial')
    parser.add_argument('--template', type=Path, help='可选：自定义同结构的 .docx 版式模板')
    parser.add_argument('--style', type=Path, help='可选：自定义 word-style.json')
    args = parser.parse_args(argv)
    if not args.check_only and not args.output:
        parser.error('生成 Word 时需要 --output；只查数据请用 --check-only')
    if args.output and args.output.suffix.lower() != '.docx':
        parser.error('--output 必须以 .docx 结尾')
    try:
        data = json.loads(args.input.read_text(encoding='utf-8'))
        audit = validate(data)
        if not args.check_only:
            build_document(data, args.output, args.template, args.style, args.cjk_font, args.english_font)
    except (DataError, OSError, json.JSONDecodeError) as error:
        print(f'错误：{error}', file=sys.stderr)
        return 2
    print(json.dumps({'validated': True, 'output': None if args.check_only else str(args.output), **audit}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
