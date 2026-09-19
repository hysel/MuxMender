"""Normalize metadata names only; never hide a changed or ambiguous value."""


def canonical_tags(tags, context='metadata'):
    if not isinstance(tags, dict):
        raise ValueError(f'Invalid tags in {context}')
    result = {}
    for name, value in tags.items():
        key = name.casefold()
        if key in result and result[key] != value:
            raise ValueError(f'Conflicting metadata keys in {context}: {key}')
        result[key] = value
    return result


def canonical_chapters(chapters):
    return [{**chapter, 'tags': canonical_tags(chapter.get('tags', {}), 'chapter')}
            for chapter in chapters]
