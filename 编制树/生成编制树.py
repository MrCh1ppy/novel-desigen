#!/usr/bin/env python3
"""Validate the organization catalogue and generate its Markdown/Mermaid view."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).with_name('编制数据.json')
OUTPUT = ROOT / '58-陆军历代团营编制树.md'
RELATIONS = {'organic': '-->', 'attached': '-. 配属 .->',
             'support': '-. 支援 .->', 'task': '-. 任务指挥 .->',
             'unknown': '-. 待定 .->'}


def nodes(node, depth=0):
    yield node, depth
    for child in node.get('children', []):
        yield from nodes(child, depth+1)


def validate(data):
    assert data['schema_version'] == 1
    templates = {t['id']: t for t in data['templates']}
    assert len(templates) == len(data['templates']), 'duplicate template ID'
    sections = {s['id'] for s in data['sections']}
    assert len(sections) == len(data['sections'])
    references = {key: set() for key in templates}
    for t in templates.values():
        assert re.fullmatch(r'[a-z][a-z0-9-]+', t['id']), t['id']
        assert t['section'] in sections
        assert t['period'] and t['basis'] and t['sources'] and t['views']
        for source in t['sources']:
            path, _, anchor = source['path'].partition('#')
            assert (ROOT/path).is_file(), source
            if anchor:
                assert f'id="{anchor}"' in (ROOT/path).read_text(encoding='utf-8'), source
        for view in t['views']:
            tree_nodes = list(nodes(view['root']))
            assert len(tree_nodes) <= 25, (t['id'], 'split oversized view')
            widths = Counter(depth for _, depth in tree_nodes)
            assert max(widths.values()) <= 7, (t['id'], 'split wide view')
            assert max(widths) <= 4, (t['id'], 'split deep view')
            for n, _ in tree_nodes:
                assert n['name'] and not any(x in n['name'] for x in ['\n','<','>','`','|'])
                assert n.get('relation','organic') in RELATIONS
                if n.get('quantity') is not None:
                    assert isinstance(n['quantity'], (int,str))
                    if isinstance(n['quantity'], int): assert n['quantity'] > 0
                if 'ref' in n:
                    assert n['ref'] in templates, (t['id'], n['ref'])
                    references[t['id']].add(n['ref'])
        for total in t.get('totals', []):
            assert sum(total['terms']) == total['value'], (t['id'], total)
        for ref in t.get('related', []): assert ref in templates
    # A subunit may be shared by many parents, but must never refer back to one.
    active, done = set(), set()
    def visit(key):
        assert key not in active, ('cyclic subunit reference',key)
        if key in done: return
        active.add(key)
        for ref in references[key]: visit(ref)
        active.remove(key); done.add(key)
    for key in templates: visit(key)
    return templates


def mermaid(root):
    definitions, edges, refs = [], [], set()
    def add(node):
        key = f'n{len(definitions)}'
        label = node['name']
        if node.get('quantity') is not None: label += f" ×{node['quantity']}"
        if node.get('detail'): label += f"（{node['detail']}）"
        label = label.replace('"','#quot;')
        definitions.append(f'    {key}["{label}"]')
        if node.get('ref'): refs.add(node['ref'])
        for child in node.get('children', []):
            child_key = add(child)
            edges.append(f"    {key} {RELATIONS[child.get('relation','organic')]} {child_key}")
        return key
    add(root)
    return '\n'.join(['```mermaid','flowchart LR',*definitions,*edges,'```']), refs


def render(data, templates):
    out = ['# 58 · 陆军历代团营编制树', '',
      '> 职责：集中管理已确认的团、营及其下级编制树，按年代区分常设建制、纸面定额和战役任务编组。装备原理、战术解释、战史与团号仍由所属专题维护。', '',
      '本页由[统一编制数据](编制树/编制数据.json)生成。同类下级单位共用固定模板编号；树下的“下钻”链接进入相应营、连、排模板，数量按当前父单位理解，不把多张视图相加。', '',
      '**图例**：实线为建制隶属或组成；虚线标明“配属”“支援”“任务指挥”或“待定”。“×3”表示三个同类单位；下级数量均为每个上级单位的数量。“待定”节点只是缺项提示，不等于已经成立该单位。', '',
      '**战时TG身份**：1970年代改革后，团营连进入战区通常迅速组织为RTG／BTG／CTG，并逐级受领、保留和下放任务资产；即使尚未得到额外加强，也不影响TG身份。团营连的永久行政建制另记。', '',
      '**年代与总量**：不得把后期装备、班排人数、坦克或FSV下放关系倒套早期；150条团史及历史300团峰值不进入本页的单团编制算式。缺少依据的团部、保障、车型与人员留空，已知车辆小计不表示全团／营完整总额。', '',
      '## 按年代与类型进入', '', '| 模板 | 年代／适用阶段 | 团／营及下级模板 | 状态 |', '|---|---|---|---|']
    for t in data['templates']:
        out.append(f"| [{t['id']}](#{t['id']}) | {t['period']} | {t['title']} | {t['basis']} |")
    out += ['', '各模板的详细树如下。折叠标题可展开；同一单位的多张图分别展示其主战、直属火力或保障，不新增中间建制。', '']
    for section in data['sections']:
        out += [f'<a id="era-{section["id"]}"></a>', '', f'## {section["title"]}', '',section['note'],'']
        for t in data['templates']:
            if t['section'] != section['id']: continue
            out += [f'<a id="{t["id"]}"></a>', '', '<details>', f'<summary>{t["id"]} · {t["title"]}</summary>', '',
                    f"**适用阶段：** {t['period']}。**记录性质：** {t['basis']}。", '']
            refs = set()
            for view in t['views']:
                out += [f'### {view["title"]}', '']
                graph, found = mermaid(view['root']); refs.update(found)
                out += [graph,'']
            if refs:
                out += ['**下钻：** '+'；'.join(f'[{r} · {templates[r]["title"]}](#{r})' for r in sorted(refs))+'。','']
            if t.get('totals'):
                out += ['| 已知小计 | 核算 | 结果 |','|---|---|---|']
                for total in t['totals']:
                    out.append(f"| {total['label']} | {'＋'.join(str(v) for v in total['terms'])} | {total['value']}{total['unit']} |")
                out.append('')
            if t.get('notes'):
                out += ['**边界与未定：**','',*[f'- {n}' for n in t['notes']],'']
            if t.get('related'):
                out += ['**对照：** '+'；'.join(f'[{r}](#{r})' for r in t['related'])+'。','']
            out += ['**依据：** '+'、'.join(f'[{s["label"]}]({s["path"]})' for s in t['sources'])+'。', '', '</details>','']
    out += ['<a id="gaps"></a>', '', '## 尚不能画成完整编制树的部分', '',
            '| 阶段／单位 | 已知与缺项 | 详细依据 |','|---|---|---|']
    for gap in data['gaps']:
        out.append(f"| {gap['name']} | {gap['note']} | [{gap['label']}]({gap['path']}) |")
    out += ['', '<a id="maintenance"></a>', '', '## 统一维护方法', '',
      '1. 在所属专题确认设定与年代边界；在[编制数据](编制树/编制数据.json)更新对应模板，新增年代另建模板，保留有效历史版本。',
      '2. 下级编制用`ref`引用已有模板；常设隶属、临时配属、支援和任务指挥用不同`relation`记录。多张视图不重复增加单位，四个改编类型列仍只由42号维护。',
      '3. 运行`python 编制树/生成编制树.py`生成本页；运行`python 编制树/生成编制树.py --check`核对数据、引用、算式及生成内容一致。无需第三方Python依赖。',
      '4. 回补受影响的时代专题和05号问题清单；图不替代战役证据，也不自动填补全军团数、比例、车辆实到或人员总额。', '']
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    data = json.loads(DATA.read_text(encoding='utf-8'))
    templates = validate(data)
    result = render(data, templates)
    if args.check:
        assert OUTPUT.read_text(encoding='utf-8') == result, 'generated page is stale; run generator'
    else:
        OUTPUT.write_text(result, encoding='utf-8')
    print(f"{'Checked' if args.check else 'Generated'} {len(templates)} templates, "
          f"{sum(len(t['views']) for t in templates.values())} trees.")


if __name__ == '__main__':
    main()
