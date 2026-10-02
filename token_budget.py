"""Compact model input only; original evidence and saved records stay intact."""
import copy
import re


def compact_material(material):
    result = copy.deepcopy(material)
    segments = result.get('segments')
    if segments is not None:
        point = result.get('point')
        if point:
            refs = set(point.get('refs', []))
            selected = {i for i, seg in enumerate(segments) if seg['id'] in refs}
            # All cited evidence is mandatory. Nearby context has a bounded budget.
            size = sum(len(segments[i]['text']) for i in selected)
            if result.get('action') == 'ask':
                query = result.get('answer', '').lower()
                words = re.findall(r'[a-z0-9_+]+|[\u4e00-\u9fff]', query)
                terms = set(w for w in words if len(w)>1)
                terms.update(query[i:i+2] for i in range(len(query)-1) if re.fullmatch(r'[\u4e00-\u9fff]{2}',query[i:i+2]))
                scores = sorted(((sum(t in s['text'].lower() for t in terms), i) for i,s in enumerate(segments)), key=lambda pair:(-pair[0],pair[1]))
                for score,i in scores[:12]:
                    if score and i not in selected and size+len(segments[i]['text'])<=6000:
                        selected.add(i);size+=len(segments[i]['text'])
            for i in sorted(selected.copy()):
                for j in (i-1, i+1, i-2, i+2):
                    if 0 <= j < len(segments) and j not in selected and size + len(segments[j]['text']) <= 6000:
                        selected.add(j)
                        size += len(segments[j]['text'])
            if selected:
                segments = [segments[i] for i in sorted(selected)]
            result['scope'] = '仅当前知识点引用、追问相关检索及邻近片段；不足时明确说明，不猜测未提供内容。'
        # Eliminate repeated JSON keys and timestamps, not source text or IDs.
        result['segments'] = '\n'.join(f"[{s['id']}] {s['text']}" for s in segments)
        if not point:
            original = material['segments']
            result['coverage_range'] = {'count': len(original), 'start': original[0].get('start') if original else None,
                                        'end': original[-1].get('end') if original else None}
    if 'history' in result:
        point_id = result.get('point', {}).get('id')
        recent = [m for m in result['history'] if m.get('point') == point_id][-4:]
        result['history'] = [{k: m[k] for k in ('role', 'text', 'question') if k in m} for m in recent]
    if 'record' in result:
        r = result['record']
        result['record'] = {'status': r.get('status'), 'skipped': r.get('skipped', False)}
    return result


def output_budget(material):
    return 1000 if 'action' in material else 3200
