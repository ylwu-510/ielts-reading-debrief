"""Behavioral invariants; run: python -m unittest discover -s tests -v"""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_review', ROOT / 'scripts/build_review.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def fixture():
    return {
        'title': '原创练习复盘', 'subtitle': 'A community garden',
        'sources': [{'id': 'p', 'label': '原创测试原文', 'text': 'Before the change, the garden was closed in winter. It is now open every day.'}, {'id': 'key', 'label': '原创练习参考答案', 'text': '1 A; 3 winter'}],
        'answers': [
            {'id': 1, 'type': '信息匹配', 'user_answer': 'B', 'key': 'A', 'status': 'wrong', 'answer_source': 'key'},
            {'id': 2, 'type': '信息匹配', 'user_answer': 'C', 'key': None, 'status': 'unverified'},
            {'id': 3, 'type': '填空', 'user_answer': 'winter', 'key': 'winter', 'status': 'correct', 'answer_source': 'key'},
        ],
        'answer_routes': [
            {'id': 1, 'status': 'verified', 'source': 'p', 'entry': 'change 与 opening times', 'path': '扫读开放时间，遇到 Before 后连读带 now 的下一句。', 'location': 'A 段第 1—2 句', 'check': '过去与现在两端都对应开放时间。', 'time_saver': '并排核对 Before 与 now 两端，条件满足后停止寻找其他时间词。'},
            {'id': 2, 'status': 'pending', 'reason': '答案及对应原文尚未核对。', 'entry': '先保留题干中独特的对象词。'},
            {'id': 3, 'status': 'verified', 'source': 'p', 'entry': 'closed 与季节空缺', 'path': '扫到 closed 后读 in 后面的季节词。', 'location': 'A 段第 1 句', 'check': '季节词填入空缺后意思和词数均满足要求。', 'time_saver': '复用第 1 题的开放时间证据，只提取季节词。'},
        ],
        'overview': {'focus': '先查全时间条件。', 'type_comments': {'信息匹配': '仍有一题待核对。'}},
        'questions': [{
            'id': 1, 'title': '开放时间的变化',
            'requirement': {'text': 'A change in opening times', 'meaning': '寻找前后时间的变化。'},
            'evidence': [{'source': 'p', 'location': 'A 段', 'quote': 'Before the change, the garden was closed in winter.', 'explanation': '这里给出过去的开放情况。', 'emphasis': ['Before', 'closed in winter']}],
            'comparison': 'B 未提供之前的情况。',
            'cause': {'code': '04', 'certainty': 'possible', 'observation': '答案只对应了部分条件。', 'self_check': '能否说出需要比较的两个时间？'},
            'action': '找到候选后补查前后两种情况。',
        }],
        'causes': [{'code': '04', 'question_ids': [1], 'training': '对照两端分别找到证据。'}],
        'method': {k: v + '具体动作。' for k, v in builder.METHODS.items()},
        'highlights': {'status': 'not_provided', 'add': [], 'reduce': [], 'keep': [], 'boundary': '实际标记未提供。'},
    }


def built_document(data):
    from docx import Document
    with tempfile.TemporaryDirectory() as folder:
        output = Path(folder) / 'review.docx'
        builder.build_document(data, output)
        return Document(output)


def coaching_fixture():
    data = fixture()
    data['overview']['passage_map'] = [
        {'paragraph': 'A', 'role': '说明开放时间的前后变化。', 'use': '变化题与季节填空可共用同一组证据。'},
    ]
    data['answer_routes'][0]['test_point'] = '比较对象一致，过去与现在两端齐全。'
    data['answer_routes'][2]['test_point'] = '从时间限定中提取符合词数要求的季节词。'
    data['questions'][0]['cause']['stage'] = '候选确认：是否查全前后两个时间条件。'
    data['method']['habits'] = [
        {'name': '两端查全再确定', 'trigger': '题干要求变化或对比。', 'action': '分别指出过去和现在的证据，再决定答案。', 'pass_check': '每个比较对象都能对应到原文。', 'record': '记录缺了一端就提前作答的次数。'},
        {'name': '复用已找到的位置', 'trigger': '下一题仍涉及开放时间。', 'action': '先查已定位句的上下文，再决定是否扩大范围。', 'pass_check': '能从已定位位置取得证据时不重新全文扫描。', 'record': '记录无必要的全文重扫次数。'},
    ]
    return data


def table_with_header(doc, header):
    return next(table for table in doc.tables if table.cell(0, 0).text == header)


def not_given_fixture():
    data = fixture()
    data['answers'][0].update(type='判断题', user_answer='FALSE', key='NOT GIVEN')
    data['sources'][1]['text'] = '1 NOT GIVEN; 3 winter'
    data['overview']['type_comments'] = {}
    question = data['questions'][0]
    question.update(
        title='花园是否收取入场费', evidence_type='not_given', evidence=[],
        requirement={'text': 'Visitors were charged an admission fee.', 'meaning': '核对访客是否需要付费。'},
        evidence_review={'source': 'p', 'scope': 'A 段全部两句，涉及过去和现在的开放时间。', 'missing_information': '未说明访客与入场费用的关系，不能推出收费或免费。'},
        comparison='FALSE 需要原文明确否定收费；现有内容只说明开放时间。',
        cause={'code': None, 'certainty': 'unconfirmed', 'observation': '本题将未提供费用信息判成了明确否定。', 'self_check': '当时依据哪个词判定免费？若未找到，记录当时如何推断。'},
        action='区分明确否定与没有说明；找不到费用关系时保留待判状态。',
    )
    data['causes'] = [{'status': 'pending', 'code': None, 'question_ids': [1], 'training': '回忆作答过程后再归类。'}]
    data['answer_routes'][0].update(entry='charged / admission fee', path='扫查收费及免费相关表达，再核查开放安排两句是否建立费用关系。', location='A 段全部两句及开放安排语境', check='只说明开放时间，未说明是否收费，不能推出免费。', time_saver='记下已核查的两句及缺失的费用关系，避免在同一范围重复搜索；未完成核查前不判 NOT GIVEN。')
    return data


class ReviewValidationTests(unittest.TestCase):
    def test_passage_map_requires_nonempty_rows_and_unique_paragraphs(self):
        valid = coaching_fixture()
        for invalid in (None, {}, [], [None]):
            with self.subTest(value=invalid):
                data = deepcopy(valid); data['overview']['passage_map'] = invalid
                with self.assertRaisesRegex(builder.DataError, 'passage_map'):
                    builder.validate(data)
        for field in ('paragraph', 'role', 'use'):
            for value in ('', '   ', None, 1):
                data = deepcopy(valid); data['overview']['passage_map'][0][field] = value
                with self.assertRaisesRegex(builder.DataError, field):
                    builder.validate(data)
        data = deepcopy(valid)
        repeated = deepcopy(data['overview']['passage_map'][0]); repeated['paragraph'] = ' A '
        data['overview']['passage_map'].append(repeated)
        with self.assertRaisesRegex(builder.DataError, '重复'):
            builder.validate(data)

    def test_habit_plan_requires_one_or_two_complete_action_records(self):
        valid = coaching_fixture()
        for invalid in (None, {}, [], [None], valid['method']['habits'] * 2):
            with self.subTest(value=invalid):
                data = deepcopy(valid); data['method']['habits'] = invalid
                with self.assertRaisesRegex(builder.DataError, 'habits'):
                    builder.validate(data)
        for field in ('name', 'trigger', 'action', 'pass_check', 'record'):
            for value in ('', '   ', None, 1):
                data = deepcopy(valid); data['method']['habits'][0][field] = value
                with self.assertRaisesRegex(builder.DataError, field):
                    builder.validate(data)
            data = deepcopy(valid); del data['method']['habits'][0][field]
            with self.assertRaisesRegex(builder.DataError, field):
                builder.validate(data)
        valid['method']['habits'].pop()
        builder.validate(valid)

    def test_new_optional_text_rejects_blank_values_even_for_pending_routes(self):
        for index in (0, 1):
            for invalid in ('', '   ', None, 1, []):
                data = fixture(); data['answer_routes'][index]['test_point'] = invalid
                with self.assertRaisesRegex(builder.DataError, 'test_point'):
                    builder.validate(data)
        for invalid in ('', '   ', None, 1, []):
            data = fixture(); data['questions'][0]['cause']['stage'] = invalid
            with self.assertRaisesRegex(builder.DataError, 'stage'):
                builder.validate(data)

    def test_coaching_fields_render_without_changing_evidence_scores_or_five_sections(self):
        import json
        data = coaching_fixture()
        data['method']['speed_plan'] = {
            'context': '本篇用时未记录；以下为下一轮建议。',
            'steps': [{'stage': '先定位', 'action': '用开放时间线索定位后共用证据。', 'saves': '免去重复全文扫描。'}],
            'stop_rule': '核对两端后仍不确定时标记缺项再暂放。',
            'practice': '使用新材料同时记录完成情况、正确率和用时。',
        }
        before = deepcopy(data)
        baseline = builder.validate(fixture())
        self.assertEqual(builder.validate(data), baseline)
        doc = built_document(data)
        self.assertEqual(data, before)
        text = '\n'.join(p.text for p in doc.paragraphs)
        self.assertEqual([p.text for p in doc.paragraphs if p.style.name == 'Heading 1'], builder.SECTIONS)
        self.assertLess(text.index('本篇重点'), text.index('全文检索地图'))
        self.assertLess(text.index('全文检索地图'), text.index('02 逐题复盘'))
        self.assertIn('不要求考场上先读完全篇或制作此表', text)
        passage_map = table_with_header(doc, '段落')
        self.assertEqual([c.text for c in passage_map.rows[1].cells], list(data['overview']['passage_map'][0].values()))
        routes = table_with_header(doc, '题号')
        cell = routes.cell(1, 2)
        self.assertLess(cell.text.index('考点：'), cell.text.index('判定：'))
        self.assertLess(cell.text.index('判定：'), cell.text.index('省时：'))
        self.assertIn(data['answer_routes'][2]['test_point'], routes.cell(3, 2).text)
        style = json.loads((ROOT / 'assets/word-style.json').read_text())
        point_label = next(r for r in cell.paragraphs[0].runs if r.text == '考点：')
        self.assertTrue(point_label.bold)
        self.assertEqual(str(point_label.font.color.rgb), style['colors']['brown'])
        point_value = next(r for r in cell.paragraphs[0].runs if r.text == data['answer_routes'][0]['test_point'] + '\n')
        self.assertFalse(point_value.bold)
        self.assertEqual(str(point_value.font.color.rgb), style['colors']['body'])
        self.assertIn('优先检查环节：', text)
        self.assertNotIn('出错环节：', text)
        self.assertIn(data['questions'][0]['evidence'][0]['quote'], text)
        self.assertIn('完成情况以练习记录为准', text)
        self.assertLess(text.index('本篇提速路线'), text.index('本轮训练动作'))
        self.assertLess(text.index('怎样练快'), text.index('本轮训练动作'))
        self.assertLess(text.index('本轮训练动作'), text.index('读题　'))
        for habit in data['method']['habits']:
            for value in habit.values():
                self.assertIn(value, text)
        for label in ('作答结果', '题目要求', '正确证据', '答案对比', '错因判断', '下次动作', '触发：', '动作', '验收', '记录：'):
            self.assertIn(label, text)

    def test_stage_label_follows_existing_cause_certainty_and_never_confirms_it(self):
        for certainty in ('possible', 'unconfirmed', 'confirmed'):
            data = coaching_fixture(); cause = data['questions'][0]['cause']; cause['certainty'] = certainty
            if certainty == 'unconfirmed':
                cause['code'] = None
                data['causes'][0]['code'] = None
            elif certainty == 'confirmed':
                cause['basis'] = '用户复述作答当时只检查了现在的开放时间。'
            doc = built_document(data); text = '\n'.join(p.text for p in doc.paragraphs)
            if certainty == 'confirmed':
                self.assertIn('出错环节：', text)
                self.assertNotIn('优先检查环节：', text)
                self.assertIn(cause['basis'], text)
            else:
                self.assertIn('优先检查环节：', text)
                self.assertNotIn('出错环节：', text)
                self.assertIn('自测：', text)

    def test_legacy_review_needs_no_new_coaching_fields(self):
        data = fixture(); doc = built_document(data)
        text = '\n'.join(p.text for p in doc.paragraphs)
        for heading in ('全文检索地图', '本轮训练动作', '优先检查环节：', '出错环节：'):
            self.assertNotIn(heading, text)
        cell = table_with_header(doc, '题号').cell(1, 2)
        self.assertNotIn('考点：', cell.text)
        self.assertTrue(cell.text.startswith(data['answer_routes'][0]['check']))

    def test_unknown_answer_is_neither_wrong_nor_correct(self):
        audit = builder.validate(fixture())
        self.assertEqual(audit['counts'], {'wrong': 1, 'unverified': 1, 'correct': 1})
        self.assertEqual(audit['wrong_ids'], ['1'])

    def test_routes_must_include_correct_questions_exactly_once(self):
        data = fixture(); data['answer_routes'].pop()
        with self.assertRaises(builder.DataError):
            builder.validate(data)
        data = fixture(); data['answer_routes'].append(deepcopy(data['answer_routes'][0]))
        with self.assertRaises(builder.DataError):
            builder.validate(data)
        data['answer_routes'][-1]['id'] = 99
        with self.assertRaises(builder.DataError):
            builder.validate(data)

    def test_routes_reject_unverified_claims_and_invalid_sources(self):
        data = fixture(); data['answer_routes'][0]['source'] = 'missing'
        with self.assertRaises(builder.DataError):
            builder.validate(data)
        data = fixture(); data['answer_routes'][1] = deepcopy(data['answer_routes'][0]); data['answer_routes'][1]['id'] = 2
        with self.assertRaises(builder.DataError):
            builder.validate(data)
        for field in ('entry', 'path', 'location', 'check'):
            data = fixture(); del data['answer_routes'][0][field]
            with self.assertRaises(builder.DataError):
                builder.validate(data)

    def test_verified_routes_require_a_specific_time_saver(self):
        for index in (0, 2):
            for value in (None, '', '   ', ['省时动作']):
                with self.subTest(question=fixture()['answer_routes'][index]['id'], value=value):
                    data = fixture()
                    if value is None:
                        del data['answer_routes'][index]['time_saver']
                    else:
                        data['answer_routes'][index]['time_saver'] = value
                    with self.assertRaisesRegex(builder.DataError, 'time_saver'):
                        builder.validate(data)
        data = fixture()
        builder.validate(data)  # A pending route can omit advice that cannot yet be verified.
        data['answer_routes'][1]['time_saver'] = ''
        with self.assertRaisesRegex(builder.DataError, 'time_saver'):
            builder.validate(data)
        data['answer_routes'][1]['time_saver'] = '先补齐原文，再安排具体定位动作。'
        self.assertEqual(builder.validate(data)['counts']['unverified'], 1)

    def test_route_time_saver_is_visible_and_uses_the_approved_table_style(self):
        import json
        data = fixture()
        data['answer_routes'][0]['if_stuck'] = '记下两端分别对应什么，再处理下一题。'
        doc = built_document(data); table = table_with_header(doc, '题号')
        style = json.loads((ROOT / 'assets/word-style.json').read_text())
        self.assertEqual(table.cell(0, 2).text, '确认与省时动作')
        for column, width in zip(table.columns, (1.5, 8.1, 7.8)):
            self.assertAlmostEqual(column.width.cm, width, places=2)
        cell = table.cell(1, 2)
        self.assertLess(cell.text.index('省时：'), cell.text.index('暂放：'))
        label = next(r for r in cell.paragraphs[0].runs if r.text == '省时：')
        value = next(r for r in cell.paragraphs[0].runs if r.text == data['answer_routes'][0]['time_saver'])
        self.assertTrue(label.bold)
        self.assertEqual(str(label.font.color.rgb), style['colors']['green'])
        self.assertFalse(value.bold)
        self.assertEqual(str(value.font.color.rgb), style['colors']['body'])
        self.assertTrue(all(r.font.size.pt == style['table']['size'] for r in cell.paragraphs[0].runs))
        self.assertIn(data['answer_routes'][2]['time_saver'], table.cell(3, 2).text)
        self.assertNotIn('省时：', table.cell(2, 2).text)

    def test_speed_plan_preserves_wrong_analysis_correct_routes_and_unknown_status(self):
        data = fixture()
        data['method']['speed_plan'] = {
            'context': '本篇用时未记录；以下路线供下一次练习验证。',
            'steps': [
                {'stage': '第一轮', 'action': '先核对前后开放时间，并记录对应句。', 'saves': '同一证据兼顾变化题和季节填空。'},
                {'stage': '第二轮', 'action': '补齐第 2 题材料后再安排路线。', 'saves': '避免围绕尚未核对的答案来回寻找。'},
            ],
            'stop_rule': '核对两端后仍无法区分候选，先记下争议条件再暂放。',
            'practice': '用新题记录定位耗时与重复回读次数，并同时记录正确率。',
        }
        self.assertEqual(builder.validate(data)['counts'], {'wrong': 1, 'unverified': 1, 'correct': 1})
        doc = built_document(data); text = '\n'.join(p.text for p in doc.paragraphs)
        self.assertEqual([p.text for p in doc.paragraphs if p.style.name == 'Heading 1'], builder.SECTIONS)
        self.assertLess(text.index('04 下一篇怎样做'), text.index('本篇提速路线'))
        self.assertLess(text.index('本篇提速路线'), text.index('读题　'))
        for label in ('作答结果', '题目要求', '正确证据', '答案对比', '错因判断', '下次动作', '何时暂放', '怎样练快'):
            self.assertIn(label, text)
        plan = table_with_header(doc, '先后安排')
        self.assertEqual([c.text for c in plan.rows[0].cells], ['先后安排', '具体操作', '省在哪里'])
        self.assertEqual(len(plan.rows), 3)
        for column, width in zip(plan.columns, (3, 9.4, 5)):
            self.assertAlmostEqual(column.width.cm, width, places=2)
        routes = table_with_header(doc, '题号')
        self.assertEqual([r.cells[0].text for r in routes.rows[1:]], ['1', '2', '3'])
        self.assertIn('待核对', routes.cell(2, 1).text)
        self.assertIn('复用第 1 题', routes.cell(3, 2).text)
        for field in ('context', 'stop_rule', 'practice', 'steps'):
            broken = deepcopy(data); del broken['method']['speed_plan'][field]
            with self.assertRaises(builder.DataError):
                builder.validate(broken)
        for invalid in (None, [], {'context': '说明', 'stop_rule': '暂放', 'practice': '练习', 'steps': []}):
            broken = deepcopy(data); broken['method']['speed_plan'] = invalid
            with self.assertRaises(builder.DataError):
                builder.validate(broken)
        for field in ('stage', 'action', 'saves'):
            for value in ('', None, 2):
                broken = deepcopy(data); broken['method']['speed_plan']['steps'][0][field] = value
                with self.assertRaises(builder.DataError):
                    builder.validate(broken)

    def test_pending_route_retains_score_and_routes_follow_answer_order(self):
        data = fixture(); baseline = builder.validate(data)['counts']
        data['answer_routes'][2] = {'id': 3, 'status': 'pending', 'reason': '答案已批改，但没有可核对的题干截图。', 'entry': '暂时只保留 closed。'}
        data['answer_routes'].reverse()
        self.assertEqual(builder.validate(data)['counts'], baseline)
        doc = built_document(data); table = table_with_header(doc, '题号')
        self.assertEqual([row.cells[0].text for row in table.rows[1:]], ['1', '2', '3'])
        self.assertIn('待核对：答案已批改', table.cell(3, 1).text)
        self.assertNotIn('A 段', table.cell(3, 1).text)
        self.assertIn('核对条件待补充', table.cell(3, 2).text)
        self.assertEqual(sum(p.text.startswith('作答结果') for p in doc.paragraphs), 1)
        del data['answer_routes'][0]['reason']
        with self.assertRaises(builder.DataError):
            builder.validate(data)

    def test_not_given_route_shows_search_scope_and_missing_relationship(self):
        data = not_given_fixture()
        data['answer_routes'][0]['if_stuck'] = '暂记核查范围，先做下一题后回查。'
        table = table_with_header(built_document(data), '题号')
        self.assertIn('charged / admission fee', table.cell(1, 1).text)
        self.assertIn('A 段全部两句', table.cell(1, 1).text)
        self.assertIn('未说明是否收费', table.cell(1, 2).text)
        self.assertIn('暂放：暂记核查范围', table.cell(1, 2).text)

    def test_route_table_labels_sources_only_when_they_differ(self):
        data = fixture(); table = table_with_header(built_document(data), '题号')
        self.assertNotIn('[p]', table.cell(1, 1).text)
        self.assertAlmostEqual(table.columns[0].width.cm, 1.5, places=2)
        data['sources'].append({'id': 'p2', 'label': '第二份原文材料'})
        data['answer_routes'][2]['source'] = 'p2'
        table = table_with_header(built_document(data), '题号')
        self.assertIn('[p]', table.cell(1, 1).text)
        self.assertIn('[p2]', table.cell(3, 1).text)

    def test_recorded_timing_overrides_legacy_text_and_calculates_delta(self):
        data = fixture(); data['overview']['time'] = '旧记录：99 分钟'
        data['overview']['timing'] = {'scope': 'passage', 'elapsed_minutes': 23.5, 'budget_minutes': 20, 'basis': '手机秒表；本篇从读题至填答结束。', 'completion_note': '已完成全部题目。'}
        text = '\n'.join(p.text for p in built_document(data).paragraphs)
        self.assertIn('单篇阅读：实际 23.5 分钟；预算 20 分钟；超时 3.5 分钟', text)
        self.assertIn('计时依据　手机秒表', text)
        self.assertIn('完成情况　已完成全部题目', text)
        self.assertNotIn('99 分钟', text)
        data['overview']['timing']['elapsed_minutes'] = 17
        self.assertIn('余量 3 分钟', builder.timing_summary(data['overview']['timing']))
        data['overview']['timing']['elapsed_minutes'] = 20
        self.assertIn('与预算一致', builder.timing_summary(data['overview']['timing']))

    def test_timing_scope_and_missing_budget_do_not_invent_targets(self):
        for scope, label in builder.TIMING_SCOPES.items():
            data = fixture(); data['overview']['timing'] = {'scope': scope, 'elapsed_minutes': 25, 'basis': '用户记录。'}
            builder.validate(data)
            summary = builder.timing_summary(data['overview']['timing'])
            self.assertIn(label, summary)
            self.assertNotIn('预算', summary)
            self.assertNotIn('超时', summary)
        for changes in ({'scope': 'unknown'}, {'basis': ''}, {'elapsed_minutes': 0}, {'elapsed_minutes': True}, {'elapsed_minutes': float('inf')}, {'budget_minutes': float('nan')}, {'budget_minutes': -1}):
            data = fixture(); data['overview']['timing'] = {'scope': 'passage', 'elapsed_minutes': 25, 'basis': '用户记录。', **changes}
            with self.assertRaises(builder.DataError):
                builder.validate(data)

    def test_unconfirmed_cause_can_remain_unclassified(self):
        data = fixture()
        data['questions'][0]['cause'].update(code=None, certainty='unconfirmed')
        data['causes'] = [{'status': 'pending', 'code': None, 'question_ids': [1], 'training': '先复述当时的核对过程。'}]
        audit = builder.validate(data)
        self.assertEqual(audit['counts']['wrong'], 1)
        doc = built_document(data)
        text = '\n'.join(p.text for p in doc.paragraphs)
        for label in ('作答结果', '题目要求', '正确证据', '答案对比', '错因判断', '下次动作'):
            self.assertIn(label, text)
        self.assertIn('待确认，尚未归类', text)
        cause_text = next(p.text for p in doc.paragraphs if p.text.startswith('错因判断'))
        self.assertLess(cause_text.index(data['questions'][0]['cause']['observation']), cause_text.index('个人原因：'))
        self.assertIn('待确认未归类', table_with_header(doc, '本次涉及的类别').cell(1, 0).text)
        for invalid in ({'code': '04'}, {'code': None, 'self_check': ''}):
            broken = deepcopy(data); broken['questions'][0]['cause'].update(invalid)
            with self.assertRaises(builder.DataError):
                builder.validate(broken)

    def test_candidates_are_hypotheses_not_extra_wrong_answers(self):
        data = fixture(); data['questions'][0]['cause']['candidates'] = ['05']
        data['causes'].append({'status': 'pending', 'code': '05', 'question_ids': [1], 'training': '比较两段完整信息。'})
        audit = builder.validate(data)
        self.assertEqual(audit['counts']['wrong'], 1)
        self.assertEqual(audit['cause_statuses'], ['pending', 'pending'])
        text = '\n'.join(p.text for p in built_document(data).paragraphs)
        self.assertIn('不能相加作为错题数', text)
        for candidates in (['05', '05'], ['04']):
            broken = deepcopy(data); broken['questions'][0]['cause']['candidates'] = candidates
            with self.assertRaises(builder.DataError):
                builder.validate(broken)
        data['questions'][0]['cause'].update(code=None, certainty='unconfirmed', candidates=['04', '05'])
        self.assertEqual(builder.validate(data)['counts']['wrong'], 1)

    def test_feedback_requires_removing_excluded_candidates(self):
        data = fixture(); data['questions'][0]['cause']['candidates'] = ['05']
        data['causes'].append({'status': 'pending', 'code': '05', 'question_ids': [1], 'training': '比較候选。'})
        builder.validate(data)
        data['questions'][0]['cause'].update(code='05', certainty='confirmed', candidates=[], basis='用户复述：已查过两个时间，却在最后比较时选了只含一端的段落。')
        with self.assertRaises(builder.DataError):
            builder.validate(data)
        data['causes'] = [{'status': 'confirmed', 'code': '05', 'question_ids': [1], 'training': '最后并列核对两个候选。'}]
        builder.validate(data)
        text = '\n'.join(p.text for p in built_document(data).paragraphs)
        self.assertIn('确认依据：用户复述', text)
        self.assertNotIn('候选：', text)
        del data['questions'][0]['cause']['basis']
        with self.assertRaises(builder.DataError):
            builder.validate(data)

    def test_confirmed_and_pending_same_code_are_separate_rows(self):
        data = fixture()
        data['answers'][1].update(key='A', status='wrong', answer_source='key')
        second = deepcopy(data['questions'][0]); second['id'] = 2
        second['cause'].update(certainty='confirmed', basis='用户确认当时只核对了一个时间条件。')
        data['questions'].append(second)
        data['causes'][0]['question_ids'] = [1, 2]
        with self.assertRaises(builder.DataError):
            builder.validate(data)
        data['causes'][0]['question_ids'] = [1]
        data['causes'].append({'code': '04', 'question_ids': [2], 'training': '逐项核对限制条件。'})
        audit = builder.validate(data)
        self.assertEqual(audit['cause_statuses'], ['pending', 'confirmed'])
        data['causes'].append(deepcopy(data['causes'][0]))
        with self.assertRaises(builder.DataError):
            builder.validate(data)

    def test_not_given_uses_review_scope_without_fabricated_quote(self):
        data = not_given_fixture(); builder.validate(data)
        text = '\n'.join(p.text for p in built_document(data).paragraphs)
        self.assertIn('正确证据　核查范围：[p] A 段全部两句', text)
        self.assertIn('缺失信息：未说明访客与入场费用的关系', text)
        self.assertNotIn('暂缺可核对的原文证据', text)
        for field in ('source', 'scope', 'missing_information'):
            broken = deepcopy(data); del broken['questions'][0]['evidence_review'][field]
            with self.assertRaises(builder.DataError):
                builder.validate(broken)
        data['questions'][0]['evidence_review']['source'] = 'missing'
        with self.assertRaises(builder.DataError):
            builder.validate(data)

    def test_not_given_key_cannot_use_direct_quote_as_shortcut(self):
        for key in ('NOT GIVEN', 'NG', ['NOT GIVEN', 'NG']):
            data = fixture(); data['answers'][0]['key'] = key
            with self.assertRaises(builder.DataError):
                builder.validate(data)

    def test_explicit_judgment_cannot_use_not_given_to_omit_evidence(self):
        for key in ('TRUE', 'FALSE', 'YES', 'NO'):
            with self.subTest(key=key):
                data = not_given_fixture()
                data['answers'][0].update(key=key, user_answer='NOT GIVEN')
                with self.assertRaises(builder.DataError):
                    builder.validate(data)

    def test_main_idea_builds_broad_evidence_and_explanation(self):
        data = fixture(); q = data['questions'][0]
        data['answers'][0].update(type='标题匹配', user_answer='i', key='ii')
        data['overview']['type_comments'] = {}
        q.update(title='开放范围扩大', evidence_type='main_idea',
                 requirement={'text': 'Choose the best heading for paragraph A.', 'meaning': '选择覆盖整段两句内容的标题。'},
                 comparison='过去关闭只是背景；开放范围扩大同时覆盖过去限制和现在每天开放。')
        q['evidence'][0].update(quote=data['sources'][0]['text'], explanation='前句说明过去的季节限制，后句说明现在全年每天开放；整段核心是开放范围扩大。')
        doc = built_document(data)
        text = '\n'.join(p.text for p in doc.paragraphs)
        self.assertIn(data['sources'][0]['text'], text)
        self.assertIn('整段核心是开放范围扩大', text)
        q['evidence'] = []
        with self.assertRaises(builder.DataError):
            builder.validate(data)

    def test_contradiction_keeps_quote_requirement(self):
        data = fixture(); q = data['questions'][0]
        data['answers'][0].update(type='判断题', user_answer='TRUE', key='FALSE')
        data['overview']['type_comments'] = {}
        q.update(evidence_type='contradiction', requirement={'text': 'The garden was open every winter before the change.', 'meaning': '核对过去是否每年冬季开放。'})
        q['evidence'][0]['explanation'] = '原文明说过去冬季关闭，与题干的冬季开放相反。'
        text = '\n'.join(p.text for p in built_document(data).paragraphs)
        self.assertIn('与题干的冬季开放相反', text)
        q['evidence'] = []
        with self.assertRaises(builder.DataError):
            builder.validate(data)

    def test_highlights_order_core_before_optional_without_style_change(self):
        data = fixture()
        def marked(location, priority):
            return {'source': 'p', 'location': location, 'observed': 'It is now open every day.', 'reason': '保存时间证据。', 'priority': priority}
        data['highlights'].update(status='observed', keep=[marked('可选记录', 'optional'), marked('核心记录', 'core')])
        for group in ('add', 'reduce'):
            data['highlights'][group] = [marked('可选记录', 'optional'), marked('核心记录', 'core')]
            for row in data['highlights'][group]:
                row.update(quote='It is now open every day.', action='缩短到 now 和 every day')
        doc = built_document(data)
        text = '\n'.join(p.text for p in doc.paragraphs)
        self.assertLess(text.index('核心记录'), text.index('可选记录（可选）'))
        for table in doc.tables[3:]:
            self.assertEqual(table.cell(1, 0).text, '核心记录')
            self.assertEqual(table.cell(2, 0).text, '可选记录（可选）')
        self.assertEqual(doc.styles['Normal'].font.size.pt, 11)
        data['highlights']['keep'][0]['priority'] = 'urgent'
        with self.assertRaises(builder.DataError):
            builder.validate(data)

    def test_verified_answers_require_declared_answer_source(self):
        for index in (0, 2):
            with self.subTest(status=fixture()['answers'][index]['status']):
                data = fixture(); del data['answers'][index]['answer_source']
                with self.assertRaises(builder.DataError):
                    builder.validate(data)
                data = fixture(); data['answers'][index]['answer_source'] = 'missing'
                with self.assertRaises(builder.DataError):
                    builder.validate(data)

    def test_optional_unverified_source_is_checked_without_changing_status(self):
        data = fixture(); data['answers'][1]['answer_source'] = 'missing'
        with self.assertRaises(builder.DataError):
            builder.validate(data)
        data['answers'][1]['answer_source'] = 'key'
        audit = builder.validate(data)
        self.assertEqual(audit['counts']['unverified'], 1)
        self.assertEqual(audit['wrong_ids'], ['1'])

    def test_explicit_highlight_text_record_can_be_observed(self):
        data = fixture()
        data['sources'].append({'id': 'mark', 'label': '用户明确提供的高亮文字记录', 'text': 'A 段已标 It is now open every day.'})
        data['highlights'] = {
            'status': 'observed', 'add': [], 'reduce': [],
            'keep': [{'source': 'mark', 'location': 'A 段', 'observed': 'It is now open every day.', 'reason': '据用户文字记录，保留现在的时间条件。'}],
            'boundary': '依据用户高亮文字记录；未查看截图。',
        }
        self.assertEqual(builder.validate(data)['total'], 3)

    def test_missing_wrong_question_is_rejected(self):
        data = fixture(); data['questions'] = []
        with self.assertRaises(builder.DataError):
            builder.validate(data)

    def test_duplicate_id_is_rejected(self):
        data = fixture(); data['answers'].append(deepcopy(data['answers'][0]))
        with self.assertRaises(builder.DataError):
            builder.validate(data)

    def test_changed_source_quote_is_rejected(self):
        data = fixture(); data['questions'][0]['evidence'][0]['quote'] = 'The garden was always open.'
        with self.assertRaises(builder.DataError):
            builder.validate(data)

    def test_uncertain_cause_requires_self_check(self):
        data = fixture(); del data['questions'][0]['cause']['self_check']
        with self.assertRaises(builder.DataError):
            builder.validate(data)

    def test_unknown_highlights_cannot_claim_observation(self):
        data = fixture(); data['highlights']['keep'] = [{'source': 'p', 'location': 'A', 'observed': 'It is now open every day.', 'reason': '定位'}]
        with self.assertRaises(builder.DataError):
            builder.validate(data)

    def test_cause_summary_must_match_question(self):
        data = fixture(); data['causes'][0]['code'] = '05'
        with self.assertRaises(builder.DataError):
            builder.validate(data)

    def test_all_correct_keeps_structure_without_fake_errors(self):
        data = fixture(); data['answers'] = [data['answers'][2]]; data['questions'] = []; data['causes'] = []; data['overview']['type_comments'] = {}
        data['answer_routes'] = [data['answer_routes'][2]]
        audit = builder.validate(data)
        self.assertEqual(audit['counts'], {'correct': 1})
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'correct.docx'; builder.build_document(data, output)
            from docx import Document
            doc = Document(output)
            self.assertEqual([p.text for p in doc.paragraphs if p.style.name == 'Heading 1'], builder.SECTIONS)
            self.assertIn('本篇无错题。', [p.text for p in doc.paragraphs])

    def test_build_preserves_footer_and_overrides_cjk_everywhere(self):
        from docx import Document
        from docx.oxml.ns import qn
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'review.docx'
            builder.build_document(fixture(), output, cjk_font='Noto Sans CJK SC', english_font='Liberation Sans')
            doc = Document(output)
            self.assertEqual([p.text for p in doc.paragraphs if p.style.name == 'Heading 1'], builder.SECTIONS)
            self.assertTrue(any(el.get(qn('w:instr')) == 'PAGE' for el in doc.sections[0].footer._element.iter(qn('w:fldSimple'))))
            roots = [doc.element, doc.styles.element, doc.sections[0].footer._element]
            for root in roots:
                for rf in root.iter(qn('w:rFonts')):
                    self.assertEqual(rf.get(qn('w:eastAsia')), 'Noto Sans CJK SC')
                    self.assertEqual(rf.get(qn('w:ascii')), 'Liberation Sans')
            evidence = next(p for p in doc.paragraphs if p.text.startswith('正确证据'))
            self.assertTrue(any(r.bold and r.text == 'Before' for r in evidence.runs))
            self.assertTrue(any(not r.bold and 'the garden was' in r.text for r in evidence.runs))
            self.assertIn('待核对 1', '\n'.join(p.text for p in doc.paragraphs))
            source_notes = [p.text for p in doc.paragraphs if p.text.startswith('答案来源')]
            self.assertEqual(len(source_notes), 1)
            self.assertIn('[key] 第 1、3 题', source_notes[0])
            self.assertIn('第 2 题未提供来源（待核对）', source_notes[0])
            self.assertEqual(len(doc.tables), 3)


if __name__ == '__main__':
    unittest.main()
